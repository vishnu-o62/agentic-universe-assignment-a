import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Original generated input dataset remains unchanged.
DATA_DIR = BASE_DIR / "data"

# These paths can be redirected for isolated testing.
DATABASE_PATH = Path(
    os.getenv("AU_DATABASE_PATH", str(DATA_DIR / "ledger.sqlite3"))
)
KEY_PATH = Path(
    os.getenv("AU_KEY_PATH", str(DATA_DIR / ".pii.key"))
)

SCHEMA_DIR = BASE_DIR / "assignment-a-data" / "schemas"

WORKFLOW_SCHEMAS = {
    "motor_renewal": SCHEMA_DIR / "motor_renewal.json",
    "policy_feedback": SCHEMA_DIR / "policy_feedback.json",
}

DISPOSITIONS_PATH = SCHEMA_DIR / "dispositions.csv"

REPORT_DIR = Path(
    os.getenv("AU_REPORT_DIR", str(BASE_DIR / "reports"))
)

PHONE_HMAC_CONTEXT = b"agentic-universe-phone-lookup-v1"
