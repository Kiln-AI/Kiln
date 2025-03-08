import csv
import json
import logging
import random
import string
import tempfile
from io import StringIO
from pathlib import Path

import pytest

from kiln_ai.adapters.dataset_import import (
    DatasetFileImporter,
    DatasetImportFormat,
    ImportConfig,
    KilnInvalidImportFormat,
)
from kiln_ai.datamodel import Project, Task

logger = logging.getLogger(__name__)


@pytest.fixture
def base_task(tmp_path) -> Task:
    project_path = Path.joinpath(
        Path(tempfile.gettempdir()),
        "".join(random.choices(string.ascii_letters + string.digits, k=10)),
        "project.kiln",
    )
    project_path.parent.mkdir()

    project = Project(name="TestProject", path=str(project_path))
    project.save_to_file()

    task = Task(
        name="Sentiment Classifier",
        parent=project,
        description="Classify the sentiment of a sentence",
        instruction="Classify the sentiment of a sentence",
        requirements=[],
    )
    task.save_to_file()
    return task


@pytest.fixture
def task_with_structured_output(base_task: Task):
    base_task.output_json_schema = json.dumps(
        {
            "type": "object",
            "properties": {
                "sentiment": {"type": "string"},
                "confidence": {"type": "number"},
            },
            "required": ["sentiment", "confidence"],
        }
    )
    base_task.save_to_file()
    return base_task


@pytest.fixture
def task_with_structured_input(base_task: Task):
    base_task.input_json_schema = json.dumps(
        {
            "type": "object",
            "properties": {
                "example_id": {"type": "integer"},
                "text": {"type": "string"},
            },
            "required": ["example_id", "text"],
        }
    )
    base_task.save_to_file()
    return base_task


@pytest.fixture
def task_with_intermediate_outputs(base_task: Task):
    for run in base_task.runs():
        run.intermediate_outputs = {"reasoning": "thinking output"}
    base_task.thinking_instruction = "thinking instructions"
    return base_task


def dict_to_csv_row(row: dict) -> str:
    """Convert a dictionary to a CSV row with proper escaping."""
    output = StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(row.values())
    return output.getvalue().rstrip("\n")


def dicts_to_file_as_csv(items: list[dict], file_name: str) -> str:
    """Write a list of dictionaries to a CSV file with escaping and a header.

    Returns the path to the file.
    """
    rows = [dict_to_csv_row(item) for item in items]
    header = ",".join(f'"{key}"' for key in items[0].keys())
    csv_data = header + "\n" + "\n".join(rows)

    file_path = Path.joinpath(Path(tempfile.gettempdir()), file_name)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(csv_data)

    return file_path


def compare_tags(actual_tags: list[str], expected_tags: list[str]):
    """Compare the tags of a run to a list of tags.

    Returns True if the run.tags contains all the tags in the list.
    """
    # the run.tags contain some extra default tags
    if expected_tags:
        tags_expected = expected_tags.split(",")
    else:
        tags_expected = []

    assert all(tag in actual_tags for tag in tags_expected)


def test_import_csv_plain_text(base_task: Task):
    row_data = [
        {
            "input": "This is my input",
            "output": "This is my output 啊",
            "tags": "t1,t2",
        },
        {
            "input": "This is my input 2",
            "output": "This is my output 2 啊",
            "tags": "t3,t4",
        },
        {
            "input": "This is my input 3",
            "output": "This is my output 3 啊",
            "tags": "t5",
        },
        {
            "input": "This is my input 4",
            "output": "This is my output 4 啊",
            "tags": "",
        },
    ]

    file_path = dicts_to_file_as_csv(row_data, "test.csv")

    importer = DatasetFileImporter(
        base_task,
        ImportConfig(
            dataset_type=DatasetImportFormat.CSV,
            dataset_path=file_path,
            dataset_name="test.csv",
        ),
    )

    importer.create_runs_from_file()

    assert len(base_task.runs()) == 4

    for run in base_task.runs():
        # identify the row data with same input as the run
        match = next(
            (row for row in row_data if row["input"] == run.input),
            None,
        )
        assert match is not None
        assert run.input == match["input"]
        assert run.output.output == match["output"]

        compare_tags(run.tags, match["tags"])


def test_import_csv_default_tags(base_task: Task):
    row_data = [
        {
            "input": "This is my input",
            "output": "This is my output 啊",
            "tags": "t1,t2",
        },
        {
            "input": "This is my input 4",
            "output": "This is my output 4 啊",
            "tags": "",
        },
    ]

    file_path = dicts_to_file_as_csv(row_data, "test.csv")

    importer = DatasetFileImporter(
        base_task,
        ImportConfig(
            dataset_type=DatasetImportFormat.CSV,
            dataset_path=file_path,
            dataset_name="test.csv",
        ),
    )

    importer.create_runs_from_file()

    assert len(base_task.runs()) == 2

    default_tags = 2

    for run in base_task.runs():
        # identify the row data with same input as the run
        match = next(
            (row for row in row_data if row["input"] == run.input),
            None,
        )

        assert match is not None

        if match["tags"]:
            expected_tags = match["tags"].split(",")
            assert len(run.tags) == len(expected_tags) + default_tags
        else:
            assert len(run.tags) == default_tags

        # these are the default tags
        assert "imported" in run.tags
        assert any(tag.startswith("imported_") for tag in run.tags)


def test_import_csv_plain_text_missing_output(base_task: Task):
    row_data = [
        {"input": "This is my input", "tags": "t1,t2"},
        {"input": "This is my input 2", "tags": "t3,t4"},
        {"input": "This is my input 3", "tags": "t5,t6"},
    ]

    file_path = dicts_to_file_as_csv(row_data, "test.csv")

    importer = DatasetFileImporter(
        base_task,
        ImportConfig(
            dataset_type=DatasetImportFormat.CSV,
            dataset_path=file_path,
            dataset_name="test.csv",
        ),
    )

    # check that the import raises an exception
    with pytest.raises(KilnInvalidImportFormat) as e:
        importer.create_runs_from_file()

    # no row number because the whole structure is invalid
    assert e.value.row_number is None
    assert "Missing required headers" in str(e.value)


def test_import_csv_structured_output(task_with_structured_output: Task):
    row_data = [
        {
            "input": "This is my input",
            "output": json.dumps({"sentiment": "高兴", "confidence": 0.95}),
            "tags": "t1,t2",
        },
        {
            "input": "This is my input 2",
            "output": json.dumps({"sentiment": "negative", "confidence": 0.05}),
            "tags": "t3,t4",
        },
        {
            "input": "This is my input 3",
            "output": json.dumps({"sentiment": "neutral", "confidence": 0.5}),
            "tags": "",
        },
    ]

    file_path = dicts_to_file_as_csv(row_data, "test.csv")

    importer = DatasetFileImporter(
        task_with_structured_output,
        ImportConfig(
            dataset_type=DatasetImportFormat.CSV,
            dataset_path=file_path,
            dataset_name="test.csv",
        ),
    )

    importer.create_runs_from_file()

    assert len(task_with_structured_output.runs()) == 3

    for run in task_with_structured_output.runs():
        # identify the row data with same input as the run
        match = next(
            (row for row in row_data if row["input"] == run.input),
            None,
        )
        assert match is not None
        assert run.input == match["input"]
        assert json.loads(run.output.output) == json.loads(match["output"])

        compare_tags(run.tags, match["tags"])


def test_import_csv_structured_output_wrong_schema(task_with_structured_output: Task):
    row_data = [
        {
            "input": "This is my input",
            "output": json.dumps({"sentiment": "positive", "confidence": 0.95}),
            "tags": "t1,t2",
        },
        {
            "input": "This is my input 2",
            # the output is wrong because sentiment is not a string
            "output": json.dumps({"sentiment": 100, "confidence": 0.05}),
            "tags": "t3,t4",
        },
        {
            "input": "This is my input 3",
            "output": json.dumps({"sentiment": "positive", "confidence": 0.5}),
            "tags": "",
        },
    ]

    file_path = dicts_to_file_as_csv(row_data, "test.csv")

    importer = DatasetFileImporter(
        task_with_structured_output,
        ImportConfig(
            dataset_type=DatasetImportFormat.CSV,
            dataset_path=file_path,
            dataset_name="test.csv",
        ),
    )

    # check that the import raises an exception
    with pytest.raises(KilnInvalidImportFormat) as e:
        importer.create_runs_from_file()

    # the row number is +1 because of the header
    assert e.value.row_number == 3
    assert "Error in row 3: Validation failed" in str(e.value)


def test_import_csv_structured_input_wrong_schema(task_with_structured_input: Task):
    row_data = [
        {
            # this one is missing example_id
            "input": json.dumps({"example_id": 1, "text": "This is my input"}),
            "output": "This is my output",
            "tags": "t1,t2",
        },
        {
            "input": json.dumps({"text": "This is my input 2"}),
            "output": "This is my output 2",
            "tags": "t3,t4",
        },
        {
            "input": json.dumps({"example_id": 3, "text": "This is my input 3"}),
            "output": "This is my output 3",
            "tags": "",
        },
    ]

    file_path = dicts_to_file_as_csv(row_data, "test.csv")

    importer = DatasetFileImporter(
        task_with_structured_input,
        ImportConfig(
            dataset_type=DatasetImportFormat.CSV,
            dataset_path=file_path,
            dataset_name="test.csv",
        ),
    )

    # check that the import raises an exception
    with pytest.raises(KilnInvalidImportFormat) as e:
        importer.create_runs_from_file()

    # the row number is +1 because of the header
    assert e.value.row_number == 3
    assert "Error in row 3: Validation failed" in str(e.value)


def test_import_csv_intermediate_outputs(task_with_intermediate_outputs: Task):
    row_data = [
        {
            "input": "This is my input",
            "output": "This is my output",
            "reasoning": "我觉得这个输出是正确的",
            "tags": "t1,t2",
        },
        {
            "input": "This is my input 2",
            "output": "This is my output 2",
            "reasoning": "thinking output 2",
            "tags": "t3,t4",
        },
        {
            "input": "This is my input 3",
            "output": "This is my output 3",
            "reasoning": "thinking output 3",
            "tags": "",
        },
    ]

    file_path = dicts_to_file_as_csv(row_data, "test.csv")

    importer = DatasetFileImporter(
        task_with_intermediate_outputs,
        ImportConfig(
            dataset_type=DatasetImportFormat.CSV,
            dataset_path=file_path,
            dataset_name="test.csv",
        ),
    )

    importer.create_runs_from_file()

    assert len(task_with_intermediate_outputs.runs()) == 3

    for run in task_with_intermediate_outputs.runs():
        # identify the row data with same input as the run
        match = next(
            (row for row in row_data if row["input"] == run.input),
            None,
        )
        assert match is not None
        assert run.input == match["input"]
        assert run.output.output == match["output"]
        assert run.intermediate_outputs["reasoning"] == match["reasoning"]

        compare_tags(run.tags, match["tags"])
