
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from solution.config import DISPOSITIONS_PATH
from solution.database.connection import get_connection
from solution.services.encryption import PIISecurity
from solution.utils.normalization import normalize_phone


IST = ZoneInfo("Asia/Kolkata")


def normalize_event_timestamp(value):
    """
    Convert timestamps to UTC ISO format.
    Naive timestamps are interpreted as IST.
    """
    if not value:
        return None

    timestamp = str(value).strip()

    if timestamp.endswith("Z"):
        timestamp = timestamp[:-1] + "+00:00"

    parsed = datetime.fromisoformat(timestamp)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=IST)

    return parsed.astimezone(timezone.utc).isoformat()


def load_dispositions():
    """Load valid disposition codes for each workflow."""
    dispositions = {}

    with DISPOSITIONS_PATH.open(
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as file:
        reader = csv.DictReader(file)

        for row in reader:
            workflow_id = row["workflow_id"].strip()
            code = row["code"].strip().lower()

            dispositions.setdefault(workflow_id, set()).add(code)

    return dispositions


def reconcile_orphan_events():
    """
    Reconcile previously orphaned events.

    Normal events are linked using workflow_id and phone_hash.
    disposition.override events without a phone are linked using
    workflow_id and call_id to another linked event for that call.

    Returns the number of newly linked events.
    """
    connection = get_connection()

    try:
        connection.execute("BEGIN IMMEDIATE")

        linked_count = 0

        # 1. Link events using workflow and canonical phone hash.
        cursor = connection.execute(
            """
            UPDATE events
            SET lead_id = (
                SELECT leads.id
                FROM leads
                WHERE leads.workflow_id = events.workflow_id
                  AND leads.phone_hash = events.phone_hash
            )
            WHERE events.lead_id IS NULL
              AND events.phone_hash IS NOT NULL
              AND EXISTS (
                  SELECT 1
                  FROM leads
                  WHERE leads.workflow_id = events.workflow_id
                    AND leads.phone_hash = events.phone_hash
              )
            """
        )

        linked_count += max(cursor.rowcount, 0)

        # 2. Link overrides through another event belonging to the call.
        cursor = connection.execute(
            """
            UPDATE events
            SET lead_id = (
                SELECT related.lead_id
                FROM events AS related
                WHERE related.workflow_id = events.workflow_id
                  AND related.call_id = events.call_id
                  AND related.lead_id IS NOT NULL
                ORDER BY related.occurred_at ASC
                LIMIT 1
            )
            WHERE events.lead_id IS NULL
              AND events.event_type = 'disposition.override'
              AND EXISTS (
                  SELECT 1
                  FROM events AS related
                  WHERE related.workflow_id = events.workflow_id
                    AND related.call_id = events.call_id
                    AND related.lead_id IS NOT NULL
              )
            """
        )

        linked_count += max(cursor.rowcount, 0)

        connection.commit()
        return linked_count

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def ingest_event_file(event_file, security=None):
    """
    Ingest one JSONL event file.

    - Skips malformed JSON and records without event IDs.
    - Drops duplicate event IDs globally.
    - Retains valid orphan events for later reconciliation.
    - Links override events through call_id.
    - Ignores unknown disposition codes.
    - Encrypts phone numbers and uses HMAC lookup.
    - Records ingestion statistics transactionally.
    - Supports idempotent ingestion.
    """

    event_file = Path(event_file)

    if not event_file.is_file():
        raise FileNotFoundError(event_file)

    security = security or PIISecurity()
    dispositions = load_dispositions()

    relative_path = event_file.resolve().relative_to(
        Path("data").resolve()
    ).as_posix()

    drop_key = f"events:{relative_path}"

    events_total = 0
    malformed_json = 0
    missing_event_id = 0
    duplicate_event_id = 0
    unknown_disposition = 0
    inserted_events = 0
    orphan_events = 0

    now = datetime.now(timezone.utc).isoformat()
    connection = get_connection()

    try:
        connection.execute("BEGIN IMMEDIATE")

        already_processed = connection.execute(
            """
            SELECT id
            FROM ingested_drops
            WHERE drop_key = ?
            """,
            (drop_key,)
        ).fetchone()

        if already_processed:
            connection.rollback()

            return {
                "drop_key": drop_key,
                "status": "already_processed",
                "events_total": 0,
                "inserted_events": 0,
            }

        with event_file.open("r", encoding="utf-8") as file:

            for line in file:

                # Empty lines do not contribute to events_total.
                if not line.strip():
                    continue

                events_total += 1

                # 1. Malformed JSON.
                try:
                    event = json.loads(line)

                except json.JSONDecodeError:
                    malformed_json += 1
                    continue

                if not isinstance(event, dict):
                    malformed_json += 1
                    continue

                # Missing event_id is malformed.
                event_id = event.get("event_id")

                if not isinstance(event_id, str) or not event_id.strip():
                    missing_event_id += 1
                    continue

                event_id = event_id.strip()

                # 2. Duplicate event ID check before further processing.
                existing_event = connection.execute(
                    """
                    SELECT id
                    FROM events
                    WHERE event_id = ?
                    """,
                    (event_id,)
                ).fetchone()

                if existing_event:
                    duplicate_event_id += 1
                    continue

                workflow_id = event.get("workflow_id")
                event_type = event.get("event_type")
                call_id = event.get("call_id")
                occurred_at = event.get("occurred_at")
                phone = event.get("phone")
                payload = event.get("payload", {})

                if (
                    not isinstance(workflow_id, str)
                    or not workflow_id.strip()
                    or not isinstance(event_type, str)
                    or not event_type.strip()
                    or not isinstance(call_id, str)
                    or not call_id.strip()
                    or not isinstance(payload, dict)
                ):
                    malformed_json += 1
                    continue

                workflow_id = workflow_id.strip()
                event_type = event_type.strip()
                call_id = call_id.strip()

                try:
                    normalized_timestamp = normalize_event_timestamp(
                        occurred_at
                    )

                except (ValueError, TypeError):
                    malformed_json += 1
                    continue

                if normalized_timestamp is None:
                    malformed_json += 1
                    continue

                # Normalize and protect phone numbers.
                phone_hash = None
                phone_encrypted = None

                if phone is not None:
                    canonical_phone = normalize_phone(phone)

                    if canonical_phone is not None:
                        phone_hash = security.phone_hash(
                            canonical_phone
                        )

                        phone_encrypted = security.encrypt(
                            canonical_phone
                        )

                # 3. Determine whether the event can be linked.
                lead = None

                if phone_hash is not None:
                    lead = connection.execute(
                        """
                        SELECT id
                        FROM leads
                        WHERE workflow_id = ?
                          AND phone_hash = ?
                        """,
                        (
                            workflow_id,
                            phone_hash
                        )
                    ).fetchone()

                # Overrides may not contain a phone number.
                if (
                    lead is None
                    and event_type == "disposition.override"
                ):
                    lead = connection.execute(
                        """
                        SELECT lead_id AS id
                        FROM events
                        WHERE workflow_id = ?
                          AND call_id = ?
                          AND lead_id IS NOT NULL
                        ORDER BY occurred_at ASC
                        LIMIT 1
                        """,
                        (
                            workflow_id,
                            call_id
                        )
                    ).fetchone()

                lead_id = lead["id"] if lead else None

                # 4. Unknown disposition codes are counted and ignored.
                if event_type in (
                    "disposition.set",
                    "disposition.override"
                ):
                    code = payload.get("disposition_code")

                    valid_codes = dispositions.get(
                        workflow_id,
                        set()
                    )

                    if (
                        not isinstance(code, str)
                        or code.strip().lower() not in valid_codes
                    ):
                        unknown_disposition += 1
                        continue

                # 5. Store valid events, including orphans.
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO events (
                        event_id,
                        workflow_id,
                        event_type,
                        call_id,
                        occurred_at,
                        phone_hash,
                        phone_encrypted,
                        lead_id,
                        payload_json,
                        received_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id,
                        workflow_id,
                        event_type,
                        call_id,
                        normalized_timestamp,
                        phone_hash,
                        phone_encrypted,
                        lead_id,
                        json.dumps(payload),
                        now
                    )
                )

                if cursor.rowcount == 1:
                    inserted_events += 1

                    if lead_id is None:
                        orphan_events += 1

                else:
                    duplicate_event_id += 1

        # Persist statistics using the existing table structure.
        connection.execute(
            """
            INSERT INTO event_ingestion_stats (
                drop_key,
                malformed_json,
                missing_event_id,
                duplicate_event_id,
                unknown_disposition,
                inserted_events,
                orphan_events,
                ingested_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                drop_key,
                malformed_json,
                missing_event_id,
                duplicate_event_id,
                unknown_disposition,
                inserted_events,
                orphan_events,
                now
            )
        )

        # Mark file processed after successful ingestion.
        connection.execute(
            """
            INSERT INTO ingested_drops (
                drop_key,
                ingested_at
            )
            VALUES (?, ?)
            """,
            (
                drop_key,
                now
            )
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()

    # Reconcile events after the complete file has been processed.
    linked_events = reconcile_orphan_events()

    return {
        "drop_key": drop_key,
        "status": "processed",
        "events_total": events_total,
        "inserted_events": inserted_events,
        "malformed_json": malformed_json,
        "missing_event_id": missing_event_id,
        "duplicate_event_id": duplicate_event_id,
        "unknown_disposition": unknown_disposition,
        "orphan_events": orphan_events,
        "reconciled_events": linked_events,
    }
