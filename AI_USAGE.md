# AI Usage Disclosure

## AI Tools Used

ChatGPT was used as an assistance tool during development of the Interaction Ledger and Reporting Pipeline.

## Areas Where AI Assistance Was Used

- Understanding and breaking down the assignment requirements.
- Discussing the ingestion architecture, processing order, and reporting logic.
- Suggesting implementation approaches for data normalization, validation, duplicate handling, event reconciliation, and report generation.
- Debugging Python implementation issues and interpreting command-line output.
- Suggesting unit tests and validation checks.
- Reviewing documentation and setup instructions.

## Human Contributions

The implementation was developed and validated through direct work in the local development environment. The developer:

- Created and organized the solution modules.
- Integrated the ingestion, database, security, and reporting components.
- Ran the data generator and pipeline locally.
- Executed the test suite and inspected the generated reports.
- Investigated errors and applied corrections.
- Verified repeat-run behavior and report consistency.
- Reviewed and edited the final documentation.

## Examples of AI-Assisted Iteration

1. A currency-normalization regular expression required correction to handle the rupee symbol reliably. The implementation was updated and tested.
2. The initial pipeline processing order was reviewed and adjusted so that each drop's lead files are processed before that drop's event files, preserving cross-drop orphan-event reconciliation.
3. Database and encryption-key paths were made configurable through environment variables to support isolated validation without modifying the existing runtime database.

## Verification

AI-generated suggestions were not treated as proof of correctness. The implementation was executed locally and checked using:

- `python -m pytest tests -q`
- `python -m compileall -q solution`
- Fresh isolated pipeline execution.
- Repeat-run idempotency verification.
- Generated report header, row-count, sorting, masking, timestamp, and total-count checks.

The final implementation and its reported results were reviewed against the assignment requirements by the developer.

## Declaration

AI assistance was used for guidance, debugging, testing suggestions, and documentation support. The developer remains responsible for the submitted implementation, its correctness, and the final deliverables.