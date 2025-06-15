import json
from unittest.mock import Mock, patch

import litellm
import pytest

from kiln_ai.adapters.ml_model_list import ModelProviderName, StructuredOutputMode
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig
from kiln_ai.adapters.model_adapters.litellm_adapter import LiteLlmAdapter
from kiln_ai.adapters.model_adapters.litellm_config import (
    LiteLlmConfig,
)
from kiln_ai.datamodel import Project, Task, Usage
from kiln_ai.datamodel.task import RunConfigProperties


@pytest.fixture
def mock_task(tmp_path):
    # Create a project first since Task requires a parent
    project_path = tmp_path / "test_project" / "project.kiln"
    project_path.parent.mkdir()

    project = Project(name="Test Project", path=str(project_path))
    project.save_to_file()

    schema = {
        "type": "object",
        "properties": {"test": {"type": "string"}},
    }

    task = Task(
        name="Test Task",
        instruction="Test instruction",
        parent=project,
        output_json_schema=json.dumps(schema),
    )
    task.save_to_file()
    return task


@pytest.fixture
def config():
    return LiteLlmConfig(
        base_url="https://api.test.com",
        run_config_properties=RunConfigProperties(
            model_name="test-model",
            model_provider_name="openrouter",
            prompt_id="simple_prompt_builder",
            structured_output_mode="json_schema",
        ),
        default_headers={"X-Test": "test"},
        additional_body_options={"api_key": "test_key"},
    )


def test_initialization(config, mock_task):
    adapter = LiteLlmAdapter(
        config=config,
        kiln_task=mock_task,
        base_adapter_config=AdapterConfig(default_tags=["test-tag"]),
    )

    assert adapter.config == config
    assert adapter.run_config.task == mock_task
    assert adapter.run_config.prompt_id == "simple_prompt_builder"
    assert adapter.base_adapter_config.default_tags == ["test-tag"]
    assert adapter.run_config.model_name == config.run_config_properties.model_name
    assert (
        adapter.run_config.model_provider_name
        == config.run_config_properties.model_provider_name
    )
    assert adapter.config.additional_body_options["api_key"] == "test_key"
    assert adapter._api_base == config.base_url
    assert adapter._headers == config.default_headers


def test_adapter_info(config, mock_task):
    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)

    assert adapter.adapter_name() == "kiln_openai_compatible_adapter"

    assert adapter.run_config.model_name == config.run_config_properties.model_name
    assert (
        adapter.run_config.model_provider_name
        == config.run_config_properties.model_provider_name
    )
    assert adapter.run_config.prompt_id == "simple_prompt_builder"


@pytest.mark.asyncio
async def test_response_format_options_unstructured(config, mock_task):
    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)

    # Mock has_structured_output to return False
    with patch.object(adapter, "has_structured_output", return_value=False):
        options = await adapter.response_format_options()
        assert options == {}


@pytest.mark.parametrize(
    "mode",
    [
        StructuredOutputMode.json_mode,
        StructuredOutputMode.json_instruction_and_object,
    ],
)
@pytest.mark.asyncio
async def test_response_format_options_json_mode(config, mock_task, mode):
    config.run_config_properties.structured_output_mode = mode
    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)

    with (
        patch.object(adapter, "has_structured_output", return_value=True),
    ):
        options = await adapter.response_format_options()
        assert options == {"response_format": {"type": "json_object"}}


@pytest.mark.parametrize(
    "mode",
    [
        StructuredOutputMode.default,
        StructuredOutputMode.function_calling,
    ],
)
@pytest.mark.asyncio
async def test_response_format_options_function_calling(config, mock_task, mode):
    config.run_config_properties.structured_output_mode = mode
    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)

    with (
        patch.object(adapter, "has_structured_output", return_value=True),
    ):
        options = await adapter.response_format_options()
        assert "tools" in options
        # full tool structure validated below


@pytest.mark.parametrize(
    "mode",
    [
        StructuredOutputMode.json_custom_instructions,
        StructuredOutputMode.json_instructions,
    ],
)
@pytest.mark.asyncio
async def test_response_format_options_json_instructions(config, mock_task, mode):
    config.run_config_properties.structured_output_mode = mode
    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)

    with (
        patch.object(adapter, "has_structured_output", return_value=True),
    ):
        options = await adapter.response_format_options()
        assert options == {}


@pytest.mark.asyncio
async def test_response_format_options_json_schema(config, mock_task):
    config.run_config_properties.structured_output_mode = (
        StructuredOutputMode.json_schema
    )
    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)

    with (
        patch.object(adapter, "has_structured_output", return_value=True),
    ):
        options = await adapter.response_format_options()
        assert options == {
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "task_response",
                    "schema": mock_task.output_schema(),
                },
            }
        }


def test_tool_call_params_weak(config, mock_task):
    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)

    params = adapter.tool_call_params(strict=False)
    expected_schema = mock_task.output_schema()
    expected_schema["additionalProperties"] = False

    assert params == {
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "task_response",
                    "parameters": expected_schema,
                },
            }
        ],
        "tool_choice": {
            "type": "function",
            "function": {"name": "task_response"},
        },
    }


def test_tool_call_params_strict(config, mock_task):
    config.provider_name = "openai"
    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)

    params = adapter.tool_call_params(strict=True)
    expected_schema = mock_task.output_schema()
    expected_schema["additionalProperties"] = False

    assert params == {
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "task_response",
                    "parameters": expected_schema,
                    "strict": True,
                },
            }
        ],
        "tool_choice": {
            "type": "function",
            "function": {"name": "task_response"},
        },
    }


@pytest.mark.parametrize(
    "provider_name,expected_prefix",
    [
        (ModelProviderName.openrouter, "openrouter"),
        (ModelProviderName.openai, "openai"),
        (ModelProviderName.groq, "groq"),
        (ModelProviderName.anthropic, "anthropic"),
        (ModelProviderName.ollama, "openai"),
        (ModelProviderName.gemini_api, "gemini"),
        (ModelProviderName.fireworks_ai, "fireworks_ai"),
        (ModelProviderName.amazon_bedrock, "bedrock"),
        (ModelProviderName.azure_openai, "azure"),
        (ModelProviderName.huggingface, "huggingface"),
        (ModelProviderName.vertex, "vertex_ai"),
        (ModelProviderName.together_ai, "together_ai"),
    ],
)
def test_litellm_model_id_standard_providers(
    config, mock_task, provider_name, expected_prefix
):
    """Test litellm_model_id for standard providers"""
    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)

    # Mock the model_provider method to return a provider with the specified name
    mock_provider = Mock()
    mock_provider.name = provider_name
    mock_provider.model_id = "test-model"

    with patch.object(adapter, "model_provider", return_value=mock_provider):
        model_id = adapter.litellm_model_id()

    assert model_id == f"{expected_prefix}/test-model"
    # Verify caching works
    assert adapter._litellm_model_id == model_id


@pytest.mark.parametrize(
    "provider_name",
    [
        ModelProviderName.openai_compatible,
        ModelProviderName.kiln_custom_registry,
        ModelProviderName.kiln_fine_tune,
    ],
)
def test_litellm_model_id_custom_providers(config, mock_task, provider_name):
    """Test litellm_model_id for custom providers that require a base URL"""
    config.base_url = "https://api.custom.com"
    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)

    # Mock the model_provider method
    mock_provider = Mock()
    mock_provider.name = provider_name
    mock_provider.model_id = "custom-model"

    with patch.object(adapter, "model_provider", return_value=mock_provider):
        model_id = adapter.litellm_model_id()

    # Custom providers should use "openai" as the provider name
    assert model_id == "openai/custom-model"
    assert adapter._litellm_model_id == model_id


def test_litellm_model_id_custom_provider_no_base_url(config, mock_task):
    """Test litellm_model_id raises error for custom providers without base URL"""
    config.base_url = None
    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)

    # Mock the model_provider method
    mock_provider = Mock()
    mock_provider.name = ModelProviderName.openai_compatible
    mock_provider.model_id = "custom-model"

    with patch.object(adapter, "model_provider", return_value=mock_provider):
        with pytest.raises(ValueError, match="Explicit Base URL is required"):
            adapter.litellm_model_id()


def test_litellm_model_id_no_model_id(config, mock_task):
    """Test litellm_model_id raises error when provider has no model_id"""
    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)

    # Mock the model_provider method to return a provider with no model_id
    mock_provider = Mock()
    mock_provider.name = ModelProviderName.openai
    mock_provider.model_id = None

    with patch.object(adapter, "model_provider", return_value=mock_provider):
        with pytest.raises(ValueError, match="Model ID is required"):
            adapter.litellm_model_id()


def test_litellm_model_id_caching(config, mock_task):
    """Test that litellm_model_id caches the result"""
    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)

    # Set the cached value directly
    adapter._litellm_model_id = "cached-value"

    # The method should return the cached value without calling model_provider
    with patch.object(adapter, "model_provider") as mock_model_provider:
        model_id = adapter.litellm_model_id()

    assert model_id == "cached-value"
    mock_model_provider.assert_not_called()


def test_litellm_model_id_unknown_provider(config, mock_task):
    """Test litellm_model_id raises error for unknown provider"""
    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)

    # Create a mock provider with an unknown name
    mock_provider = Mock()
    mock_provider.name = "unknown_provider"  # Not in ModelProviderName enum
    mock_provider.model_id = "test-model"

    with patch.object(adapter, "model_provider", return_value=mock_provider):
        with patch(
            "kiln_ai.adapters.model_adapters.litellm_adapter.raise_exhaustive_enum_error"
        ) as mock_raise_error:
            mock_raise_error.side_effect = Exception("Test error")

            with pytest.raises(Exception, match="Test error"):
                adapter.litellm_model_id()


@pytest.mark.asyncio
async def test_build_completion_kwargs_custom_temperature_top_p(config, mock_task):
    """Test build_completion_kwargs with custom temperature and top_p values"""
    # Create config with custom temperature and top_p
    config.run_config_properties.temperature = 0.7
    config.run_config_properties.top_p = 0.9

    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)
    mock_provider = Mock()
    messages = [{"role": "user", "content": "Hello"}]

    with (
        patch.object(adapter, "model_provider", return_value=mock_provider),
        patch.object(adapter, "litellm_model_id", return_value="openai/test-model"),
        patch.object(adapter, "build_extra_body", return_value={}),
        patch.object(adapter, "response_format_options", return_value={}),
    ):
        kwargs = await adapter.build_completion_kwargs(mock_provider, messages, None)

    # Verify custom temperature and top_p are passed through
    assert kwargs["temperature"] == 0.7
    assert kwargs["top_p"] == 0.9
    # Verify drop_params is set correctly
    assert kwargs["drop_params"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "top_logprobs,response_format,extra_body",
    [
        (None, {}, {}),  # Basic case
        (5, {}, {}),  # With logprobs
        (
            None,
            {"response_format": {"type": "json_object"}},
            {},
        ),  # With response format
        (
            3,
            {"tools": [{"type": "function"}]},
            {"reasoning_effort": 0.8},
        ),  # Combined options
    ],
)
async def test_build_completion_kwargs(
    config, mock_task, top_logprobs, response_format, extra_body
):
    """Test build_completion_kwargs with various configurations"""
    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)
    mock_provider = Mock()
    messages = [{"role": "user", "content": "Hello"}]

    with (
        patch.object(adapter, "model_provider", return_value=mock_provider),
        patch.object(adapter, "litellm_model_id", return_value="openai/test-model"),
        patch.object(adapter, "build_extra_body", return_value=extra_body),
        patch.object(adapter, "response_format_options", return_value=response_format),
    ):
        kwargs = await adapter.build_completion_kwargs(
            mock_provider, messages, top_logprobs
        )

    # Verify core functionality
    assert kwargs["model"] == "openai/test-model"
    assert kwargs["messages"] == messages
    assert kwargs["api_base"] == config.base_url

    # Verify temperature and top_p are included with default values
    assert kwargs["temperature"] == 1.0  # Default from RunConfigProperties
    assert kwargs["top_p"] == 1.0  # Default from RunConfigProperties

    # Verify drop_params is set correctly
    assert kwargs["drop_params"] is True

    # Verify optional parameters
    if top_logprobs is not None:
        assert kwargs["logprobs"] is True
        assert kwargs["top_logprobs"] == top_logprobs
    else:
        assert "logprobs" not in kwargs
        assert "top_logprobs" not in kwargs

    # Verify response format is included
    for key, value in response_format.items():
        assert kwargs[key] == value

    # Verify extra body is included
    for key, value in extra_body.items():
        assert kwargs[key] == value


@pytest.mark.parametrize(
    "litellm_usage,cost,expected_usage",
    [
        # No usage data
        (None, None, None),
        # Only cost
        (None, 0.5, Usage(cost=0.5)),
        # Only token counts
        (
            litellm.types.utils.Usage(
                prompt_tokens=10,
                completion_tokens=20,
                total_tokens=30,
            ),
            None,
            Usage(input_tokens=10, output_tokens=20, total_tokens=30),
        ),
        # Both cost and token counts
        (
            litellm.types.utils.Usage(
                prompt_tokens=10,
                completion_tokens=20,
                total_tokens=30,
            ),
            0.5,
            Usage(input_tokens=10, output_tokens=20, total_tokens=30, cost=0.5),
        ),
        # Invalid usage type (should be ignored)
        ({"prompt_tokens": 10}, None, None),
        # Invalid cost type (should be ignored)
        (None, "0.5", None),
    ],
)
def test_usage_from_response(config, mock_task, litellm_usage, cost, expected_usage):
    """Test usage_from_response with various combinations of usage data and cost"""
    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)

    # Create a mock response
    response = Mock(spec=litellm.types.utils.ModelResponse)
    response.get.return_value = litellm_usage
    response._hidden_params = {"response_cost": cost}

    # Call the method
    result = adapter.usage_from_response(response)

    # Verify the result
    if expected_usage is None:
        if result is not None:
            assert result.input_tokens is None
            assert result.output_tokens is None
            assert result.total_tokens is None
            assert result.cost is None
    else:
        assert result is not None
        assert result.input_tokens == expected_usage.input_tokens
        assert result.output_tokens == expected_usage.output_tokens
        assert result.total_tokens == expected_usage.total_tokens
        assert result.cost == expected_usage.cost

    # Verify the response was queried correctly
    response.get.assert_called_once_with("usage", None)
