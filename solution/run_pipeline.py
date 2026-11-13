from solution.config import DATA_DIR
from solution.database.connection import initialize_database
from solution.ingestion.lead_ingestion import ingest_lead_batch
from solution.ingestion.event_ingestion import ingest_event_file
from solution.reporting.report_generator import generate_reports
from solution.services.encryption import PIISecurity


def main():
    print("=" * 60)
    print("AGENTIC UNIVERSE - INTERACTION LEDGER PIPELINE")
    print("=" * 60)

    initialize_database()
    security = PIISecurity()

    drop_dirs = sorted(
        path for path in DATA_DIR.glob("drop_*") if path.is_dir()
    )

    for drop_dir in drop_dirs:
        print(f"\nProcessing {drop_dir.name}")

        # Process this drop's lead batches in filename order.
        for workflow in ("motor_renewal", "policy_feedback"):
            lead_dir = drop_dir / "leads" / workflow

            if lead_dir.exists():
                for csv_file in sorted(lead_dir.glob("*.csv")):
                    result = ingest_lead_batch(
                        csv_file, workflow, security
                    )
                    print("Lead:", csv_file.name, result)

        # Process events before moving to the next drop.
        event_dir = drop_dir / "events"

        if event_dir.exists():
            for event_file in sorted(event_dir.glob("*.jsonl")):
                result = ingest_event_file(event_file, security)
                print("Events:", event_file.name, result)

    print("\nGenerating reports...")
    result = generate_reports()
    print(result)

    print("\nPipeline completed.")


if __name__ == "__main__":
    main()
