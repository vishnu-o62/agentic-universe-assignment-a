# Agentic Universe – Interaction Ledger and Reporting Pipeline

## Overview

This solution implements an interaction ledger and reporting pipeline for motor renewal and policy feedback workflows.

The pipeline ingests lead CSV batches and event JSONL files, normalizes and validates input data, protects phone numbers using encryption and deterministic HMAC-based lookup, reconciles duplicate leads and orphan events, and generates the required CSV and JSON reports.

## Requirements

- Python 3.10 or later
- pip
- Windows, Linux, or macOS

## Setup

From the repository root, create and activate a virtual environment.

**Windows PowerShell**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Generate input data

Generate the small sample dataset using the provided data generator:

```powershell
python assignment-a-data/tools/generate_data.py --seed 42 --scale small --out data
```

The generated input data is read from the `data` directory.

## Run the pipeline

From the repository root:

```powershell
python -m solution.run_pipeline
```

The pipeline initializes the SQLite database, processes lead batches and event files in drop order, reconciles orphan events, and generates the reports.

By default:
- SQLite database: `data/ledger.sqlite3`
- Persistent encryption key: `data/.pii.key`
- Reports: `reports/`

The database and encryption key are persistent. Keep the key safe because it is required to decrypt stored phone numbers. Do not delete or replace it while retaining the associated database.

Optional environment variables can be used to select separate runtime locations:

- `AU_DATABASE_PATH`
- `AU_KEY_PATH`
- `AU_REPORT_DIR`

## Generated reports

The pipeline generates five output files:

| File | Description |
|---|---|
| `batch_summary.csv` | Lead counts grouped by workflow and batch, including processing buckets |
| `daily_overview.csv` | Daily call counts, connected calls, connectivity rate, and successful leads |
| `lead_report.csv` | Per-lead call activity, current disposition, bucket, and success status |
| `rejections.csv` | Rejected lead rows and their validation reasons |
| `data_quality.json` | Lead, event, duplicate, rejection, warning, and orphan-event statistics |

Reports are written to the configured report directory.

## Run tests

Run the test suite from the repository root:

```powershell
python -m pytest tests -q
```

To check Python compilation:

```powershell
python -m compileall -q solution
```

## Processing and data-handling notes

- Lead batches and event files are processed in drop order.
- Repeated ingestion of an already processed batch or event file is skipped.
- Duplicate leads are identified using workflow and normalized phone identity.
- Phone numbers are encrypted at rest, with a separate deterministic HMAC lookup value.
- Events that cannot initially be linked to a lead are retained for later reconciliation.
- Report timestamps are represented in Indian Standard Time (IST).
- Input data and generated runtime files should not be committed to version control.