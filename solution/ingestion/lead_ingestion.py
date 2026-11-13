
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from solution.database.connection import get_connection
from solution.ingestion.event_ingestion import reconcile_orphan_events
from solution.services.encryption import PIISecurity
from solution.utils.normalization import (
    clean_text,
    normalize_phone,
    normalize_date,
    normalize_decimal,
    normalize_enum,
)
from solution.utils.schema_loader import load_workflow_schema


def normalize_header(value):
    """Normalize headers according to the assignment specification."""
    return re.sub(r"[_\s]+", " ", value.strip().lower())


def build_header_map(csv_headers, schema_fields):
    """Map CSV headers to canonical schema field names."""
    available = {
        normalize_header(header): header
        for header in csv_headers
    }

    mapping = {}

    for field in schema_fields:
        candidates = [field["name"]] + field.get("aliases", [])

        for candidate in candidates:
            key = normalize_header(candidate)

            if key in available:
                mapping[field["name"]] = available[key]
                break

    return mapping


def normalize_field_value(value, field):
    """Normalize a field according to its declared schema type."""
    value = clean_text(value)

    if value is None:
        return None

    field_type = field.get("type")

    if field_type == "phone":
        result = normalize_phone(value)

        if result is None:
            raise ValueError("invalid_phone")

        return result

    if field_type == "date":
        return normalize_date(value)

    if field_type == "decimal":
        return normalize_decimal(value)

    if field_type == "enum":
        return normalize_enum(value, field.get("values", []))

    return value


def protect_pii(fields, schema_fields, security):
    """Encrypt all fields marked as PII in the workflow schema."""
    pii_names = {
        field["name"]
        for field in schema_fields
        if field.get("pii", False)
    }

    return {
        name: (
            security.encrypt(value)
            if value is not None and name in pii_names
            else value
        )
        for name, value in fields.items()
    }


def unprotect_fields(fields, schema_fields, security):
    """Decrypt PII fields when merging an existing lead."""
    pii_names = {
        field["name"]
        for field in schema_fields
        if field.get("pii", False)
    }

    result = dict(fields)

    for name in pii_names:
        if result.get(name) is not None:
            result[name] = security.decrypt(result[name])

    return result


def apply_defaults(fields, schema_fields):
    """Apply defaults to fields that remain null after merging."""
    result = dict(fields)

    for field in schema_fields:
        name = field["name"]

        if result.get(name) is None and "default" in field:
            result[name] = field["default"]

    return result


def ingest_lead_batch(csv_path, workflow_id, security=None):
    """
    Ingest a single CSV batch.

    Features:
    - Schema-based header mapping and validation.
    - Indian phone normalization.
    - First-failure rejection reasons.
    - Optional field warnings.
    - Duplicate merging using workflow_id and phone_hash.
    - PII encryption.
    - Transactional and idempotent ingestion.
    - Automatic orphan event reconciliation.
    """

    csv_path = Path(csv_path)

    if not csv_path.is_file():
        raise FileNotFoundError(csv_path)

    security = security or PIISecurity()

    schema = load_workflow_schema(workflow_id)
    schema_fields = schema["fields"]

    batch_id = csv_path.stem
    drop_key = f"{workflow_id}:{batch_id}"

    now = datetime.now(timezone.utc).isoformat()

    accepted = 0
    merged = 0
    rejected = 0
    warnings = []

    with csv_path.open(
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as file:

        reader = csv.DictReader(file)

        if not reader.fieldnames:
            raise ValueError(f"CSV has no headers: {csv_path}")

        header_map = build_header_map(
            reader.fieldnames,
            schema_fields
        )

        connection = get_connection()

        try:
            connection.execute("BEGIN IMMEDIATE")

            # Idempotency check.
            existing_batch = connection.execute(
                """
                SELECT id
                FROM ingested_drops
                WHERE drop_key = ?
                """,
                (drop_key,)
            ).fetchone()

            if existing_batch:
                connection.rollback()

                return {
                    "workflow_id": workflow_id,
                    "batch_id": batch_id,
                    "status": "already_processed",
                    "accepted": 0,
                    "merged": 0,
                    "rejected": 0,
                    "warnings": [],
                    "reconciled_events": 0,
                }

            # Row numbers count non-blank rows only, starting at 1.
            row_number = 0

            for row in reader:

                # Skip blank rows without incrementing row_number.
                if not any(clean_text(v) for v in row.values()):
                    continue

                row_number += 1

                normalized_fields = {}
                rejection_reason = None
                row_warnings = []

                # Validate fields in schema order.
                for field in schema_fields:

                    name = field["name"]
                    source_header = header_map.get(name)

                    raw_value = (
                        row.get(source_header)
                        if source_header is not None
                        else None
                    )

                    try:
                        value = normalize_field_value(
                            raw_value,
                            field
                        )

                    except ValueError as exc:

                        reason = str(exc)

                        if field.get("required", False):

                            if field.get("type") == "phone":
                                rejection_reason = "invalid_phone"
                            else:
                                rejection_reason = f"invalid_{name}"

                            break

                        value = None

                        row_warnings.append(
                            f"{name}:{reason}"
                        )

                    # Required field missing.
                    if value is None and field.get("required", False):
                        rejection_reason = (
                            f"missing_required:{name}"
                        )
                        break

                    normalized_fields[name] = value

                # Rejected rows are not inserted as leads.
                if rejection_reason:

                    connection.execute(
                        """
                        INSERT INTO rejections (
                            workflow_id,
                            batch_id,
                            row_number,
                            reason
                        )
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            workflow_id,
                            batch_id,
                            row_number,
                            rejection_reason
                        )
                    )

                    rejected += 1
                    continue

                # Canonical phone and deterministic HMAC identity.
                phone = normalized_fields["phone"]
                phone_hash = security.phone_hash(phone)

                existing = connection.execute(
                    """
                    SELECT id, fields_json
                    FROM leads
                    WHERE workflow_id = ?
                      AND phone_hash = ?
                    """,
                    (
                        workflow_id,
                        phone_hash
                    )
                ).fetchone()

                if existing:

                    old_fields = json.loads(
                        existing["fields_json"]
                    )

                    old_fields = unprotect_fields(
                        old_fields,
                        schema_fields,
                        security
                    )

                    # Last non-null value wins.
                    for name, value in normalized_fields.items():

                        if value is not None:
                            old_fields[name] = value

                    merged_fields = apply_defaults(
                        old_fields,
                        schema_fields
                    )

                    protected = protect_pii(
                        merged_fields,
                        schema_fields,
                        security
                    )

                    external_ref = next(
                        (
                            merged_fields.get(field["name"])
                            for field in schema_fields
                            if field.get("reference", False)
                        ),
                        None
                    )

                    connection.execute(
                        """
                        UPDATE leads
                        SET external_ref = ?,
                            fields_json = ?,
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            external_ref,
                            json.dumps(protected),
                            now,
                            existing["id"]
                        )
                    )

                    # Original batch_id is deliberately preserved.
                    merged += 1

                else:

                    merged_fields = apply_defaults(
                        normalized_fields,
                        schema_fields
                    )

                    protected = protect_pii(
                        merged_fields,
                        schema_fields,
                        security
                    )

                    external_ref = next(
                        (
                            merged_fields.get(field["name"])
                            for field in schema_fields
                            if field.get("reference", False)
                        ),
                        None
                    )

                    connection.execute(
                        """
                        INSERT INTO leads (
                            workflow_id,
                            external_ref,
                            batch_id,
                            phone_hash,
                            fields_json,
                            created_at,
                            updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            workflow_id,
                            external_ref,
                            batch_id,
                            phone_hash,
                            json.dumps(protected),
                            now,
                            now
                        )
                    )

                    accepted += 1

                # Persist optional field warnings only for valid rows.
                for warning in row_warnings:

                    warning_record = {
                        "batch_id": batch_id,
                        "row_number": row_number,
                        "warning": warning
                    }

                    warnings.append(warning_record)

                    connection.execute(
                        """
                        INSERT INTO warnings (
                            workflow_id,
                            batch_id,
                            row_number,
                            warning
                        )
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            workflow_id,
                            batch_id,
                            row_number,
                            warning
                        )
                    )

            # Mark batch processed after successful processing.
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

    # Reconcile orphan events after the lead transaction commits.
    reconciled_events = reconcile_orphan_events()

    return {
        "workflow_id": workflow_id,
        "batch_id": batch_id,
        "status": "processed",
        "accepted": accepted,
        "merged": merged,
        "rejected": rejected,
        "warnings": warnings,
        "reconciled_events": reconciled_events,
    }
