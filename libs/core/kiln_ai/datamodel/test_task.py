import pytest
from pydantic import ValidationError

from kiln_ai.datamodel.datamodel_enums import StructuredOutputMode, TaskOutputRatingType
from kiln_ai.datamodel.prompt_id import PromptGenerators
from kiln_ai.datamodel.task import RunConfig, RunConfigProperties, Task, TaskRunConfig
from kiln_ai.datamodel.task_output import normalize_rating


def test_runconfig_valid_creation():
    task = Task(id="task1", name="Test Task", instruction="Do something")

    config = RunConfig(
        task=task,
        model_name="gpt-4",
        model_provider_name="openai",
        prompt_id=PromptGenerators.SIMPLE,
    )

    assert config.task == task
    assert config.model_name == "gpt-4"
    assert config.model_provider_name == "openai"
    assert config.prompt_id == PromptGenerators.SIMPLE  # Check default value


def test_runconfig_missing_required_fields():
    with pytest.raises(ValidationError) as exc_info:
        RunConfig()

    errors = exc_info.value.errors()
    assert (
        len(errors) == 4
    )  # task, model_name, model_provider_name, and prompt_id are required
    assert any(error["loc"][0] == "task" for error in errors)
    assert any(error["loc"][0] == "model_name" for error in errors)
    assert any(error["loc"][0] == "model_provider_name" for error in errors)
    assert any(error["loc"][0] == "prompt_id" for error in errors)


def test_runconfig_custom_prompt_id():
    task = Task(id="task1", name="Test Task", instruction="Do something")

    config = RunConfig(
        task=task,
        model_name="gpt-4",
        model_provider_name="openai",
        prompt_id=PromptGenerators.SIMPLE_CHAIN_OF_THOUGHT,
    )

    assert config.prompt_id == PromptGenerators.SIMPLE_CHAIN_OF_THOUGHT


@pytest.fixture
def sample_task():
    return Task(name="Test Task", instruction="Test instruction")


@pytest.fixture
def sample_run_config_props(sample_task):
    return RunConfigProperties(
        model_name="gpt-4",
        model_provider_name="openai",
        prompt_id=PromptGenerators.SIMPLE,
    )


def test_task_run_config_valid_creation(sample_task, sample_run_config_props):
    config = TaskRunConfig(
        name="Test Config",
        description="Test description",
        run_config_properties=sample_run_config_props,
        parent=sample_task,
    )

    assert config.name == "Test Config"
    assert config.description == "Test description"
    assert config.run_config_properties == sample_run_config_props
    assert config.parent_task() == sample_task


def test_task_run_config_minimal_creation(sample_task, sample_run_config_props):
    # Test creation with only required fields
    config = TaskRunConfig(
        name="Test Config",
        run_config_properties=sample_run_config_props,
        parent=sample_task,
    )

    assert config.name == "Test Config"
    assert config.description is None
    assert config.run_config_properties == sample_run_config_props


def test_task_run_config_missing_required_fields(sample_task):
    # Test missing name
    with pytest.raises(ValidationError) as exc_info:
        TaskRunConfig(
            run_config_properties=RunConfigProperties(
                task=sample_task, model_name="gpt-4", model_provider_name="openai"
            ),
            parent=sample_task,
        )
    assert "Field required" in str(exc_info.value)

    # Test missing run_config
    with pytest.raises(ValidationError) as exc_info:
        TaskRunConfig(name="Test Config", parent=sample_task)
    assert "Field required" in str(exc_info.value)


def test_task_run_config_missing_task_in_run_config(sample_task):
    with pytest.raises(
        ValidationError, match="Input should be a valid dictionary or instance of Task"
    ):
        # Create a run config without a task
        RunConfig(
            model_name="gpt-4",
            model_provider_name="openai",
            task=None,  # type: ignore
        )


@pytest.mark.parametrize(
    "rating_type,rating,expected",
    [
        (TaskOutputRatingType.five_star, 1, 0),
        (TaskOutputRatingType.five_star, 2, 0.25),
        (TaskOutputRatingType.five_star, 3, 0.5),
        (TaskOutputRatingType.five_star, 4, 0.75),
        (TaskOutputRatingType.five_star, 5, 1),
        (TaskOutputRatingType.pass_fail, 0, 0),
        (TaskOutputRatingType.pass_fail, 1, 1),
        (TaskOutputRatingType.pass_fail, 0.5, 0.5),
        (TaskOutputRatingType.pass_fail_critical, -1, 0),
        (TaskOutputRatingType.pass_fail_critical, 0, 0.5),
        (TaskOutputRatingType.pass_fail_critical, 1, 1),
        (TaskOutputRatingType.pass_fail_critical, 0.5, 0.75),
    ],
)
def test_normalize_rating(rating_type, rating, expected):
    assert normalize_rating(rating, rating_type) == expected


@pytest.mark.parametrize(
    "rating_type,rating",
    [
        (TaskOutputRatingType.five_star, 0),
        (TaskOutputRatingType.five_star, 6),
        (TaskOutputRatingType.pass_fail, -0.5),
        (TaskOutputRatingType.pass_fail, 1.5),
        (TaskOutputRatingType.pass_fail_critical, -1.5),
        (TaskOutputRatingType.pass_fail_critical, 1.5),
        (TaskOutputRatingType.custom, 0),
        (TaskOutputRatingType.custom, 99),
    ],
)
def test_normalize_rating_errors(rating_type, rating):
    with pytest.raises(ValueError):
        normalize_rating(rating, rating_type)


def test_run_config_defaults():
    """RunConfig should require top_p, temperature, and structured_output_mode to be set."""
    task = Task(id="task1", name="Test Task", instruction="Do something")

    config = RunConfig(
        task=task,
        model_name="gpt-4",
        model_provider_name="openai",
        prompt_id=PromptGenerators.SIMPLE,
    )
    assert config.top_p == 1.0
    assert config.temperature == 1.0
    assert config.structured_output_mode == StructuredOutputMode.default


def test_run_config_valid_ranges():
    """RunConfig should accept valid ranges for top_p and temperature."""
    task = Task(id="task1", name="Test Task", instruction="Do something")

    # Test valid values
    config = RunConfig(
        task=task,
        model_name="gpt-4",
        model_provider_name="openai",
        prompt_id=PromptGenerators.SIMPLE,
        top_p=0.9,
        temperature=0.7,
        structured_output_mode=StructuredOutputMode.json_schema,
    )

    assert config.top_p == 0.9
    assert config.temperature == 0.7
    assert config.structured_output_mode == StructuredOutputMode.json_schema


@pytest.mark.parametrize("top_p", [0.0, 0.5, 1.0])
def test_run_config_valid_top_p(top_p):
    """Test that RunConfig accepts valid top_p values (0-1)."""
    task = Task(id="task1", name="Test Task", instruction="Do something")

    config = RunConfig(
        task=task,
        model_name="gpt-4",
        model_provider_name="openai",
        prompt_id=PromptGenerators.SIMPLE,
        top_p=top_p,
        temperature=1.0,
        structured_output_mode=StructuredOutputMode.json_schema,
    )

    assert config.top_p == top_p


@pytest.mark.parametrize("top_p", [-0.1, 1.1, 2.0])
def test_run_config_invalid_top_p(top_p):
    """Test that RunConfig rejects invalid top_p values."""
    task = Task(id="task1", name="Test Task", instruction="Do something")

    with pytest.raises(ValueError, match="top_p must be between 0 and 1"):
        RunConfig(
            task=task,
            model_name="gpt-4",
            model_provider_name="openai",
            prompt_id=PromptGenerators.SIMPLE,
            top_p=top_p,
            temperature=1.0,
            structured_output_mode=StructuredOutputMode.json_schema,
        )


@pytest.mark.parametrize("temperature", [0.0, 1.0, 2.0])
def test_run_config_valid_temperature(temperature):
    """Test that RunConfig accepts valid temperature values (0-2)."""
    task = Task(id="task1", name="Test Task", instruction="Do something")

    config = RunConfig(
        task=task,
        model_name="gpt-4",
        model_provider_name="openai",
        prompt_id=PromptGenerators.SIMPLE,
        top_p=0.9,
        temperature=temperature,
        structured_output_mode=StructuredOutputMode.json_schema,
    )

    assert config.temperature == temperature


@pytest.mark.parametrize("temperature", [-0.1, 2.1, 3.0])
def test_run_config_invalid_temperature(temperature):
    """Test that RunConfig rejects invalid temperature values."""
    task = Task(id="task1", name="Test Task", instruction="Do something")

    with pytest.raises(ValueError, match="temperature must be between 0 and 2"):
        RunConfig(
            task=task,
            model_name="gpt-4",
            model_provider_name="openai",
            prompt_id=PromptGenerators.SIMPLE,
            top_p=0.9,
            temperature=temperature,
            structured_output_mode=StructuredOutputMode.json_schema,
        )
