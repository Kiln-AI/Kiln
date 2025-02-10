import json

import pytest

from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.data_gen.data_gen_task import (
    DataGenCategoriesTask,
    DataGenCategoriesTaskInput,
    DataGenCategoriesTaskOutput,
    DataGenSampleTask,
    DataGenSampleTaskInput,
    list_json_schema_for_task,
)
from kiln_ai.adapters.provider_tools import get_model_and_provider
from kiln_ai.adapters.test_prompt_adaptors import get_all_models_and_providers
from kiln_ai.datamodel import Project, Task


@pytest.fixture
def base_task():
    project = Project(name="TestProject")
    return Task(
        name="Cowboy Speaker",
        parent=project,
        description="Reply like a cowboy",
        instruction="Reply like a cowboy",
        requirements=[],
    )


def test_data_gen_categories_task_input_initialization(base_task):
    # Arrange
    node_path = ["root", "branch", "leaf"]
    num_subtopics = 4
    human_guidance = "Test guidance"

    # Act
    input_model = DataGenCategoriesTaskInput.from_task(
        task=base_task,
        node_path=node_path,
        num_subtopics=num_subtopics,
        human_guidance=human_guidance,
    )

    # Assert
    assert input_model.node_path == node_path
    assert input_model.num_subtopics == num_subtopics
    assert input_model.human_guidance == human_guidance
    assert isinstance(input_model.system_prompt, str)
    assert "Reply like a cowboy" in input_model.system_prompt


def test_data_gen_categories_task_input_default_values(base_task):
    # Act
    input_model = DataGenCategoriesTaskInput.from_task(task=base_task)

    # Assert
    assert input_model.num_subtopics == 6
    assert input_model.human_guidance is None
    assert input_model.node_path == []


def test_data_gen_categories_task_initialization():
    # Act
    task = DataGenCategoriesTask()

    # Assert
    assert task.name == "DataGen"
    assert isinstance(task.parent, Project)
    assert task.description is not None
    assert task.instruction is not None
    assert isinstance(task.input_json_schema, str)
    assert isinstance(task.output_json_schema, str)


def test_data_gen_categories_task_schemas():
    # Act
    task = DataGenCategoriesTask()

    # Assert
    input_schema = json.loads(task.input_json_schema)
    output_schema = json.loads(task.output_json_schema)

    assert isinstance(input_schema, dict)
    assert isinstance(output_schema, dict)
    assert output_schema["type"] == "object"
    assert output_schema["properties"]["subtopics"]["type"] == "array"
    assert input_schema["properties"]["node_path"]["type"] == "array"
    assert input_schema["properties"]["num_subtopics"]["type"] == "integer"
    assert set(input_schema["required"]) == {
        "node_path",
        "num_subtopics",
        "system_prompt",
    }


@pytest.mark.paid
@pytest.mark.ollama
@pytest.mark.parametrize("model_name,provider_name", get_all_models_and_providers())
async def test_data_gen_all_models_providers(
    tmp_path, model_name, provider_name, base_task
):
    _, provider = get_model_and_provider(model_name, provider_name)
    if not provider.supports_data_gen:
        # pass if the model doesn't support data gen (testing the support flag is part of this)
        return

    data_gen_task = DataGenCategoriesTask()
    data_gen_input = DataGenCategoriesTaskInput.from_task(base_task, num_subtopics=6)

    adapter = adapter_for_task(
        data_gen_task,
        model_name=model_name,
        provider=provider_name,
    )

    input_dict = data_gen_input.model_dump()
    run = await adapter.invoke(input_dict)
    parsed_output = DataGenCategoriesTaskOutput.model_validate_json(run.output.output)
    assert len(parsed_output.subtopics) == 6
    for subtopic in parsed_output.subtopics:
        assert isinstance(subtopic, str)


def test_data_gen_sample_task_input_initialization(base_task):
    # Arrange
    topic = ["cowboys", "hats"]
    num_samples = 4
    human_guidance = "Test guidance"

    # Act
    input_model = DataGenSampleTaskInput.from_task(
        task=base_task,
        topic=topic,
        num_samples=num_samples,
        human_guidance=human_guidance,
    )

    # Assert
    assert input_model.topic == topic
    assert input_model.num_samples == num_samples
    assert input_model.human_guidance == human_guidance
    assert isinstance(input_model.system_prompt, str)
    assert "Reply like a cowboy" in input_model.system_prompt


def test_data_gen_sample_task_input_default_values(base_task):
    # Act
    input_model = DataGenSampleTaskInput.from_task(task=base_task)

    # Assert
    assert input_model.num_samples == 8
    assert input_model.human_guidance is None
    assert input_model.topic == []


def test_data_gen_sample_task_initialization(base_task):
    # Act
    task = DataGenSampleTask(target_task=base_task)

    # Assert
    assert task.name == "DataGenSample"
    assert isinstance(task.parent, Project)
    assert task.description is not None
    assert task.instruction is not None

    input_schema = json.loads(task.input_json_schema)
    output_schema = json.loads(task.output_json_schema)

    assert isinstance(input_schema, dict)
    assert isinstance(output_schema, dict)
    assert output_schema["type"] == "object"
    assert output_schema["properties"]["generated_samples"]["type"] == "array"
    assert input_schema["properties"]["topic"]["type"] == "array"
    assert input_schema["properties"]["num_samples"]["type"] == "integer"
    assert set(input_schema["required"]) == {
        "topic",
        "num_samples",
        "system_prompt",
    }


def test_list_json_schema_for_task_with_input_schema(base_task):
    # Arrange
    base_task.input_json_schema = json.dumps(
        {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
        }
    )

    # Act
    schema = list_json_schema_for_task(base_task)
    parsed_schema = json.loads(schema)

    # Assert
    assert parsed_schema["type"] == "object"
    generated_samples_schema = parsed_schema["properties"]["generated_samples"]
    assert generated_samples_schema["type"] == "array"
    assert generated_samples_schema["items"]["type"] == "object"
    assert generated_samples_schema["items"]["properties"]["name"]["type"] == "string"
    assert generated_samples_schema["items"]["properties"]["age"]["type"] == "integer"


def test_list_json_schema_for_task_with_input_schema_non_ascii(base_task):
    # Arrange
    base_task.input_json_schema = json.dumps(
        {
            "type": "object",
            "properties": {
                "名字": {"type": "string"},
                "年齢": {"type": "integer"},
            },
        }
    )

    # Act
    schema = list_json_schema_for_task(base_task)

    # Assert
    assert "名字" in schema
    assert "年齢" in schema


def test_list_json_schema_for_task_without_input_schema(base_task):
    # Arrange
    base_task.input_json_schema = None

    # Act
    schema = list_json_schema_for_task(base_task)
    parsed_schema = json.loads(schema)

    # Assert
    assert parsed_schema["type"] == "object"
    assert parsed_schema["properties"]["generated_samples"]["type"] == "array"
    assert parsed_schema["properties"]["generated_samples"]["items"]["type"] == "string"


@pytest.mark.paid
@pytest.mark.ollama
@pytest.mark.parametrize("model_name,provider_name", get_all_models_and_providers())
async def test_data_gen_sample_all_models_providers(
    tmp_path, model_name, provider_name, base_task
):
    _, provider = get_model_and_provider(model_name, provider_name)
    if not provider.supports_data_gen:
        # pass if the model doesn't support data gen (testing the support flag is part of this)
        return

    data_gen_task = DataGenSampleTask(target_task=base_task)
    data_gen_input = DataGenSampleTaskInput.from_task(
        base_task, topic=["riding horses"], num_samples=4
    )

    adapter = adapter_for_task(
        data_gen_task,
        model_name=model_name,
        provider=provider_name,
    )

    input_dict = data_gen_input.model_dump()
    run = await adapter.invoke(input_dict)
    parsed_output = json.loads(run.output.output)
    samples = parsed_output["generated_samples"]
    assert len(samples) == 4
    for sample in samples:
        assert isinstance(sample, str)


@pytest.mark.paid
@pytest.mark.ollama
@pytest.mark.parametrize("model_name,provider_name", get_all_models_and_providers())
async def test_data_gen_sample_all_models_providers_with_structured_output(
    tmp_path, model_name, provider_name
):
    project = Project(name="TestProject")
    task = Task(
        name="Summarize",
        parent=project,
        description="Explain if the username matches the tweet",
        instruction="Explain if the username matches the tweet",
        requirements=[],
        input_json_schema=json.dumps(
            {
                "type": "object",
                "properties": {
                    "username": {"type": "string"},
                    "tweet": {"type": "string"},
                },
                "required": ["username", "tweet"],
            }
        ),
    )

    _, provider = get_model_and_provider(model_name, provider_name)
    if not provider.supports_data_gen:
        # pass if the model doesn't support data gen (testing the support flag is part of this)
        return

    data_gen_task = DataGenSampleTask(target_task=task)
    data_gen_input = DataGenSampleTaskInput.from_task(
        task, topic=["Food"], num_samples=4
    )

    adapter = adapter_for_task(
        data_gen_task,
        model_name=model_name,
        provider=provider_name,
    )

    input_dict = data_gen_input.model_dump()
    run = await adapter.invoke(input_dict)
    parsed_output = json.loads(run.output.output)
    samples = parsed_output["generated_samples"]
    assert len(samples) == 4
    for sample in samples:
        assert isinstance(sample, dict)
        assert "username" in sample
        assert "tweet" in sample
        assert isinstance(sample["username"], str)
        assert isinstance(sample["tweet"], str)
