import json
from unittest.mock import Mock, patch

import litellm
import pytest
from litellm.types.utils import ChoiceLogprobs

from kiln_ai.adapters.ml_model_list import ModelProviderName, StructuredOutputMode
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig
from kiln_ai.adapters.model_adapters.litellm_adapter import LiteLlmAdapter
from kiln_ai.adapters.model_adapters.litellm_config import LiteLlmConfig
from kiln_ai.datamodel import Project, Task, Usage
from kiln_ai.datamodel.task import RunConfigProperties
from kiln_ai.tools.built_in_tools.math_tools import (
    AddTool,
    DivideTool,
    MultiplyTool,
    SubtractTool,
)


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
    assert adapter.task == mock_task
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
        # for openai-compatible providers, we expect openai as the provider name
        (ModelProviderName.siliconflow_cn, "openai"),
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


@pytest.mark.parametrize(
    "provider_name,expected_usage_param",
    [
        (ModelProviderName.openrouter, {"usage": {"include": True}}),
        (ModelProviderName.openai, {}),
        (ModelProviderName.anthropic, {}),
        (ModelProviderName.groq, {}),
    ],
)
def test_build_extra_body_openrouter_usage(
    config, mock_task, provider_name, expected_usage_param
):
    """Test build_extra_body includes usage parameter for OpenRouter providers"""
    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)

    # Create a mock provider with the specified name and minimal required attributes
    mock_provider = Mock()
    mock_provider.name = provider_name
    mock_provider.thinking_level = None
    mock_provider.require_openrouter_reasoning = False
    mock_provider.anthropic_extended_thinking = False
    mock_provider.r1_openrouter_options = False
    mock_provider.logprobs_openrouter_options = False
    mock_provider.openrouter_skip_required_parameters = False

    # Call build_extra_body
    extra_body = adapter.build_extra_body(mock_provider)

    # Verify the usage parameter is included only for OpenRouter
    for key, value in expected_usage_param.items():
        assert extra_body.get(key) == value

    # Verify non-OpenRouter providers don't have the usage parameter
    if provider_name != ModelProviderName.openrouter:
        assert "usage" not in extra_body


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
        # Cost in OpenRouter format
        (
            litellm.types.utils.Usage(
                prompt_tokens=10,
                completion_tokens=20,
                total_tokens=30,
                cost=0.5,
            ),
            None,
            Usage(input_tokens=10, output_tokens=20, total_tokens=30, cost=0.5),
        ),
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


@pytest.fixture
def mock_math_tools():
    """Create a list of 4 math tools for testing"""
    return [AddTool(), SubtractTool(), MultiplyTool(), DivideTool()]


async def test_litellm_tools_returns_openai_format_with_tools(
    config, mock_task, mock_math_tools
):
    """Test litellm_tools returns OpenAI formatted tool list when available_tools has tools"""
    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)

    with patch.object(adapter, "available_tools", return_value=mock_math_tools):
        tools = await adapter.litellm_tools()

    # Should return 4 tools
    assert len(tools) == 4

    # Each tool should have the OpenAI format
    for tool in tools:
        assert "type" in tool
        assert tool["type"] == "function"
        assert "function" in tool
        assert "name" in tool["function"]
        assert "description" in tool["function"]
        assert "parameters" in tool["function"]

    # Verify specific tools are present
    tool_names = [tool["function"]["name"] for tool in tools]
    assert "add" in tool_names
    assert "subtract" in tool_names
    assert "multiply" in tool_names
    assert "divide" in tool_names


async def test_litellm_tools_returns_empty_list_without_tools(config, mock_task):
    """Test litellm_tools returns empty list when available_tools has no tools"""
    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)

    with patch.object(adapter, "available_tools", return_value=[]):
        tools = await adapter.litellm_tools()

    assert tools == []


@pytest.mark.asyncio
async def test_build_completion_kwargs_includes_tools(
    config, mock_task, mock_math_tools
):
    """Test build_completion_kwargs includes tools when available_tools has tools"""
    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)
    mock_provider = Mock()
    messages = [{"role": "user", "content": "Hello"}]

    with (
        patch.object(adapter, "model_provider", return_value=mock_provider),
        patch.object(adapter, "litellm_model_id", return_value="openai/test-model"),
        patch.object(adapter, "build_extra_body", return_value={}),
        patch.object(adapter, "response_format_options", return_value={}),
        patch.object(adapter, "available_tools", return_value=mock_math_tools),
    ):
        kwargs = await adapter.build_completion_kwargs(mock_provider, messages, None)

    # Should include tools
    assert "tools" in kwargs
    assert len(kwargs["tools"]) == 4
    assert "tool_choice" in kwargs
    assert kwargs["tool_choice"] == "auto"

    # Verify tools are properly formatted
    for tool in kwargs["tools"]:
        assert "type" in tool
        assert tool["type"] == "function"
        assert "function" in tool


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "structured_output_mode, expected_error_message",
    [
        (
            StructuredOutputMode.function_calling,
            "Function calling/tools can't be used as the JSON response format if you're also using tools",
        ),
        (
            StructuredOutputMode.function_calling_weak,
            "Function calling/tools can't be used as the JSON response format if you're also using tools",
        ),
        (
            StructuredOutputMode.json_instructions,
            None,
        ),
        (
            StructuredOutputMode.json_schema,
            None,
        ),
    ],
)
async def test_build_completion_kwargs_raises_error_with_tools_conflict(
    config, mock_task, mock_math_tools, structured_output_mode, expected_error_message
):
    """Test build_completion_kwargs raises error when structured output mode conflicts with available tools"""
    config.run_config_properties.structured_output_mode = structured_output_mode
    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)
    mock_provider = Mock()
    messages = [{"role": "user", "content": "Hello"}]

    with (
        patch.object(adapter, "model_provider", return_value=mock_provider),
        patch.object(adapter, "litellm_model_id", return_value="openai/test-model"),
        patch.object(adapter, "build_extra_body", return_value={}),
        patch.object(adapter, "available_tools", return_value=mock_math_tools),
    ):
        if expected_error_message is not None:
            with pytest.raises(
                ValueError,
                match=expected_error_message,
            ):
                await adapter.build_completion_kwargs(mock_provider, messages, None)
        else:
            # should not raise an error
            await adapter.build_completion_kwargs(mock_provider, messages, None)


class TestExtractAndValidateLogprobs:
    """Test cases for the _extract_and_validate_logprobs helper method"""

    @pytest.fixture
    def adapter_with_logprobs_required(self, config, mock_task):
        """Create an adapter with logprobs required"""
        base_config = AdapterConfig(top_logprobs=5)
        return LiteLlmAdapter(
            config=config, kiln_task=mock_task, base_adapter_config=base_config
        )

    @pytest.fixture
    def adapter_without_logprobs_required(self, config, mock_task):
        """Create an adapter without logprobs required"""
        base_config = AdapterConfig(top_logprobs=None)
        return LiteLlmAdapter(
            config=config, kiln_task=mock_task, base_adapter_config=base_config
        )

    def test_extract_logprobs_with_valid_logprobs(
        self, adapter_without_logprobs_required
    ):
        """Test extracting logprobs when final_choice has valid logprobs"""
        # Create a mock final_choice with valid logprobs
        mock_choice = Mock()
        mock_logprobs = Mock(spec=ChoiceLogprobs)
        mock_choice.logprobs = mock_logprobs

        result = adapter_without_logprobs_required._extract_and_validate_logprobs(
            mock_choice
        )

        assert result == mock_logprobs

    def test_extract_logprobs_with_none_choice(self, adapter_without_logprobs_required):
        """Test extracting logprobs when final_choice is None"""
        result = adapter_without_logprobs_required._extract_and_validate_logprobs(None)

        assert result is None

    def test_extract_logprobs_without_logprobs_attribute(
        self, adapter_without_logprobs_required
    ):
        """Test extracting logprobs when final_choice has no logprobs attribute"""
        mock_choice = Mock()
        # Don't add logprobs attribute

        result = adapter_without_logprobs_required._extract_and_validate_logprobs(
            mock_choice
        )

        assert result is None

    def test_extract_logprobs_with_non_choicelogprobs_type(
        self, adapter_without_logprobs_required
    ):
        """Test extracting logprobs when logprobs is not a ChoiceLogprobs instance"""
        mock_choice = Mock()
        mock_choice.logprobs = {"not": "a ChoiceLogprobs object"}

        result = adapter_without_logprobs_required._extract_and_validate_logprobs(
            mock_choice
        )

        assert result is None

    def test_extract_logprobs_with_none_logprobs(
        self, adapter_without_logprobs_required
    ):
        """Test extracting logprobs when logprobs attribute is None"""
        mock_choice = Mock()
        mock_choice.logprobs = None

        result = adapter_without_logprobs_required._extract_and_validate_logprobs(
            mock_choice
        )

        assert result is None

    def test_validate_logprobs_required_but_missing_raises_error(
        self, adapter_with_logprobs_required
    ):
        """Test that missing logprobs raises error when required"""
        mock_choice = Mock()
        # Don't add logprobs or make it None
        mock_choice.logprobs = None

        with pytest.raises(
            RuntimeError, match="Logprobs were required, but no logprobs were returned"
        ):
            adapter_with_logprobs_required._extract_and_validate_logprobs(mock_choice)

    def test_validate_logprobs_required_but_none_choice_raises_error(
        self, adapter_with_logprobs_required
    ):
        """Test that None choice raises error when logprobs are required"""
        with pytest.raises(
            RuntimeError, match="Logprobs were required, but no logprobs were returned"
        ):
            adapter_with_logprobs_required._extract_and_validate_logprobs(None)

    def test_validate_logprobs_required_but_wrong_type_raises_error(
        self, adapter_with_logprobs_required
    ):
        """Test that wrong logprobs type raises error when required"""
        mock_choice = Mock()
        mock_choice.logprobs = {"not": "a ChoiceLogprobs object"}

        with pytest.raises(
            RuntimeError, match="Logprobs were required, but no logprobs were returned"
        ):
            adapter_with_logprobs_required._extract_and_validate_logprobs(mock_choice)

    def test_validate_logprobs_required_and_present_succeeds(
        self, adapter_with_logprobs_required
    ):
        """Test that valid logprobs are returned when required and present"""
        mock_choice = Mock()
        mock_logprobs = Mock(spec=ChoiceLogprobs)
        mock_choice.logprobs = mock_logprobs

        result = adapter_with_logprobs_required._extract_and_validate_logprobs(
            mock_choice
        )

        assert result == mock_logprobs

    def test_validate_logprobs_not_required_missing_ok(
        self, adapter_without_logprobs_required
    ):
        """Test that missing logprobs is OK when not required"""
        mock_choice = Mock()
        mock_choice.logprobs = None

        result = adapter_without_logprobs_required._extract_and_validate_logprobs(
            mock_choice
        )

        assert result is None

    @pytest.mark.parametrize("top_logprobs_value", [0, 1, 5, 10])
    def test_validate_logprobs_various_top_logprobs_values(
        self, config, mock_task, top_logprobs_value
    ):
        """Test validation with various top_logprobs values"""
        base_config = AdapterConfig(top_logprobs=top_logprobs_value)
        adapter = LiteLlmAdapter(
            config=config, kiln_task=mock_task, base_adapter_config=base_config
        )

        mock_choice = Mock()
        mock_choice.logprobs = None

        with pytest.raises(
            RuntimeError, match="Logprobs were required, but no logprobs were returned"
        ):
            adapter._extract_and_validate_logprobs(mock_choice)


class TestExtractReasoningToIntermediateOutputs:
    def test_extract_reasoning_with_valid_content(self, config, mock_task):
        """Test extracting reasoning content when present and valid"""
        adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)

        # Create mock choice with reasoning content
        mock_choice = Mock()
        mock_message = Mock()
        mock_message.reasoning_content = "This is my reasoning"
        mock_choice.message = mock_message

        intermediate_outputs = {}

        adapter._extract_reasoning_to_intermediate_outputs(
            mock_choice, intermediate_outputs
        )

        assert intermediate_outputs["reasoning"] == "This is my reasoning"

    def test_extract_reasoning_with_whitespace_content(self, config, mock_task):
        """Test extracting reasoning content with whitespace that gets stripped"""
        adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)

        mock_choice = Mock()
        mock_message = Mock()
        mock_message.reasoning_content = (
            "  \n  This is my reasoning with whitespace  \n  "
        )
        mock_choice.message = mock_message

        intermediate_outputs = {}

        adapter._extract_reasoning_to_intermediate_outputs(
            mock_choice, intermediate_outputs
        )

        assert (
            intermediate_outputs["reasoning"] == "This is my reasoning with whitespace"
        )

    def test_extract_reasoning_with_empty_content(self, config, mock_task):
        """Test that empty reasoning content is not added to intermediate outputs"""
        adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)

        mock_choice = Mock()
        mock_message = Mock()
        mock_message.reasoning_content = "   "  # Only whitespace
        mock_choice.message = mock_message

        intermediate_outputs = {}

        adapter._extract_reasoning_to_intermediate_outputs(
            mock_choice, intermediate_outputs
        )

        assert "reasoning" not in intermediate_outputs

    def test_extract_reasoning_with_none_content(self, config, mock_task):
        """Test that None reasoning content is not added to intermediate outputs"""
        adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)

        mock_choice = Mock()
        mock_message = Mock()
        mock_message.reasoning_content = None
        mock_choice.message = mock_message

        intermediate_outputs = {}

        adapter._extract_reasoning_to_intermediate_outputs(
            mock_choice, intermediate_outputs
        )

        assert "reasoning" not in intermediate_outputs

    def test_extract_reasoning_with_no_reasoning_attribute(self, config, mock_task):
        """Test that missing reasoning_content attribute is handled gracefully"""
        adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)

        mock_choice = Mock()
        mock_message = Mock(spec=[])  # Empty spec, no attributes
        mock_choice.message = mock_message

        intermediate_outputs = {}

        adapter._extract_reasoning_to_intermediate_outputs(
            mock_choice, intermediate_outputs
        )

        assert "reasoning" not in intermediate_outputs

    def test_extract_reasoning_with_no_message_attribute(self, config, mock_task):
        """Test that missing message attribute is handled gracefully"""
        adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)

        mock_choice = Mock(spec=[])  # Empty spec, no attributes

        intermediate_outputs = {}

        adapter._extract_reasoning_to_intermediate_outputs(
            mock_choice, intermediate_outputs
        )

        assert "reasoning" not in intermediate_outputs

    def test_extract_reasoning_with_none_choice(self, config, mock_task):
        """Test that None choice is handled gracefully"""
        adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)

        intermediate_outputs = {}

        adapter._extract_reasoning_to_intermediate_outputs(None, intermediate_outputs)

        assert "reasoning" not in intermediate_outputs


@pytest.mark.parametrize(
    "enable_thinking",
    [
        True,
        False,
    ],
)
def test_build_extra_body_enable_thinking(config, mock_task, enable_thinking):
    provider = Mock()
    provider.name = ModelProviderName.siliconflow_cn
    provider.siliconflow_enable_thinking = enable_thinking

    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)

    extra_body = adapter.build_extra_body(provider)

    assert extra_body["enable_thinking"] == enable_thinking
