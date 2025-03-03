import json
import sys

import pytest
from pydantic import ValidationError

from kiln_ai.datamodel import (
    DatasetSplit,
    DataSource,
    DataSourceType,
    Finetune,
    Project,
    Task,
    TaskOutput,
    TaskOutputRating,
    TaskOutputRatingType,
    TaskRequirement,
    TaskRun,
)


@pytest.fixture
def valid_task_run(tmp_path):
    task = Task(
        name="Test Task",
        instruction="test instruction",
        path=tmp_path / Task.base_filename(),
    )
    return TaskRun(
        parent=task,
        input="Test input",
        input_source=DataSource(
            type=DataSourceType.human,
            properties={"created_by": "John Doe"},
        ),
        output=TaskOutput(
            output="Test output",
            source=DataSource(
                type=DataSourceType.human,
                properties={"created_by": "John Doe"},
            ),
        ),
    )


def test_task_model_validation(valid_task_run):
    task_run = valid_task_run
    task_run.model_validate(task_run, strict=True)
    task_run.save_to_file()
    assert task_run.input == "Test input"
    assert task_run.input_source.type == DataSourceType.human
    assert task_run.input_source.properties == {"created_by": "John Doe"}
    assert task_run.output.output == "Test output"
    assert task_run.output.source.type == DataSourceType.human
    assert task_run.output.source.properties == {"created_by": "John Doe"}

    # Invalid source
    with pytest.raises(ValidationError, match="Input should be"):
        DataSource(type="invalid")

    if sys.version_info >= (3, 12):
        with pytest.raises(ValidationError, match="Invalid data source type"):
            task_run = valid_task_run.model_copy(deep=True)
            task_run.input_source.type = "invalid"
            DataSource.model_validate(task_run.input_source, strict=True)

    # Missing required field
    with pytest.raises(ValidationError, match="Input should be a valid string"):
        task_run = valid_task_run.model_copy()
        task_run.input = None

    # Invalid source_properties type
    with pytest.raises(ValidationError):
        task_run = valid_task_run.model_copy()
        task_run.input_source.properties = "invalid"
        DataSource.model_validate(task_run.input_source, strict=True)

    # Test we catch nested validation errors
    with pytest.raises(ValidationError, match="'created_by' is required for"):
        task_run = TaskRun(
            input="Test input",
            input_source=DataSource(
                type=DataSourceType.human,
                properties={"created_by": "John Doe"},
            ),
            output=TaskOutput(
                output="Test output",
                source=DataSource(
                    type=DataSourceType.human,
                    properties={"wrong_key": "John Doe"},
                ),
            ),
        )


def test_task_run_relationship(valid_task_run):
    assert valid_task_run.__class__.relationship_name() == "runs"
    assert valid_task_run.__class__.parent_type().__name__ == "Task"


def test_dataset_split_relationship():
    assert DatasetSplit.relationship_name() == "dataset_splits"
    assert DatasetSplit.parent_type().__name__ == "Task"


def test_base_finetune_relationship():
    assert Finetune.relationship_name() == "finetunes"
    assert Finetune.parent_type().__name__ == "Task"


def test_structured_output_workflow(tmp_path):
    tmp_project_file = (
        tmp_path / "test_structured_output_runs" / Project.base_filename()
    )
    # Create project
    project = Project(name="Test Project", path=str(tmp_project_file))
    project.save_to_file()

    # Create task with requirements
    req1 = TaskRequirement(name="Req1", instruction="Name must be capitalized")
    req2 = TaskRequirement(name="Req2", instruction="Age must be positive")

    task = Task(
        name="Structured Output Task",
        parent=project,
        instruction="Generate a JSON object with name and age",
        output_json_schema=json.dumps(
            {
                "type": "object",
                "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
                "required": ["name", "age"],
            }
        ),
        requirements=[
            req1,
            req2,
        ],
    )
    task.save_to_file()

    # Create runs
    runs = []
    for source in [DataSourceType.human, DataSourceType.synthetic]:
        for _ in range(2):
            task_run = TaskRun(
                input="Generate info for John Doe",
                input_source=DataSource(
                    type=DataSourceType.human,
                    properties={"created_by": "john_doe"},
                )
                if source == DataSourceType.human
                else DataSource(
                    type=DataSourceType.synthetic,
                    properties={
                        "adapter_name": "TestAdapter",
                        "model_name": "GPT-4",
                        "model_provider": "OpenAI",
                        "prompt_id": "simple_prompt_builder",
                    },
                ),
                parent=task,
                output=TaskOutput(
                    output='{"name": "John Doe", "age": 30}',
                    source=DataSource(
                        type=DataSourceType.human,
                        properties={"created_by": "john_doe"},
                    ),
                ),
            )
            task_run.save_to_file()
            runs.append(task_run)

    # make a run with a repaired output
    repaired_run = TaskRun(
        input="Generate info for John Doe",
        input_source=DataSource(
            type=DataSourceType.human,
            properties={"created_by": "john_doe"},
        ),
        parent=task,
        output=TaskOutput(
            output='{"name": "John Doe", "age": 31}',
            source=DataSource(
                type=DataSourceType.human,
                properties={"created_by": "john_doe"},
            ),
        ),
        repair_instructions="The age should be 31 instead of 30",
        repaired_output=TaskOutput(
            output='{"name": "John Doe", "age": 31}',
            source=DataSource(
                type=DataSourceType.human,
                properties={"created_by": "john_doe"},
            ),
        ),
    )
    repaired_run.save_to_file()
    runs.append(repaired_run)

    # Update outputs with ratings
    for task_run in runs:
        task_run.output.rating = TaskOutputRating(
            value=4,
            requirement_ratings={
                req1.id: 5,
                req2.id: 5,
            },
        )
        task_run.save_to_file()

    # Load from disk and validate
    loaded_project = Project.load_from_file(tmp_project_file)
    loaded_task = loaded_project.tasks()[0]

    assert loaded_task.name == "Structured Output Task"
    assert len(loaded_task.requirements) == 2
    loaded_runs = loaded_task.runs()
    assert len(loaded_runs) == 5

    for task_run in loaded_runs:
        output = task_run.output
        assert output.rating is not None
        assert output.rating.value == 4
        assert len(output.rating.requirement_ratings) == 2

    # Find the run with the fixed output
    run_with_fixed_output = next(
        (task_run for task_run in loaded_runs if task_run.repaired_output is not None),
        None,
    )
    assert run_with_fixed_output is not None, "No run found with fixed output"
    assert (
        run_with_fixed_output.repaired_output.output
        == '{"name": "John Doe", "age": 31}'
    )


def test_task_output_requirement_rating_keys(tmp_path):
    # Create a project, task, and example hierarchy
    project = Project(name="Test Project", path=(tmp_path / "test_project"))
    project.save_to_file()

    # Create task requirements
    req1 = TaskRequirement(
        name="Requirement 1", instruction="Requirement 1 instruction"
    )
    req2 = TaskRequirement(
        name="Requirement 2", instruction="Requirement 2 instruction"
    )
    task = Task(
        name="Test Task",
        parent=project,
        instruction="Task instruction",
        requirements=[req1, req2],
    )
    task.save_to_file()

    # Valid case: all requirement IDs are valid
    task_run = TaskRun(
        input="Test input",
        input_source=DataSource(
            type=DataSourceType.human,
            properties={"created_by": "john_doe"},
        ),
        parent=task,
        output=TaskOutput(
            output="Test output",
            source=DataSource(
                type=DataSourceType.human,
                properties={"created_by": "john_doe"},
            ),
            rating=TaskOutputRating(
                value=4,
                requirement_ratings={
                    req1.id: 5,
                    req2.id: 4,
                },
            ),
        ),
    )
    task_run.save_to_file()
    assert task_run.output.rating.requirement_ratings is not None


_schema_match = "This task requires a specific output schema. While the model produced JSON, that JSON didn't meet the schema."


def test_task_output_schema_validation(tmp_path):
    # Create a project, task, and example hierarchy
    project = Project(name="Test Project", path=(tmp_path / "test_project"))
    project.save_to_file()
    task = Task(
        name="Test Task",
        instruction="test instruction",
        parent=project,
        output_json_schema=json.dumps(
            {
                "type": "object",
                "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
                "required": ["name", "age"],
            }
        ),
    )
    task.save_to_file()

    # Create an run output with a valid schema
    task_output = TaskRun(
        input="Test input",
        input_source=DataSource(
            type=DataSourceType.human,
            properties={"created_by": "john_doe"},
        ),
        parent=task,
        output=TaskOutput(
            output='{"name": "John Doe", "age": 30}',
            source=DataSource(
                type=DataSourceType.human,
                properties={"created_by": "john_doe"},
            ),
        ),
    )
    task_output.save_to_file()

    # changing to invalid output
    with pytest.raises(
        ValueError,
        match=_schema_match,
    ):
        task_output.output.output = '{"name": "John Doe", "age": "thirty"}'
        task_output.save_to_file()

    # changing to invalid output from loaded model
    loaded_task_output = TaskRun.load_from_file(task_output.path)
    with pytest.raises(
        ValueError,
        match=_schema_match,
    ):
        loaded_task_output.output.output = '{"name": "John Doe", "age": "forty"}'
        loaded_task_output.save_to_file()

    # Invalid case: output does not match task output schema
    with pytest.raises(ValueError, match=_schema_match):
        task_output = TaskRun(
            input="Test input",
            input_source=DataSource(
                type=DataSourceType.human,
                properties={"created_by": "john_doe"},
            ),
            parent=task,
            output=TaskOutput(
                output='{"name": "John Doe", "age": "thirty"}',
                source=DataSource(
                    type=DataSourceType.human,
                    properties={"created_by": "john_doe"},
                ),
            ),
        )
        task_output.save_to_file()


def test_task_input_schema_validation(tmp_path):
    # Create a project and task hierarchy
    project = Project(name="Test Project", path=(tmp_path / "test_project"))
    project.save_to_file()
    task = Task(
        name="Test Task",
        parent=project,
        instruction="test instruction",
        input_json_schema=json.dumps(
            {
                "type": "object",
                "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
                "required": ["name", "age"],
            }
        ),
    )
    task.save_to_file()

    # Create an example with a valid input schema
    valid_task_output = TaskRun(
        input='{"name": "John Doe", "age": 30}',
        input_source=DataSource(
            type=DataSourceType.human,
            properties={"created_by": "john_doe"},
        ),
        parent=task,
        output=TaskOutput(
            output="Test output",
            source=DataSource(
                type=DataSourceType.human,
                properties={"created_by": "john_doe"},
            ),
        ),
    )
    valid_task_output.save_to_file()

    # Changing to invalid input
    with pytest.raises(ValueError, match=_schema_match):
        valid_task_output.input = '{"name": "John Doe", "age": "thirty"}'
        valid_task_output.save_to_file()

    # loading from file, then changing to invalid input
    loaded_task_output = TaskRun.load_from_file(valid_task_output.path)
    with pytest.raises(ValueError, match=_schema_match):
        loaded_task_output.input = '{"name": "John Doe", "age": "thirty"}'
        loaded_task_output.save_to_file()

    # Invalid case: input does not match task input schema
    with pytest.raises(ValueError, match=_schema_match):
        task_output = TaskRun(
            input='{"name": "John Doe", "age": "thirty"}',
            input_source=DataSource(
                type=DataSourceType.human,
                properties={"created_by": "john_doe"},
            ),
            parent=task,
            output=TaskOutput(
                output="Test output",
                source=DataSource(
                    type=DataSourceType.human,
                    properties={"created_by": "john_doe"},
                ),
            ),
        )
        task_output.save_to_file()


def test_valid_human_task_output():
    output = TaskOutput(
        output="Test output",
        source=DataSource(
            type=DataSourceType.human,
            properties={"created_by": "John Doe"},
        ),
    )
    assert output.source.type == DataSourceType.human
    assert output.source.properties["created_by"] == "John Doe"


def test_invalid_human_task_output_missing_created_by():
    with pytest.raises(ValidationError, match="'created_by' is required for"):
        TaskOutput(
            output="Test output",
            source=DataSource(
                type=DataSourceType.human,
                properties={},
            ),
        )


def test_invalid_human_task_output_empty_created_by():
    with pytest.raises(
        ValidationError, match="Property 'created_by' must be a non-empty string"
    ):
        TaskOutput(
            output="Test output",
            source=DataSource(
                type=DataSourceType.human,
                properties={"created_by": ""},
            ),
        )


def test_valid_synthetic_task_output():
    output = TaskOutput(
        output="Test output",
        source=DataSource(
            type=DataSourceType.synthetic,
            properties={
                "adapter_name": "TestAdapter",
                "model_name": "GPT-4",
                "model_provider": "OpenAI",
                "prompt_id": "simple_prompt_builder",
            },
        ),
    )
    assert output.source.type == DataSourceType.synthetic
    assert output.source.properties["adapter_name"] == "TestAdapter"
    assert output.source.properties["model_name"] == "GPT-4"
    assert output.source.properties["model_provider"] == "OpenAI"
    assert output.source.properties["prompt_id"] == "simple_prompt_builder"


def test_invalid_synthetic_task_output_missing_keys():
    with pytest.raises(
        ValidationError,
        match="'model_provider' is required for",
    ):
        TaskOutput(
            output="Test output",
            source=DataSource(
                type=DataSourceType.synthetic,
                properties={"adapter_name": "TestAdapter", "model_name": "GPT-4"},
            ),
        )


def test_invalid_synthetic_task_output_empty_values():
    with pytest.raises(
        ValidationError, match="'model_name' must be a non-empty string"
    ):
        TaskOutput(
            output="Test output",
            source=DataSource(
                type=DataSourceType.synthetic,
                properties={
                    "adapter_name": "TestAdapter",
                    "model_name": "",
                    "model_provider": "OpenAI",
                    "prompt_id": "simple_prompt_builder",
                },
            ),
        )


def test_invalid_synthetic_task_output_non_string_values():
    with pytest.raises(ValidationError, match="'prompt_id' must be of type str"):
        DataSource(
            type=DataSourceType.synthetic,
            properties={
                "adapter_name": "TestAdapter",
                "model_name": "GPT-4",
                "model_provider": "OpenAI",
                "prompt_id": 123,
            },
        )


def test_task_run_validate_repaired_output():
    # Test case 1: Valid TaskRun with no repaired_output
    valid_task_run = TaskRun(
        input="test input",
        input_source=DataSource(
            type=DataSourceType.human,
            properties={"created_by": "john_doe"},
        ),
        output=TaskOutput(
            output="test output",
            source=DataSource(
                type=DataSourceType.human,
                properties={"created_by": "john_doe"},
            ),
        ),
    )
    assert valid_task_run.repaired_output is None

    # Test case 2: Valid TaskRun with repaired_output and no rating
    valid_task_run_with_repair = TaskRun(
        input="test input",
        input_source=DataSource(
            type=DataSourceType.human,
            properties={"created_by": "john_doe"},
        ),
        output=TaskOutput(
            output="test output",
            source=DataSource(
                type=DataSourceType.human,
                properties={"created_by": "john_doe"},
            ),
        ),
        repair_instructions="Fix the output",
        repaired_output=TaskOutput(
            output="repaired output",
            source=DataSource(
                type=DataSourceType.human,
                properties={"created_by": "john_doe"},
            ),
        ),
    )
    assert valid_task_run_with_repair.repaired_output is not None
    assert valid_task_run_with_repair.repaired_output.rating is None

    # test missing repair_instructions
    with pytest.raises(ValidationError) as exc_info:
        TaskRun(
            input="test input",
            input_source=DataSource(
                type=DataSourceType.human,
                properties={"created_by": "john_doe"},
            ),
            output=TaskOutput(
                output="test output",
                source=DataSource(
                    type=DataSourceType.human,
                    properties={"created_by": "john_doe"},
                ),
            ),
            repaired_output=TaskOutput(
                output="repaired output",
                source=DataSource(
                    type=DataSourceType.human,
                    properties={"created_by": "john_doe"},
                ),
            ),
        )

    assert "Repair instructions are required" in str(exc_info.value)

    # test missing repaired_output
    with pytest.raises(ValidationError) as exc_info:
        TaskRun(
            input="test input",
            input_source=DataSource(
                type=DataSourceType.human,
                properties={"created_by": "john_doe"},
            ),
            output=TaskOutput(
                output="test output",
                source=DataSource(
                    type=DataSourceType.human,
                    properties={"created_by": "john_doe"},
                ),
            ),
            repair_instructions="Fix the output",
        )

    assert "A repaired output is required" in str(exc_info.value)

    # Test case 3: Invalid TaskRun with repaired_output containing a rating
    with pytest.raises(ValidationError) as exc_info:
        TaskRun(
            input="test input",
            input_source=DataSource(
                type=DataSourceType.human,
                properties={"created_by": "john_doe"},
            ),
            output=TaskOutput(
                output="test output",
                source=DataSource(
                    type=DataSourceType.human,
                    properties={"created_by": "john_doe"},
                ),
            ),
            repaired_output=TaskOutput(
                output="repaired output",
                source=DataSource(
                    type=DataSourceType.human,
                    properties={"created_by": "john_doe"},
                ),
                rating=TaskOutputRating(type=TaskOutputRatingType.five_star, value=5.0),
            ),
        )

    assert "Repaired output rating must be None" in str(exc_info.value)
