import json

import pytest

from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.data_gen.data_gen_prompts import (
    generate_sample_generation_prompt,
    generate_topic_tree_prompt,
)
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
from kiln_ai.datamodel.task import RunConfigProperties


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

    # Act
    input_model = DataGenCategoriesTaskInput.from_task(
        task=base_task,
        node_path=node_path,
        num_subtopics=num_subtopics,
    )

    # Assert
    assert input_model.kiln_data_gen_topic_path == node_path
    assert input_model.kiln_data_gen_num_subtopics == num_subtopics
    assert isinstance(input_model.kiln_data_gen_system_prompt, str)
    assert "Reply like a cowboy" in input_model.kiln_data_gen_system_prompt


def test_data_gen_categories_task_input_default_values(base_task):
    # Act
    input_model = DataGenCategoriesTaskInput.from_task(task=base_task)

    # Assert
    assert input_model.kiln_data_gen_num_subtopics == 6
    assert input_model.kiln_data_gen_topic_path == []


def test_data_gen_categories_task_initialization():
    # Act
    task = DataGenCategoriesTask(gen_type="training", guidance="Test guidance")

    # Assert
    assert task.name == "DataGen"
    assert isinstance(task.parent, Project)
    assert task.description is not None
    assert task.instruction is not None
    assert isinstance(task.input_json_schema, str)
    assert isinstance(task.output_json_schema, str)
    assert "I want to train a large language model" in task.instruction
    assert "Test guidance" in task.instruction


def test_data_gen_categories_task_schemas():
    # Act
    task = DataGenCategoriesTask(gen_type="eval", guidance="Test guidance")

    assert "I want to evaluate a large language model" in task.instruction
    assert "Test guidance" in task.instruction

    # Assert
    input_schema = json.loads(task.input_json_schema)
    output_schema = json.loads(task.output_json_schema)

    assert isinstance(input_schema, dict)
    assert isinstance(output_schema, dict)
    assert output_schema["type"] == "object"
    assert output_schema["properties"]["subtopics"]["type"] == "array"
    assert input_schema["properties"]["kiln_data_gen_topic_path"]["type"] == "array"
    assert (
        input_schema["properties"]["kiln_data_gen_num_subtopics"]["type"] == "integer"
    )
    assert set(input_schema["required"]) == {
        "kiln_data_gen_topic_path",
        "kiln_data_gen_num_subtopics",
        "kiln_data_gen_system_prompt",
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

    data_gen_task = DataGenCategoriesTask(gen_type="training", guidance=None)
    data_gen_input = DataGenCategoriesTaskInput.from_task(base_task, num_subtopics=6)

    adapter = adapter_for_task(
        data_gen_task,
        run_config_properties=RunConfigProperties(
            model_name=model_name,
            model_provider_name=provider_name,
            prompt_id="simple_prompt_builder",
            structured_output_mode="unknown",
        ),
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

    # Act
    input_model = DataGenSampleTaskInput.from_task(
        task=base_task,
        topic=topic,
        num_samples=num_samples,
    )

    # Assert
    assert input_model.kiln_data_gen_topic_path == topic
    assert input_model.kiln_data_gen_num_samples == num_samples
    assert isinstance(input_model.kiln_data_gen_system_prompt, str)
    assert "Reply like a cowboy" in input_model.kiln_data_gen_system_prompt


def test_data_gen_sample_task_input_default_values(base_task):
    # Act
    input_model = DataGenSampleTaskInput.from_task(task=base_task)

    # Assert
    assert input_model.kiln_data_gen_num_samples == 8
    assert input_model.kiln_data_gen_topic_path == []


def test_data_gen_sample_task_initialization(base_task):
    # Act
    task = DataGenSampleTask(
        target_task=base_task, gen_type="eval", guidance="Test guidance"
    )

    # Assert
    assert task.name == "DataGenSample"
    assert isinstance(task.parent, Project)
    assert task.description is not None
    assert task.instruction is not None
    assert "I want to evaluate a large language model" in task.instruction
    assert "Test guidance" in task.instruction

    input_schema = json.loads(task.input_json_schema)
    output_schema = json.loads(task.output_json_schema)

    assert isinstance(input_schema, dict)
    assert isinstance(output_schema, dict)
    assert output_schema["type"] == "object"
    assert output_schema["properties"]["generated_samples"]["type"] == "array"
    assert input_schema["properties"]["kiln_data_gen_topic_path"]["type"] == "array"
    assert input_schema["properties"]["kiln_data_gen_num_samples"]["type"] == "integer"
    assert set(input_schema["required"]) == {
        "kiln_data_gen_topic_path",
        "kiln_data_gen_num_samples",
        "kiln_data_gen_system_prompt",
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
    if provider is None or not provider.supports_data_gen:
        # pass if the model doesn't support data gen (testing the support flag is part of this)
        return

    data_gen_task = DataGenSampleTask(
        target_task=base_task, gen_type="training", guidance=None
    )
    data_gen_input = DataGenSampleTaskInput.from_task(
        base_task, topic=["riding horses"], num_samples=4
    )

    adapter = adapter_for_task(
        data_gen_task,
        run_config_properties=RunConfigProperties(
            model_name=model_name,
            model_provider_name=provider_name,
            prompt_id="simple_prompt_builder",
            structured_output_mode="unknown",
        ),
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

    data_gen_task = DataGenSampleTask(
        target_task=task, gen_type="training", guidance=None
    )
    data_gen_input = DataGenSampleTaskInput.from_task(
        task, topic=["Food"], num_samples=4
    )

    adapter = adapter_for_task(
        data_gen_task,
        run_config_properties=RunConfigProperties(
            model_name=model_name,
            model_provider_name=provider_name,
            prompt_id="simple_prompt_builder",
            structured_output_mode="unknown",
        ),
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


def test_generate_topic_tree_prompt_training_type():
    """Test generate_topic_tree_prompt with gen_type='training'"""
    # Act
    prompt = generate_topic_tree_prompt(gen_type="training")

    # Assert
    assert isinstance(prompt, str)
    assert (
        "I want to train a large language model and you should help me generate training data for it."
        in prompt
    )
    assert "## Task Description" in prompt
    assert "Your job is the following:" in prompt
    assert "## Next Step" in prompt
    assert "When generating subtopics, remain somewhat vague." in prompt
    assert "The guidance is:" not in prompt  # Should not have specific guidance


def test_generate_topic_tree_prompt_eval_type():
    """Test generate_topic_tree_prompt with gen_type='eval'"""
    # Act
    prompt = generate_topic_tree_prompt(gen_type="eval")

    # Assert
    assert isinstance(prompt, str)
    assert (
        "I want to evaluate a large language model and you should help me generate eval data for it."
        in prompt
    )
    assert "## Task Description" in prompt
    assert "Your job is the following:" in prompt
    assert "## Next Step" in prompt
    assert "When generating subtopics, remain somewhat vague." in prompt
    assert "The guidance is:" not in prompt  # Should not have specific guidance


def test_generate_topic_tree_prompt_with_guidance():
    """Test generate_topic_tree_prompt with guidance provided"""
    # Arrange
    guidance = "Focus on technical topics related to artificial intelligence and machine learning"

    # Act
    prompt = generate_topic_tree_prompt(gen_type="training", guidance=guidance)

    # Assert
    assert isinstance(prompt, str)
    assert (
        "I want to train a large language model and you should help me generate training data for it."
        in prompt
    )
    assert "## Custom Guidance" in prompt
    assert f"<guidance>\n{guidance}\n</guidance>" in prompt
    assert (
        "When generating subtopics, remain somewhat vague." not in prompt
    )  # Should not have default guidance


def test_generate_topic_tree_prompt_with_empty_guidance():
    """Test generate_topic_tree_prompt with empty string guidance"""
    # Act
    prompt = generate_topic_tree_prompt(gen_type="eval", guidance="")

    # Assert
    assert isinstance(prompt, str)
    assert (
        "I want to evaluate a large language model and you should help me generate eval data for it."
        in prompt
    )
    assert "## Specific Guidance" not in prompt
    assert (
        "When generating subtopics, remain somewhat vague." in prompt
    )  # Should have default guidance


def test_generate_topic_tree_prompt_contains_examples():
    """Test that the prompt contains the expected examples"""
    # Act
    prompt = generate_topic_tree_prompt(gen_type="training")

    # Assert
    # Check for news examples
    assert "News Topics" in prompt
    assert "Sports" in prompt
    assert "Football" in prompt
    assert "College Football" in prompt
    assert "Entertainment" in prompt
    assert "Tom Hanks" in prompt

    # Check for smalltalk examples
    assert "Small Talk Topics" in prompt
    assert "Weather" in prompt
    assert "Family" in prompt
    assert "Hobbies" in prompt
    assert "Cooking" in prompt
    assert "Asian Food" in prompt


def test_generate_topic_tree_prompt_contains_required_sections():
    """Test that the prompt contains all required sections"""
    # Act
    prompt = generate_topic_tree_prompt(gen_type="training")

    # Assert
    assert "## Task Description" in prompt
    assert "## Next Step" in prompt
    assert "system_prompt" in prompt
    assert "kiln_data_gen_topic_path" in prompt
    assert "kiln_data_gen_num_subtopics" in prompt
    assert "existing_topics" in prompt


def test_generate_topic_tree_prompt_structure_consistency():
    """Test that the prompt structure is consistent between training and eval types"""
    # Act
    training_prompt = generate_topic_tree_prompt(gen_type="training")
    eval_prompt = generate_topic_tree_prompt(gen_type="eval")

    # Assert
    # Both should have the same structure, just different goal descriptions
    assert "## Task Description" in training_prompt
    assert "## Task Description" in eval_prompt
    assert "## Next Step" in training_prompt
    assert "## Next Step" in eval_prompt

    # The main difference should be in the goal description
    assert "train a large language model" in training_prompt
    assert "evaluate a large language model" in eval_prompt
    assert "generate training data" in training_prompt
    assert "generate eval data" in eval_prompt


def test_generate_sample_generation_prompt_training_type():
    """Test generate_sample_generation_prompt with gen_type='training'"""
    # Act
    prompt = generate_sample_generation_prompt(gen_type="training")

    # Assert
    assert isinstance(prompt, str)
    assert (
        "I want to train a large language model and you should help me generate training data for it."
        in prompt
    )
    assert "## Task Description" in prompt
    assert "Your job is to generate a list of potential inputs" in prompt
    assert "The guidance is:" not in prompt  # Should not have specific guidance


def test_generate_sample_generation_prompt_eval_type():
    """Test generate_sample_generation_prompt with gen_type='eval'"""
    # Act
    prompt = generate_sample_generation_prompt(gen_type="eval")

    # Assert
    assert isinstance(prompt, str)
    assert (
        "I want to evaluate a large language model and you should help me generate eval data for it."
        in prompt
    )
    assert "## Task Description" in prompt
    assert "Your job is to generate a list of potential inputs" in prompt
    assert "The guidance is:" not in prompt  # Should not have specific guidance


def test_generate_sample_generation_prompt_with_guidance():
    """Test generate_sample_generation_prompt with guidance provided"""
    # Arrange
    guidance = "Focus on generating diverse examples with varying complexity levels"

    # Act
    prompt = generate_sample_generation_prompt(gen_type="training", guidance=guidance)

    # Assert
    assert isinstance(prompt, str)
    assert (
        "I want to train a large language model and you should help me generate training data for it."
        in prompt
    )
    assert "## Custom Guidance" in prompt
    assert f"<guidance>\n{guidance}\n</guidance>" in prompt


def test_generate_sample_generation_prompt_with_empty_guidance():
    """Test generate_sample_generation_prompt with empty string guidance"""
    # Act
    prompt = generate_sample_generation_prompt(gen_type="eval", guidance="")

    # Assert
    assert isinstance(prompt, str)
    assert (
        "I want to evaluate a large language model and you should help me generate eval data for it."
        in prompt
    )
    assert "## Specific Guidance" not in prompt


def test_generate_sample_generation_prompt_contains_examples():
    """Test that the prompt contains the expected examples"""
    # Act
    prompt = generate_sample_generation_prompt(gen_type="training")

    # Assert
    # Check for the tweet classification example
    assert "You are an assistant that classifies the tone of a tweet" in prompt
    assert "positive" in prompt
    assert "negative" in prompt
    assert "neutral" in prompt
    assert "Technology" in prompt
    assert "New iPhone Event" in prompt
    assert "New iPhone looks amazing! I need that camera." in prompt
    assert "Another boring event from Apple." in prompt


def test_generate_sample_generation_prompt_contains_required_sections():
    """Test that the prompt contains all required sections"""
    # Act
    prompt = generate_sample_generation_prompt(gen_type="training")

    # Assert
    assert "## Task Description" in prompt
    assert "system_prompt" in prompt
    assert "topic" in prompt
    assert "num_samples" in prompt
    assert "generated_samples" in prompt
    assert "The output must be formatted:" in prompt
    assert "Do not include any other text or break the schema in any way." in prompt
    assert (
        "Note how the output of this task is data to input into the system prompt"
        in prompt
    )


def test_generate_sample_generation_prompt_structure_consistency():
    """Test that the prompt structure is consistent between training and eval types"""
    # Act
    training_prompt = generate_sample_generation_prompt(gen_type="training")
    eval_prompt = generate_sample_generation_prompt(gen_type="eval")

    # Assert
    # Both should have the same structure, just different goal descriptions
    assert "## Task Description" in training_prompt
    assert "## Task Description" in eval_prompt

    # The main difference should be in the goal description
    assert "train a large language model" in training_prompt
    assert "evaluate a large language model" in eval_prompt
    assert "generate training data" in training_prompt
    assert "generate eval data" in eval_prompt

    # Both should have the same core content
    assert "Your job is to generate a list of potential inputs" in training_prompt
    assert "Your job is to generate a list of potential inputs" in eval_prompt
    assert "generated_samples" in training_prompt
    assert "generated_samples" in eval_prompt


def test_generate_sample_generation_prompt_with_none_guidance():
    """Test generate_sample_generation_prompt with None guidance"""
    # Act
    prompt = generate_sample_generation_prompt(gen_type="training", guidance=None)

    # Assert
    assert isinstance(prompt, str)
    assert (
        "I want to train a large language model and you should help me generate training data for it."
        in prompt
    )
    assert "## Specific Guidance" not in prompt
    assert "The guidance is:" not in prompt
