import json

import pytest
from pydantic import ValidationError

from kiln_ai.datamodel import (
    DataSource,
    DataSourceType,
    Project,
    Task,
    TaskOutput,
    TaskRun,
)
from kiln_ai.datamodel.test_json_schema import json_joke_schema


@pytest.fixture
def test_project_file(tmp_path):
    test_file_path = tmp_path / "project.kiln"
    data = {"v": 1, "name": "Test Project", "model_type": "project"}

    with open(test_file_path, "w") as file:
        json.dump(data, file, indent=4)

    return test_file_path


@pytest.fixture
def test_task_file(tmp_path):
    test_file_path = tmp_path / "task.json"
    data = {
        "v": 1,
        "name": "Test Task",
        "instruction": "Test Instruction",
        "model_type": "task",
    }

    with open(test_file_path, "w") as file:
        json.dump(data, file, indent=4)

    return test_file_path


def test_load_from_file(test_project_file):
    project = Project.load_from_file(test_project_file)
    assert project.v == 1
    assert project.name == "Test Project"
    assert project.path == test_project_file


def test_project_init():
    project = Project(name="test")
    assert project.name == "test"


def test_save_to_file(test_project_file):
    project = Project(
        name="Test Project", description="Test Description", path=test_project_file
    )
    project.save_to_file()

    with open(test_project_file, "r") as file:
        data = json.load(file)

    assert data["v"] == 1
    assert data["name"] == "Test Project"
    assert data["description"] == "Test Description"


def test_task_defaults():
    task = Task(name="Test Task", instruction="Test Instruction")
    assert task.description is None


def test_task_serialization(test_project_file):
    project = Project.load_from_file(test_project_file)
    task = Task(
        parent=project,
        name="Test Task",
        description="Test Description",
        instruction="Test Base Task Instruction",
        thinking_instruction="Test Thinking Instruction",
    )

    task.save_to_file()

    parsed_task = Task.all_children_of_parent_path(test_project_file)[0]
    assert parsed_task.name == "Test Task"
    assert parsed_task.description == "Test Description"
    assert parsed_task.instruction == "Test Base Task Instruction"
    assert parsed_task.thinking_instruction == "Test Thinking Instruction"


def test_save_to_file_without_path():
    project = Project(name="Test Project")
    with pytest.raises(ValueError):
        project.save_to_file()


def test_name_validation():
    Project(name="Test Project")
    Project(name="Te st_Proj- 1234567890")
    Project(name=("a" * 120))  # longest

    # a string with 120 characters

    with pytest.raises(ValueError):
        Project(name="Test Project!")
        Project(name="Test.Project")
        Project(name=("a" * 121))  # too long
        Project(name=("a"))  # too short


def test_auto_type_name():
    model = Project(name="Test Project")
    assert model.model_type == "project"


def test_load_tasks(test_project_file):
    # Set up a project model
    project = Project.load_from_file(test_project_file)

    # Set up multiple task models under the project
    task1 = Task(parent=project, name="Task1", instruction="Task 1 instruction")
    task2 = Task(parent=project, name="Task2", instruction="Task 2 instruction")
    task3 = Task(parent=project, name="Task3", instruction="Task 3 instruction")

    # Ensure the tasks are saved correctly
    task1.save_to_file()
    task2.save_to_file()
    task3.save_to_file()

    # Load tasks from the project
    tasks = project.tasks()

    # Verify that all tasks are loaded correctly
    assert len(tasks) == 3
    names = [task.name for task in tasks]
    assert "Task1" in names
    assert "Task2" in names
    assert "Task3" in names
    assert all(task.model_type == "task" for task in tasks)
    assert all(task.instruction != "" for task in tasks)


# verify no error on non-saved model
def test_load_children_no_path():
    project = Project(name="Test Project")
    assert len(project.tasks()) == 0


def test_check_model_type(test_project_file, test_task_file):
    project = Project.load_from_file(test_project_file)
    task = Task.load_from_file(test_task_file)
    assert project.model_type == "project"
    assert task.model_type == "task"
    assert task.instruction == "Test Instruction"

    with pytest.raises(ValueError):
        project = Project.load_from_file(test_task_file)

    with pytest.raises(ValueError):
        task = Task.load_from_file(test_project_file)


def test_task_output_schema(tmp_path):
    path = tmp_path / "task.kiln"
    task = Task(name="Test Task", path=path, instruction="Test Instruction")
    task.save_to_file()
    assert task.output_schema() is None
    task = Task(
        name="Test Task",
        instruction="Test Instruction",
        output_json_schema=json_joke_schema,
        input_json_schema=json_joke_schema,
        path=path,
    )
    task.save_to_file()
    schemas = [task.output_schema(), task.input_schema()]
    for schema in schemas:
        assert schema is not None
        assert schema["properties"]["setup"]["type"] == "string"
        assert schema["properties"]["punchline"]["type"] == "string"
        assert schema["properties"]["rating"] is not None

    # Not json schema
    with pytest.raises(ValidationError):
        task = Task(name="Test Task", output_json_schema="hello", path=path)
    with pytest.raises(ValidationError):
        task = Task(name="Test Task", output_json_schema='{"asdf":{}}', path=path)
    with pytest.raises(ValidationError):
        task = Task(name="Test Task", output_json_schema="{'asdf':{}}", path=path)
    with pytest.raises(ValidationError):
        task = Task(name="Test Task", input_json_schema="{asdf", path=path)


def test_task_run_intermediate_outputs():
    # Create a basic task output
    output = TaskOutput(
        output="test output",
        source=DataSource(
            type=DataSourceType.synthetic,
            properties={
                "model_name": "test-model",
                "model_provider": "test-provider",
                "adapter_name": "test-adapter",
            },
        ),
    )

    # Test valid intermediate outputs
    task_run = TaskRun(
        input="test input",
        input_source=DataSource(
            type=DataSourceType.human,
            properties={"created_by": "test-user"},
        ),
        output=output,
        intermediate_outputs={
            "cot": "chain of thought output",
            "draft": "draft output",
        },
    )
    assert task_run.intermediate_outputs == {
        "cot": "chain of thought output",
        "draft": "draft output",
    }
