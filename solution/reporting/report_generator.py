
import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from solution.config import (
    DATA_DIR,
    REPORT_DIR,
    DISPOSITIONS_PATH,
)
from solution.database.connection import get_connection
from solution.services.encryption import PIISecurity


IST = ZoneInfo("Asia/Kolkata")


def parse_timestamp(value):
    """Parse a stored UTC timestamp and return an aware datetime."""
    if not value:
        return None

    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def to_ist(value):
    """Convert a stored timestamp to IST."""
    parsed = parse_timestamp(value)

    if parsed is None:
        return None

    return parsed.astimezone(IST)


def load_disposition_metadata():
    """Load terminal and success flags from dispositions.csv."""
    metadata = defaultdict(dict)

    with DISPOSITIONS_PATH.open(
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as file:
        reader = csv.DictReader(file)

        for row in reader:
            workflow = row["workflow_id"].strip()
            code = row["code"].strip().lower()

            metadata[workflow][code] = {
                "is_terminal": row["is_terminal"].strip().lower() == "true",
                "is_success": row["is_success"].strip().lower() == "true",
            }

    return metadata


def write_csv(path, headers, rows):
    """Write a CSV file with a fixed column order."""
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open(
        "w",
        encoding="utf-8",
        newline=""
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=headers,
            extrasaction="ignore"
        )

        writer.writeheader()
        writer.writerows(rows)


def get_processed_drop_keys(connection):
    """Get all successfully processed input drop identifiers."""
    rows = connection.execute(
        "SELECT drop_key FROM ingested_drops"
    ).fetchall()

    return {row["drop_key"] for row in rows}


def get_processed_lead_input_counts(processed_keys):
    """
    Count nonblank rows in processed lead CSV files.

    This supports historical databases that do not yet store
    lead ingestion row statistics.
    """
    total_rows = 0

    for workflow in ("motor_renewal", "policy_feedback"):
        for csv_path in DATA_DIR.glob(
            f"drop_*/leads/{workflow}/*.csv"
        ):
            drop_key = f"{workflow}:{csv_path.stem}"

            if drop_key not in processed_keys:
                continue

            with csv_path.open(
                "r",
                encoding="utf-8-sig",
                newline=""
            ) as file:
                reader = csv.DictReader(file)

                for row in reader:
                    if any(
                        value is not None and str(value).strip()
                        for value in row.values()
                    ):
                        total_rows += 1

    return total_rows


def get_processed_event_line_count(processed_keys):
    """Count nonempty lines in successfully processed JSONL files."""
    total = 0

    for event_path in DATA_DIR.glob("drop_*/events/*.jsonl"):
        relative_path = event_path.resolve().relative_to(
            DATA_DIR.resolve()
        ).as_posix()

        drop_key = f"events:{relative_path}"

        if drop_key not in processed_keys:
            continue

        with event_path.open("r", encoding="utf-8") as file:
            total += sum(1 for line in file if line.strip())

    return total


def determine_bucket(calls):
    """Determine the lead bucket using the required priority."""
    if not calls:
        return "yet_to_reach_out"

    if any(call["is_terminal"] for call in calls):
        return "completed"

    if all(call["telephony_failed"] for call in calls):
        return "in_progress_telephony_failed"

    return "in_progress_dialed"


def get_effective_disposition(call_events, disposition_metadata, workflow):
    """
    Get effective disposition for one call.

    Latest override takes priority over all disposition.set events.
    If there is no override, use the latest disposition.set event.
    """
    overrides = [
        event for event in call_events
        if event["event_type"] == "disposition.override"
    ]

    sets = [
        event for event in call_events
        if event["event_type"] == "disposition.set"
    ]

    candidates = overrides if overrides else sets

    if not candidates:
        return None, False, False

    candidates.sort(
        key=lambda event: (
            parse_timestamp(event["occurred_at"]),
            event["id"]
        )
    )

    selected = candidates[-1]

    try:
        payload = json.loads(selected["payload_json"] or "{}")
    except json.JSONDecodeError:
        return None, False, False

    code = payload.get("disposition_code")

    if not isinstance(code, str):
        return None, False, False

    code = code.strip().lower()
    definition = disposition_metadata.get(workflow, {}).get(code)

    # Ignore unknown disposition codes, including legacy stored events.
    if definition is None:
        return None, False, False

    return (
        code,
        definition["is_terminal"],
        definition["is_success"]
    )


def generate_reports():
    """Generate all five required Assignment A reports."""

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    disposition_metadata = load_disposition_metadata()
    security = PIISecurity()

    connection = get_connection()

    try:
        processed_keys = get_processed_drop_keys(connection)

        # ---------------------------------------------------------
        # 1. Load leads
        # ---------------------------------------------------------
        lead_rows = connection.execute(
            """
            SELECT *
            FROM leads
            ORDER BY workflow_id, external_ref
            """
        ).fetchall()

        leads = {
            row["id"]: dict(row)
            for row in lead_rows
        }

        # ---------------------------------------------------------
        # 2. Load linked events only
        # ---------------------------------------------------------
        event_rows = connection.execute(
            """
            SELECT *
            FROM events
            WHERE lead_id IS NOT NULL
            ORDER BY occurred_at, id
            """
        ).fetchall()

        # Group events by lead and call.
        grouped_events = defaultdict(list)

        for event in event_rows:
            key = (
                event["lead_id"],
                event["workflow_id"],
                event["call_id"]
            )
            grouped_events[key].append(dict(event))

        # ---------------------------------------------------------
        # 3. Derive call-level facts
        # ---------------------------------------------------------
        calls_by_lead = defaultdict(list)
        calls_by_workflow_date = defaultdict(list)

        for (lead_id, workflow, call_id), events in grouped_events.items():

            initiated_events = [
                event for event in events
                if event["event_type"] == "call.initiated"
            ]

            # Calls without call.initiated are not counted.
            if not initiated_events:
                continue

            initiated_events.sort(
                key=lambda event: (
                    parse_timestamp(event["occurred_at"]),
                    event["id"]
                )
            )

            initiated = initiated_events[0]
            initiated_ist = to_ist(initiated["occurred_at"])

            connected = any(
                event["event_type"] == "call.connected"
                for event in events
            )

            telephony_failed = any(
                event["event_type"] == "call.telephony_failed"
                for event in events
            )

            code, terminal, success = get_effective_disposition(
                events,
                disposition_metadata,
                workflow
            )

            call = {
                "lead_id": lead_id,
                "workflow_id": workflow,
                "call_id": call_id,
                "initiated_at": initiated["occurred_at"],
                "initiated_ist": initiated_ist,
                "connected": connected,
                "telephony_failed": telephony_failed,
                "disposition": code,
                "is_terminal": terminal,
                "is_success": success,
            }

            calls_by_lead[lead_id].append(call)

            date_key = (
                workflow,
                initiated_ist.date().isoformat()
            )

            calls_by_workflow_date[date_key].append(call)

        # ---------------------------------------------------------
        # 4. Derive lead-level facts and buckets
        # ---------------------------------------------------------
        lead_facts = {}

        for lead_id, lead in leads.items():

            calls = calls_by_lead.get(lead_id, [])

            calls.sort(
                key=lambda call: (
                    parse_timestamp(call["initiated_at"]),
                    call["call_id"]
                )
            )

            total_calls = len(calls)

            connected_calls = sum(
                1 for call in calls if call["connected"]
            )

            bucket = determine_bucket(calls)

            latest_call = calls[-1] if calls else None

            # Current disposition is from the most recent call
            # that has an effective disposition.
            calls_with_disposition = [
                call for call in calls
                if call["disposition"] is not None
            ]

            current_disposition = (
                calls_with_disposition[-1]["disposition"]
                if calls_with_disposition
                else ""
            )

            ever_success = any(
                call["is_success"]
                for call in calls
            )

            phone = ""

            try:
                fields = json.loads(lead["fields_json"])
                encrypted_phone = fields.get("phone")

                if encrypted_phone:
                    canonical_phone = security.decrypt(encrypted_phone)
                    phone = "+91******" + canonical_phone[-4:]

            except (ValueError, TypeError, KeyError):
                phone = ""

            lead_facts[lead_id] = {
                "workflow_id": lead["workflow_id"],
                "external_ref": lead["external_ref"] or "",
                "batch_id": lead["batch_id"],
                "phone_masked": phone,
                "bucket": bucket,
                "total_calls": total_calls,
                "connected_calls": connected_calls,
                "last_call_at": (
                    latest_call["initiated_ist"].isoformat()
                    if latest_call else ""
                ),
                "current_disposition": current_disposition,
                "ever_success": ever_success,
                "calls": calls,
            }

        # ---------------------------------------------------------
        # 5. batch_summary.csv
        # ---------------------------------------------------------
        batch_groups = defaultdict(list)

        for fact in lead_facts.values():
            key = (
                fact["workflow_id"],
                fact["batch_id"]
            )
            batch_groups[key].append(fact)

        batch_rows = []

        for (workflow, batch_id), facts in batch_groups.items():

            batch_rows.append({
                "workflow_id": workflow,
                "batch_id": batch_id,
                "total_leads": len(facts),
                "yet_to_reach_out": sum(
                    fact["bucket"] == "yet_to_reach_out"
                    for fact in facts
                ),
                "in_progress_telephony_failed": sum(
                    fact["bucket"] == "in_progress_telephony_failed"
                    for fact in facts
                ),
                "in_progress_dialed": sum(
                    fact["bucket"] == "in_progress_dialed"
                    for fact in facts
                ),
                "completed": sum(
                    fact["bucket"] == "completed"
                    for fact in facts
                ),
            })

        batch_rows.sort(
            key=lambda row: (
                row["workflow_id"],
                row["batch_id"]
            )
        )

        write_csv(
            REPORT_DIR / "batch_summary.csv",
            [
                "workflow_id",
                "batch_id",
                "total_leads",
                "yet_to_reach_out",
                "in_progress_telephony_failed",
                "in_progress_dialed",
                "completed",
            ],
            batch_rows
        )

        # ---------------------------------------------------------
        # 6. daily_overview.csv
        # ---------------------------------------------------------
        daily_rows = []

        for (workflow, date), calls in sorted(
            calls_by_workflow_date.items()
        ):

            total_calls = len(calls)

            connected_calls = sum(
                1 for call in calls if call["connected"]
            )

            successful_leads = {
                call["lead_id"]
                for call in calls
                if call["is_success"]
            }

            daily_rows.append({
                "workflow_id": workflow,
                "date": date,
                "total_calls": total_calls,
                "connected_calls": connected_calls,
                "connectivity_rate": (
                    f"{connected_calls / total_calls:.4f}"
                    if total_calls else "0.0000"
                ),
                "success_leads": len(successful_leads),
            })

        write_csv(
            REPORT_DIR / "daily_overview.csv",
            [
                "workflow_id",
                "date",
                "total_calls",
                "connected_calls",
                "connectivity_rate",
                "success_leads",
            ],
            daily_rows
        )

        # ---------------------------------------------------------
        # 7. lead_report.csv
        # ---------------------------------------------------------
        lead_report_rows = []

        for lead_id, fact in lead_facts.items():

            lead_report_rows.append({
                "workflow_id": fact["workflow_id"],
                "external_ref": fact["external_ref"],
                "batch_id": fact["batch_id"],
                "phone_masked": fact["phone_masked"],
                "bucket": fact["bucket"],
                "total_calls": fact["total_calls"],
                "connected_calls": fact["connected_calls"],
                "last_call_at": fact["last_call_at"],
                "current_disposition": fact["current_disposition"],
                "ever_success": str(fact["ever_success"]).lower(),
            })

        lead_report_rows.sort(
            key=lambda row: (
                row["workflow_id"],
                row["external_ref"]
            )
        )

        write_csv(
            REPORT_DIR / "lead_report.csv",
            [
                "workflow_id",
                "external_ref",
                "batch_id",
                "phone_masked",
                "bucket",
                "total_calls",
                "connected_calls",
                "last_call_at",
                "current_disposition",
                "ever_success",
            ],
            lead_report_rows
        )

        # ---------------------------------------------------------
        # 8. rejections.csv
        # ---------------------------------------------------------
        rejection_rows = connection.execute(
            """
            SELECT workflow_id, batch_id, row_number, reason
            FROM rejections
            ORDER BY workflow_id, batch_id, row_number
            """
        ).fetchall()

        write_csv(
            REPORT_DIR / "rejections.csv",
            [
                "workflow_id",
                "batch_id",
                "row_number",
                "reason",
            ],
            [dict(row) for row in rejection_rows]
        )

        # ---------------------------------------------------------
        # 9. data_quality.json
        # ---------------------------------------------------------
        lead_rows_total = get_processed_lead_input_counts(
            processed_keys
        )

        lead_rows_rejected = connection.execute(
            "SELECT COUNT(*) FROM rejections"
        ).fetchone()[0]

        unique_leads = len(leads)

        duplicate_lead_rows_merged = max(
            0,
            lead_rows_total - lead_rows_rejected - unique_leads
        )

        rejections_by_reason = {}

        reason_rows = connection.execute(
            """
            SELECT reason, COUNT(*) AS count
            FROM rejections
            GROUP BY reason
            ORDER BY reason
            """
        ).fetchall()

        for row in reason_rows:
            rejections_by_reason[row["reason"]] = row["count"]

        field_warnings = connection.execute(
            "SELECT COUNT(*) FROM warnings"
        ).fetchone()[0]

        event_stats = connection.execute(
            """
            SELECT
                COALESCE(SUM(malformed_json), 0) AS malformed_json,
                COALESCE(SUM(missing_event_id), 0) AS missing_event_id,
                COALESCE(SUM(duplicate_event_id), 0) AS duplicate_event_id,
                COALESCE(SUM(unknown_disposition), 0) AS unknown_disposition
            FROM event_ingestion_stats
            """
        ).fetchone()

        events_total = get_processed_event_line_count(
            processed_keys
        )

        orphan_events = connection.execute(
            """
            SELECT COUNT(*)
            FROM events
            WHERE lead_id IS NULL
            """
        ).fetchone()[0]

        data_quality = {
            "lead_rows_total": lead_rows_total,
            "lead_rows_rejected": lead_rows_rejected,
            "rejections_by_reason": rejections_by_reason,
            "duplicate_lead_rows_merged": duplicate_lead_rows_merged,
            "field_warnings": field_warnings,
            "events_total": events_total,
            "malformed_events": (
                event_stats["malformed_json"]
                + event_stats["missing_event_id"]
            ),
            "duplicate_events_dropped": event_stats["duplicate_event_id"],
            "orphan_events": orphan_events,
            "unknown_disposition_events": event_stats["unknown_disposition"],
        }

        with (REPORT_DIR / "data_quality.json").open(
            "w",
            encoding="utf-8"
        ) as file:
            json.dump(
                data_quality,
                file,
                indent=4
            )

        return {
            "status": "success",
            "reports_directory": str(REPORT_DIR),
            "lead_count": len(leads),
            "call_count": sum(
                len(calls) for calls in calls_by_lead.values()
            ),
            "reports": [
                "batch_summary.csv",
                "daily_overview.csv",
                "lead_report.csv",
                "rejections.csv",
                "data_quality.json",
            ],
            "data_quality": data_quality,
        }

    finally:
        connection.close()


if __name__ == "__main__":
    result = generate_reports()
    print(json.dumps(result, indent=4))
