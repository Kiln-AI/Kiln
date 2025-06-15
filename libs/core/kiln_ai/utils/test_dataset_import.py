import csv
import json
import logging
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import BaseModel, ValidationError

from kiln_ai.datamodel import (
    DataSource,
    DataSourceType,
    Project,
    Task,
    TaskOutput,
    TaskRun,
)
from kiln_ai.utils.dataset_import import (
    DatasetFileImporter,
    DatasetImportFormat,
    ImportConfig,
    KilnInvalidImportFormat,
    add_tag_splits,
    deserialize_tags,
    format_validation_error,
    generate_import_tags,
    without_none_values,
)

logger = logging.getLogger(__name__)


@pytest.fixture
def base_task(tmp_path) -> Task:
    project_path = tmp_path / "project.kiln"

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


def dicts_to_file_as_csv(items: list[dict], file_name: str, tmp_path: Path) -> str:
    """Write a list of dictionaries to a CSV file with escaping and a header.

    Returns the path to the file.
    """
    rows = [dict_to_csv_row(item) for item in items]
    header = ",".join(f'"{key}"' for key in items[0].keys())
    csv_data = header + "\n" + "\n".join(rows)

    file_path = tmp_path / file_name
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


def test_import_csv_plain_text(base_task: Task, tmp_path):
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

    file_path = dicts_to_file_as_csv(row_data, "test.csv", tmp_path)

    with patch("kiln_ai.utils.dataset_import.add_tag_splits") as mock_add_tag_splits:
        importer = DatasetFileImporter(
            base_task,
            ImportConfig(
                dataset_type=DatasetImportFormat.CSV,
                dataset_path=file_path,
                dataset_name="test.csv",
            ),
        )

        importer.create_runs_from_file()

        # Verify add_tag_splits was called
        mock_add_tag_splits.assert_called_once()

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


def test_import_csv_default_tags(base_task: Task, tmp_path):
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

    file_path = dicts_to_file_as_csv(row_data, "test.csv", tmp_path)

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


def test_import_csv_plain_text_missing_output(base_task: Task, tmp_path):
    row_data = [
        {"input": "This is my input", "tags": "t1,t2"},
        {"input": "This is my input 2", "tags": "t3,t4"},
        {"input": "This is my input 3", "tags": "t5,t6"},
    ]

    file_path = dicts_to_file_as_csv(row_data, "test.csv", tmp_path)

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


def test_import_csv_utf8_encoding(base_task: Task, tmp_path):
    """Ensure UTF-8 encoded files are read correctly."""

    row_data = [
        {
            "input": "Español entrada 你好👋",
            "output": "salida áéí 你好👋",
            "tags": "",
        },
    ]

    file_path = dicts_to_file_as_csv(row_data, "utf8.csv", tmp_path)

    importer = DatasetFileImporter(
        base_task,
        ImportConfig(
            dataset_type=DatasetImportFormat.CSV,
            dataset_path=file_path,
            dataset_name="utf8.csv",
        ),
    )

    importer.create_runs_from_file()

    assert len(base_task.runs()) == 1
    run = base_task.runs()[0]
    assert run.input == "Español entrada 你好👋"
    assert run.output.output == "salida áéí 你好👋"


def test_import_csv_structured_output(task_with_structured_output: Task, tmp_path):
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

    file_path = dicts_to_file_as_csv(row_data, "test.csv", tmp_path)

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


def test_import_csv_structured_output_wrong_schema(
    task_with_structured_output: Task, tmp_path
):
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

    file_path = dicts_to_file_as_csv(row_data, "test.csv", tmp_path)

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


def test_import_csv_structured_input_wrong_schema(
    task_with_structured_input: Task, tmp_path
):
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

    file_path = dicts_to_file_as_csv(row_data, "test.csv", tmp_path)

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


def test_import_csv_intermediate_outputs_reasoning(
    task_with_intermediate_outputs: Task,
    tmp_path,
):
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

    file_path = dicts_to_file_as_csv(row_data, "test.csv", tmp_path)

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


def test_import_csv_intermediate_outputs_cot(
    task_with_intermediate_outputs: Task, tmp_path
):
    row_data = [
        {
            "input": "This is my input",
            "output": "This is my output",
            "chain_of_thought": "我觉得这个输出是正确的",
            "tags": "t1,t2",
        },
        {
            "input": "This is my input 2",
            "output": "This is my output 2",
            "chain_of_thought": "thinking output 2",
            "tags": "t3,t4",
        },
        {
            "input": "This is my input 3",
            "output": "This is my output 3",
            "chain_of_thought": "thinking output 3",
            "tags": "",
        },
    ]

    file_path = dicts_to_file_as_csv(row_data, "test.csv", tmp_path)

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
        assert run.intermediate_outputs["chain_of_thought"] == match["chain_of_thought"]
        compare_tags(run.tags, match["tags"])


def test_import_csv_intermediate_outputs_reasoning_and_cot(
    task_with_intermediate_outputs: Task,
    tmp_path,
):
    row_data = [
        {
            "input": "This is my input",
            "output": "This is my output",
            "reasoning": "thinking output 1",
            "chain_of_thought": "thinking output 1",
            "tags": "t1,t2",
        },
    ]

    file_path = dicts_to_file_as_csv(row_data, "test.csv", tmp_path)

    importer = DatasetFileImporter(
        task_with_intermediate_outputs,
        ImportConfig(
            dataset_type=DatasetImportFormat.CSV,
            dataset_path=file_path,
            dataset_name="test.csv",
        ),
    )

    importer.create_runs_from_file()

    assert len(task_with_intermediate_outputs.runs()) == 1

    for run in task_with_intermediate_outputs.runs():
        # identify the row data with same input as the run
        match = next(
            (row for row in row_data if row["input"] == run.input),
            None,
        )
        assert match is not None
        assert run.input == match["input"]
        assert run.output.output == match["output"]
        assert run.intermediate_outputs["chain_of_thought"] == match["chain_of_thought"]
        assert run.intermediate_outputs["reasoning"] == match["reasoning"]
        compare_tags(run.tags, match["tags"])


def test_import_csv_invalid_tags(base_task: Task, tmp_path):
    row_data = [
        {
            "input": "This is my input",
            "output": "This is my output",
            "tags": "tag with space,valid-tag",
        },
        {
            "input": "This is my input 2",
            "output": "This is my output 2",
            "tags": "another invalid tag",
        },
    ]

    file_path = dicts_to_file_as_csv(row_data, "test.csv", tmp_path)

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

    # the row number is +1 because of the header
    assert e.value.row_number == 2
    assert "Tags cannot contain spaces" in str(e.value)


def test_without_none_values():
    assert without_none_values({"a": 1, "b": None}) == {"a": 1}
    assert without_none_values({"a": None, "b": 2}) == {"b": 2}
    assert without_none_values({"a": None, "b": None}) == {}


def test_deserialize_tags():
    assert deserialize_tags("t1,t2") == ["t1", "t2"]
    assert deserialize_tags(None) == []
    assert deserialize_tags("") == []
    assert deserialize_tags("   ") == []
    assert deserialize_tags("t1, t2") == ["t1", "t2"]


def test_format_validation_error():
    class TestModel(BaseModel):
        a: int
        b: int

    try:
        TestModel.model_validate({"a": "not an int"})
    except ValidationError as e:
        human_readable = format_validation_error(e)
        assert human_readable.startswith("Validation failed:")
        assert (
            "a: Input should be a valid integer, unable to parse string as an integer"
            in human_readable
        )
        assert "b: Field required" in human_readable


def test_generate_import_tags():
    assert generate_import_tags("123") == ["imported", "imported_123"]


def test_add_tag_splits(base_task: Task):
    """Test that tag splits are assigned correctly with exact proportions."""
    # Create some test runs
    runs = []
    for i in range(10):
        run = TaskRun(
            parent=base_task,
            input=f"input {i}",
            input_source=DataSource(
                type=DataSourceType.file_import,
                properties={"file_name": "test.csv"},
            ),
            output=TaskOutput(
                output=f"output {i}",
                source=DataSource(
                    type=DataSourceType.file_import,
                    properties={"file_name": "test.csv"},
                ),
            ),
        )
        runs.append(run)

    # Test with 70/30 split
    tag_splits = {"train": 0.7, "test": 0.3}
    add_tag_splits(runs, tag_splits)

    # Count the tags
    train_count = sum(1 for run in runs if "train" in run.tags)
    test_count = sum(1 for run in runs if "test" in run.tags)

    # With 10 runs, we should get exactly 7 train and 3 test
    assert train_count == 7
    assert test_count == 3
    assert len(runs) == train_count + test_count


def test_add_tag_splits_rounding(base_task: Task):
    """Test that tag splits handle rounding correctly."""
    # Test a 33/33/34 split
    runs = []
    for i in range(34):
        run = TaskRun(
            parent=base_task,
            input=f"input {i}",
            input_source=DataSource(
                type=DataSourceType.file_import,
                properties={"file_name": "test.csv"},
            ),
            output=TaskOutput(
                output=f"output {i}",
                source=DataSource(
                    type=DataSourceType.file_import,
                    properties={"file_name": "test.csv"},
                ),
            ),
        )
        runs.append(run)

    # Test with three equal splits
    tag_splits = {"train": 0.33, "val": 0.33, "test": 0.34}
    add_tag_splits(runs, tag_splits)

    # Count the tags
    train_count = sum(1 for run in runs if "train" in run.tags)
    val_count = sum(1 for run in runs if "val" in run.tags)
    test_count = sum(1 for run in runs if "test" in run.tags)

    # Should have one of each
    assert train_count in [11, 12]
    assert val_count in [11, 12]
    assert test_count in [11, 12]
    assert len(runs) == train_count + val_count + test_count


def test_add_tag_splits_none(base_task: Task):
    """Test that None tag_splits is handled correctly."""
    runs = []
    for i in range(5):
        run = TaskRun(
            parent=base_task,
            input=f"input {i}",
            input_source=DataSource(
                type=DataSourceType.file_import,
                properties={"file_name": "test.csv"},
            ),
            output=TaskOutput(
                output=f"output {i}",
                source=DataSource(
                    type=DataSourceType.file_import,
                    properties={"file_name": "test.csv"},
                ),
            ),
        )
        runs.append(run)

    # Should not modify any tags
    original_tags = [run.tags.copy() for run in runs]
    add_tag_splits(runs, None)
    for run, original in zip(runs, original_tags):
        assert run.tags == original


def test_add_tag_splits_randomness(base_task: Task):
    """Test that tag assignment is random but maintains proportions."""
    # Create 100 runs for better statistical significance
    runs = []
    for i in range(100):
        run = TaskRun(
            parent=base_task,
            input=f"input {i}",
            input_source=DataSource(
                type=DataSourceType.file_import,
                properties={"file_name": "test.csv"},
            ),
            output=TaskOutput(
                output=f"output {i}",
                source=DataSource(
                    type=DataSourceType.file_import,
                    properties={"file_name": "test.csv"},
                ),
            ),
        )
        runs.append(run)

    # Test with 60/40 split
    tag_splits = {"train": 0.6, "test": 0.4}
    add_tag_splits(runs, tag_splits)

    # Count the tags
    train_count = sum(1 for run in runs if "train" in run.tags)
    test_count = sum(1 for run in runs if "test" in run.tags)

    # Should have exactly 60 train and 40 test
    assert train_count == 60
    assert test_count == 40
    assert len(runs) == train_count + test_count

    # Check that the assignment is not just sequential
    # by looking at the first few runs
    first_few_runs = runs[:35]
    train_tags = sum(1 for run in first_few_runs if "train" in run.tags)
    test_tags = sum(1 for run in first_few_runs if "test" in run.tags)

    # If assignment was sequential, we'd expect all first 35 to be train
    # This test might occasionally fail if we get unlucky with random assignment
    # but it's very unlikely
    assert train_tags < 35
    assert test_tags > 0


def test_validate_tag_splits():
    """Test that validate_tag_splits correctly validates tag split proportions."""
    # Test valid splits
    config = ImportConfig(
        dataset_type=DatasetImportFormat.CSV,
        dataset_path="test.csv",
        dataset_name="test.csv",
        tag_splits={"train": 0.7, "test": 0.3},
    )
    config.validate_tag_splits()  # Should not raise

    # Test valid splits with small floating point errors
    config = ImportConfig(
        dataset_type=DatasetImportFormat.CSV,
        dataset_path="test.csv",
        dataset_name="test.csv",
        tag_splits={"train": 0.7, "test": 0.3000001},
    )
    config.validate_tag_splits()  # Should not raise

    # Test invalid splits that don't sum to 1
    config = ImportConfig(
        dataset_type=DatasetImportFormat.CSV,
        dataset_path="test.csv",
        dataset_name="test.csv",
        tag_splits={"train": 0.7, "test": 0.4},
    )
    with pytest.raises(ValueError) as e:
        config.validate_tag_splits()
    assert "Splits must sum to 1" in str(e.value)

    # Test None tag_splits
    config = ImportConfig(
        dataset_type=DatasetImportFormat.CSV,
        dataset_path="test.csv",
        dataset_name="test.csv",
        tag_splits=None,
    )
    config.validate_tag_splits()  # Should not raise


def test_dataset_file_importer_validates_tag_splits(base_task: Task, tmp_path):
    """Test that DatasetFileImporter validates tag splits on initialization."""
    # Test with invalid splits
    with pytest.raises(ValueError) as e:
        DatasetFileImporter(
            base_task,
            ImportConfig(
                dataset_type=DatasetImportFormat.CSV,
                dataset_path="test.csv",
                dataset_name="test.csv",
                tag_splits={"train": 0.7, "test": 0.4},  # Sums to 1.1
            ),
        )
    assert "Splits must sum to 1" in str(e.value)

    # Test with valid splits
    importer = DatasetFileImporter(
        base_task,
        ImportConfig(
            dataset_type=DatasetImportFormat.CSV,
            dataset_path="test.csv",
            dataset_name="test.csv",
            tag_splits={"train": 0.7, "test": 0.3},
        ),
    )
    assert importer.config.tag_splits == {"train": 0.7, "test": 0.3}
