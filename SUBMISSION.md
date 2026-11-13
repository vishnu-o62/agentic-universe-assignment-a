# Submission – Assignment A: Interaction Ledger and Reporting Pipeline

## Repository

GitHub repository: https://github.com/AryamannNingombam/sde-assignment-junior-2026

**Repository visibility:** Private

**Reviewer access:** Add the reviewer handles or email addresses specified in the assignment instructions before submission.

## Implementation Summary

Implemented an interaction ledger and reporting pipeline for the `motor_renewal` and `policy_feedback` workflows.

The solution includes:

- Schema-driven lead ingestion and field normalization.
- Lead validation, rejection tracking, and optional-field warnings.
- Duplicate lead detection and non-null field merging.
- Phone-number encryption and deterministic HMAC-based identity lookup.
- Event ingestion with malformed, duplicate, orphan, and unknown-disposition handling.
- Cross-drop orphan-event reconciliation.
- Effective disposition calculation and lead bucket classification.
- Generation of the five required CSV and JSON reports.

## Technical Stack

- Python
- SQLite
- Cryptography (Fernet encryption and HMAC-SHA256)
- CSV and JSON processing
- pytest

## Execution

Install dependencies:

```bash
pip install -r requirements.txt
```

Generate the sample dataset:

```bash
python assignment-a-data/tools/generate_data.py --seed 42 --scale small --out data
```

Run the pipeline:

```bash
python -m solution.run_pipeline
```

Run tests:

```bash
python -m pytest tests -q
```

## Validation Results

Fresh isolated dataset execution:

- Unique leads processed: 1,892
- Calls counted: 2,536
- Rejected lead rows: 108
- Merged duplicate lead rows: 57
- Field warnings: 65
- Malformed events: 8
- Duplicate events dropped: 235
- Unknown disposition events: 21
- Final orphan events: 461

Test suite: **45 tests passed**.

Additional manual validation confirmed:

- Repeated pipeline execution did not change database record counts.
- All five required report files were generated.
- CSV headers matched the required output contract.
- Report row counts and call totals reconciled.
- Phone masking, sorting, four-decimal connectivity rates, and IST timestamps passed validation.

## Design Decisions

- SQLite is used for persistent storage and ingestion idempotency.
- Phone numbers are encrypted at rest; HMAC values support deterministic identity matching without storing plaintext phone numbers as lookup keys.
- Lead batches and event files are processed in drop order to support cross-drop event reconciliation.
- The first valid lead batch establishes the lead's original batch identifier; later duplicates merge non-null values.
- Reports are generated from the stored ledger and processed input files.

## Limitations

- The pipeline expects the provided input directory structure and schema files.
- The encryption key must be retained to decrypt stored phone numbers.
- Data-quality input-line totals are derived from the processed source files, so those files should remain available when regenerating reports.

## Submission Checklist

- [ ] Confirm the GitHub repository is private.
- [ ] Grant reviewer access using the handles or email addresses in the assignment instructions.
- [ ] Confirm source code, tests, and documentation are committed.
- [ ] Confirm generated databases, encryption keys, input data, virtual environments, and reports are excluded from Git.
- [ ] Submit the repository URL through the assignment submission form.