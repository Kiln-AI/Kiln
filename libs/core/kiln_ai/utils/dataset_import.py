import csv
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Protocol

from pydantic import BaseModel, Field, ValidationError, field_validator

from kiln_ai.datamodel import DataSource, DataSourceType, Task, TaskOutput, TaskRun

logger = logging.getLogger(__name__)


class DatasetImportFormat(str, Enum):
    """
    The format of the dataset to import.
    """

    CSV = "csv"


class Importer(Protocol):
    """Protocol for dataset importers"""

    def __call__(
        self,
        task: Task,
        dataset_path: str,
        dataset_name: str,
    ) -> int: ...


class CSVRowSchema(BaseModel):
    """Schema for validating rows in a CSV file."""

    input: str = Field(description="The input to the model")
    output: str = Field(description="The output of the model")
    reasoning: str | None = Field(
        description="The reasoning of the model (optional)",
        default=None,
    )
    chain_of_thought: str | None = Field(
        description="The chain of thought of the model (optional)",
        default=None,
    )
    tags: list[str] = Field(
        default_factory=list,
        description="The tags of the run (optional)",
    )


def generate_import_tags(session_id: str) -> list[str]:
    return [
        "imported",
        f"imported_{session_id}",
    ]


class KilnInvalidImportFormat(Exception):
    """Raised when the import format is invalid"""

    def __init__(self, message: str, row_number: int | None = None):
        self.row_number = row_number
        if row_number is not None:
            message = f"Error in row {row_number}: {message}"
        super().__init__(message)


def format_validation_error(e: ValidationError) -> str:
    """Convert a Pydantic validation error into a human-readable message."""
    error_messages = []
    for error in e.errors():
        location = " -> ".join(str(loc) for loc in error["loc"])
        message = error["msg"]
        error_messages.append(f"- {location}: {message}")

    return "Validation failed:\n" + "\n".join(error_messages)


def deserialize_tags(tags_serialized: str | None) -> list[str]:
    """Deserialize tags from a comma-separated string to a list of strings."""
    if tags_serialized:
        return [tag.strip() for tag in tags_serialized.split(",") if tag.strip()]
    return []


def without_none_values(d: dict) -> dict:
    """Return a copy of the dictionary with all None values removed."""
    return {k: v for k, v in d.items() if v is not None}


def create_task_run_from_csv_row(
    task: Task,
    row: dict[str, str],
    dataset_name: str,
    session_id: str,
) -> TaskRun:
    """Validate and create a TaskRun from a CSV row, without saving to file"""

    # first we validate the row from the CSV file
    validated_row = CSVRowSchema.model_validate(
        {
            **row,
            "tags": deserialize_tags(row.get("tags")),
        }
    )

    tags = generate_import_tags(session_id)
    if validated_row.tags:
        tags.extend(validated_row.tags)

    # note that we don't persist the run yet, we just create and validate it
    # this instantiation may raise pydantic validation errors
    run = TaskRun(
        parent=task,
        input=validated_row.input,
        input_source=DataSource(
            type=DataSourceType.file_import,
            properties={
                "file_name": dataset_name,
            },
        ),
        output=TaskOutput(
            output=validated_row.output,
            source=DataSource(
                type=DataSourceType.file_import,
                properties={
                    "file_name": dataset_name,
                },
            ),
        ),
        intermediate_outputs=without_none_values(
            {
                "reasoning": validated_row.reasoning,
                "chain_of_thought": validated_row.chain_of_thought,
            }
        )
        or None,
        tags=tags,
    )

    return run


def import_csv(task: Task, dataset_path: str, dataset_name: str) -> int:
    """Import a CSV dataset.

    All rows are validated before any are persisted to files to avoid partial imports."""

    session_id = str(int(time.time()))

    required_headers = {"input", "output"}  # minimum required headers
    optional_headers = {"reasoning", "tags", "chain_of_thought"}  # optional headers

    rows: list[TaskRun] = []
    with open(dataset_path, "r", newline="") as csvfile:
        reader = csv.DictReader(csvfile)

        # Check if we have headers
        if not reader.fieldnames:
            raise KilnInvalidImportFormat(
                "CSV file appears to be empty or missing headers"
            )

        # Check for required headers
        actual_headers = set(reader.fieldnames)
        missing_headers = required_headers - actual_headers
        if missing_headers:
            raise KilnInvalidImportFormat(
                f"Missing required headers: {', '.join(missing_headers)}. "
                f"Required headers are: {', '.join(required_headers)}"
            )

        # Warn about unknown headers (not required or optional)
        unknown_headers = actual_headers - (required_headers | optional_headers)
        if unknown_headers:
            logger.warning(
                f"Unknown headers in CSV file will be ignored: {', '.join(unknown_headers)}"
            )

        # enumeration starts at 2 because row 1 is headers
        for row_number, row in enumerate(reader, start=2):
            try:
                run = create_task_run_from_csv_row(
                    task=task,
                    row=row,
                    dataset_name=dataset_name,
                    session_id=session_id,
                )
            except ValidationError as e:
                logger.warning(f"Invalid row {row_number}: {row}", exc_info=True)
                human_readable = format_validation_error(e)
                raise KilnInvalidImportFormat(
                    human_readable,
                    row_number=row_number,
                ) from e
            rows.append(run)

    # now that we know all rows are valid, we can save them
    for run in rows:
        run.save_to_file()

    return len(rows)


DATASET_IMPORTERS: Dict[DatasetImportFormat, Importer] = {
    DatasetImportFormat.CSV: import_csv,
}


@dataclass
class ImportConfig:
    """Configuration for importing a dataset"""

    dataset_type: DatasetImportFormat
    dataset_path: str
    dataset_name: str


class DatasetFileImporter:
    """Import a dataset from a file"""

    def __init__(self, task: Task, config: ImportConfig):
        self.task = task
        self.dataset_type = config.dataset_type
        self.dataset_path = config.dataset_path
        self.dataset_name = config.dataset_name

    def create_runs_from_file(self) -> int:
        fn = DATASET_IMPORTERS[self.dataset_type]
        return fn(self.task, self.dataset_path, self.dataset_name)
