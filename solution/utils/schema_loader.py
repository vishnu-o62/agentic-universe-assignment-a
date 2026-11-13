
import json

from solution.config import WORKFLOW_SCHEMAS


def load_workflow_schema(workflow_id):
    schema_path = WORKFLOW_SCHEMAS.get(workflow_id)

    if schema_path is None:
        raise ValueError(
            f"Unknown workflow: {workflow_id}"
        )

    with schema_path.open("r", encoding="utf-8") as file:
        schema = json.load(file)

    return schema
