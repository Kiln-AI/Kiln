import json
from unittest.mock import AsyncMock, Mock, patch

import litellm
import pytest
from litellm.types.utils import (
    ChatCompletionMessageToolCall,
    ChoiceLogprobs,
    Function,
    ModelResponse,
)

from kiln_ai.adapters.ml_model_list import ModelProviderName, StructuredOutputMode
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig
from kiln_ai.adapters.model_adapters.litellm_adapter import (
    LiteLlmAdapter,
    ModelTurnResult,
)
from kiln_ai.adapters.model_adapters.litellm_config import LiteLlmConfig
from kiln_ai.datamodel import Project, Task, Usage
from kiln_ai.datamodel.json_schema import close_object_schemas
from kiln_ai.datamodel.run_config import (
    KilnAgentRunConfigProperties,
    McpRunConfigProperties,
    MCPToolReference,
    ToolsRunConfig,
)
from kiln_ai.datamodel.tool_id import KilnBuiltInToolId
from kiln_ai.tools.base_tool import UnmanagedKilnTool
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
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="test-model",
            model_provider_name="openrouter",
            prompt_id="simple_prompt_builder",
            structured_output_mode="json_schema",
        ),
        default_headers={"X-Test": "test"},
        additional_body_options={"api_key": "test_key"},
    )


def test_initialization_rejects_non_kiln_agent_run_config(mock_task):
    bad_config = LiteLlmConfig(
        base_url="https://api.test.com",
        run_config_properties=McpRunConfigProperties(
            tool_reference=MCPToolReference(tool_id="mcp::local::server_id::tool_name")
        ),  # type: ignore[arg-type]
        default_headers=None,
        additional_body_options={},
    )

    with pytest.raises(
        ValueError, match="LiteLlmAdapter requires KilnAgentRunConfigProperties"
    ):
        LiteLlmAdapter(config=bad_config, kiln_task=mock_task)


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
        expected_schema = close_object_schemas(mock_task.output_schema(), strict=True)
        assert options == {
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "task_response",
                    "schema": expected_schema,
                },
            }
        }


def test_tool_call_params_weak(config, mock_task):
    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)

    params = adapter.tool_call_params(strict=False)
    expected_schema = close_object_schemas(mock_task.output_schema())

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
    expected_schema = close_object_schemas(mock_task.output_schema(), strict=True)

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


def test_tool_call_params_strict_adds_required_to_nested(config, tmp_path):
    project_path = tmp_path / "test_project_nested" / "project.kiln"
    project_path.parent.mkdir()
    project = Project(name="Nested Project", path=str(project_path))
    project.save_to_file()

    nested_schema = {
        "type": "object",
        "properties": {
            "user": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "age": {"type": "integer"},
                },
            },
            "status": {"type": "string"},
        },
    }
    task = Task(
        name="Nested Task",
        instruction="Test instruction",
        parent=project,
        output_json_schema=json.dumps(nested_schema),
    )
    task.save_to_file()

    adapter = LiteLlmAdapter(config=config, kiln_task=task)
    params = adapter.tool_call_params(strict=True)

    result_schema = params["tools"][0]["function"]["parameters"]
    assert result_schema["required"] == ["user", "status"]
    assert result_schema["properties"]["user"]["required"] == ["name", "age"]


@pytest.mark.asyncio
async def test_json_schema_response_format_adds_required_to_nested(config, tmp_path):
    project_path = tmp_path / "test_project_nested2" / "project.kiln"
    project_path.parent.mkdir()
    project = Project(name="Nested Project 2", path=str(project_path))
    project.save_to_file()

    nested_schema = {
        "type": "object",
        "properties": {
            "result": {
                "type": "object",
                "properties": {
                    "value": {"type": "number"},
                    "unit": {"type": "string"},
                },
            },
        },
    }
    task = Task(
        name="Nested Task 2",
        instruction="Test instruction",
        parent=project,
        output_json_schema=json.dumps(nested_schema),
    )
    task.save_to_file()

    config.run_config_properties.structured_output_mode = (
        StructuredOutputMode.json_schema
    )
    adapter = LiteLlmAdapter(config=config, kiln_task=task)

    with patch.object(adapter, "has_structured_output", return_value=True):
        options = await adapter.response_format_options()

    result_schema = options["response_format"]["json_schema"]["schema"]
    assert result_schema["required"] == ["result"]
    assert result_schema["properties"]["result"]["required"] == ["value", "unit"]


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
            "kiln_ai.utils.litellm.raise_exhaustive_enum_error"
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
    mock_provider.default_thinking_level = None
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


def test_build_extra_body_thinking_level_fallback_to_default(config, mock_task):
    """Test that the thinking level falls back to the provider's default if not set in the run config"""
    assert "thinking_level" not in config.run_config_properties.model_fields_set
    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)

    mock_provider = Mock()
    mock_provider.name = ModelProviderName.openai
    mock_provider.default_thinking_level = "medium"
    mock_provider.openrouter_reasoning_object = False
    mock_provider.require_openrouter_reasoning = False
    mock_provider.gemini_reasoning_enabled = False
    mock_provider.anthropic_extended_thinking = False
    mock_provider.r1_openrouter_options = False
    mock_provider.logprobs_openrouter_options = False
    mock_provider.openrouter_skip_required_parameters = False
    mock_provider.siliconflow_enable_thinking = None

    extra_body = adapter.build_extra_body(mock_provider)

    assert extra_body.get("reasoning_effort") == "medium"


def test_build_extra_body_thinking_level_openrouter_anthropic(config, mock_task):
    """Test that OpenRouter Anthropic models use reasoning.effort"""
    config.run_config_properties.thinking_level = "high"
    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)

    mock_provider = Mock()
    mock_provider.name = ModelProviderName.openrouter
    mock_provider.model_id = "anthropic/claude-4.5-sonnet"
    mock_provider.openrouter_reasoning_object = True
    mock_provider.default_thinking_level = None
    mock_provider.require_openrouter_reasoning = False
    mock_provider.gemini_reasoning_enabled = False
    mock_provider.anthropic_extended_thinking = False
    mock_provider.r1_openrouter_options = False
    mock_provider.logprobs_openrouter_options = False
    mock_provider.openrouter_skip_required_parameters = False
    mock_provider.siliconflow_enable_thinking = None

    extra_body = adapter.build_extra_body(mock_provider)

    assert extra_body.get("reasoning") == {"effort": "high"}
    assert "reasoning_effort" not in extra_body


def test_build_extra_body_thinking_level_run_config_override(config, mock_task):
    """Test that the thinking level in the run config overrides the provider's default"""
    config.run_config_properties.thinking_level = "low"
    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)

    mock_provider = Mock()
    mock_provider.name = ModelProviderName.openai
    mock_provider.default_thinking_level = "high"
    mock_provider.openrouter_reasoning_object = False
    mock_provider.require_openrouter_reasoning = False
    mock_provider.gemini_reasoning_enabled = False
    mock_provider.anthropic_extended_thinking = False
    mock_provider.r1_openrouter_options = False
    mock_provider.logprobs_openrouter_options = False
    mock_provider.openrouter_skip_required_parameters = False
    mock_provider.siliconflow_enable_thinking = None

    extra_body = adapter.build_extra_body(mock_provider)

    assert extra_body.get("reasoning_effort") == "low"


def test_build_extra_body_thinking_level_explicit_none(config, mock_task):
    """Test that the thinking level is not set if it's explicitly set to None"""
    config = LiteLlmConfig(
        base_url="https://api.test.com",
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="test-model",
            model_provider_name="openrouter",
            prompt_id="simple_prompt_builder",
            structured_output_mode="json_schema",
            thinking_level=None,  # Explicitly set to None to test that it's not set
        ),
        default_headers={"X-Test": "test"},
        additional_body_options={"api_key": "test_key"},
    )
    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)

    mock_provider = Mock()
    mock_provider.name = ModelProviderName.openai
    mock_provider.default_thinking_level = "high"
    mock_provider.openrouter_reasoning_object = False
    mock_provider.require_openrouter_reasoning = False
    mock_provider.gemini_reasoning_enabled = False
    mock_provider.anthropic_extended_thinking = False
    mock_provider.r1_openrouter_options = False
    mock_provider.logprobs_openrouter_options = False
    mock_provider.openrouter_skip_required_parameters = False
    mock_provider.siliconflow_enable_thinking = None

    extra_body = adapter.build_extra_body(mock_provider)

    assert "reasoning_effort" not in extra_body


def test_build_extra_body_openrouter_default_provider_order(config, mock_task):
    """Test build_extra_body sets default provider order for OpenRouter"""
    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)

    # Create a mock OpenRouter provider with minimal attributes
    mock_provider = Mock()
    mock_provider.name = ModelProviderName.openrouter
    mock_provider.default_thinking_level = None
    mock_provider.require_openrouter_reasoning = False
    mock_provider.gemini_reasoning_enabled = False
    mock_provider.anthropic_extended_thinking = False
    mock_provider.r1_openrouter_options = False
    mock_provider.logprobs_openrouter_options = False
    mock_provider.openrouter_skip_required_parameters = False
    mock_provider.siliconflow_enable_thinking = None

    extra_body = adapter.build_extra_body(mock_provider)

    # Verify default provider order is set
    assert "provider" in extra_body
    assert "order" in extra_body["provider"]
    expected_order = [
        "fireworks",
        "parasail",
        "together",
        "deepinfra",
        "novita",
        "groq",
        "amazon-bedrock",
        "azure",
        "nebius",
    ]
    assert extra_body["provider"]["order"] == expected_order


def test_build_extra_body_r1_overrides_default_order(config, mock_task):
    """Test that R1 specific options override the default provider order"""
    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)

    # Create a mock OpenRouter provider with R1 options enabled
    mock_provider = Mock()
    mock_provider.name = ModelProviderName.openrouter
    mock_provider.default_thinking_level = None
    mock_provider.require_openrouter_reasoning = False
    mock_provider.gemini_reasoning_enabled = False
    mock_provider.anthropic_extended_thinking = False
    mock_provider.r1_openrouter_options = True  # R1 special case
    mock_provider.logprobs_openrouter_options = False
    mock_provider.openrouter_skip_required_parameters = False
    mock_provider.siliconflow_enable_thinking = None

    extra_body = adapter.build_extra_body(mock_provider)

    # Verify R1 specific order overrides default
    assert "provider" in extra_body
    assert "order" in extra_body["provider"]
    # R1 has a specific order that should override the default
    assert extra_body["provider"]["order"] == ["fireworks", "together"]
    # R1 also sets require_parameters and ignore
    assert extra_body["provider"]["require_parameters"] is True
    assert extra_body["provider"]["ignore"] == ["deepinfra"]


def test_build_extra_body_non_openrouter_no_provider_order(config, mock_task):
    """Test that non-OpenRouter providers don't get provider order"""
    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)

    # Test with various non-OpenRouter providers
    for provider_name in [
        ModelProviderName.openai,
        ModelProviderName.anthropic,
        ModelProviderName.groq,
    ]:
        mock_provider = Mock()
        mock_provider.name = provider_name
        mock_provider.default_thinking_level = None
        mock_provider.require_openrouter_reasoning = False
        mock_provider.gemini_reasoning_enabled = False
        mock_provider.anthropic_extended_thinking = False
        mock_provider.r1_openrouter_options = False
        mock_provider.logprobs_openrouter_options = False
        mock_provider.openrouter_skip_required_parameters = False
        mock_provider.siliconflow_enable_thinking = None

        extra_body = adapter.build_extra_body(mock_provider)

        # Non-OpenRouter providers should not have provider options
        assert "provider" not in extra_body


@pytest.mark.asyncio
async def test_build_completion_kwargs_custom_temperature_top_p(config, mock_task):
    """Test build_completion_kwargs with custom temperature and top_p values"""
    # Create config with custom temperature and top_p
    config.run_config_properties.temperature = 0.7
    config.run_config_properties.top_p = 0.9

    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)
    mock_provider = Mock()
    mock_provider.temp_top_p_exclusive = False
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
    mock_provider.temp_top_p_exclusive = False
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
    assert kwargs["temperature"] == 1.0  # Default from KilnAgentRunConfigProperties
    assert kwargs["top_p"] == 1.0  # Default from KilnAgentRunConfigProperties

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
        # Cached tokens present
        (
            litellm.types.utils.Usage(
                prompt_tokens=100,
                completion_tokens=20,
                total_tokens=120,
                prompt_tokens_details={"cached_tokens": 80},
            ),
            None,
            Usage(
                input_tokens=100,
                output_tokens=20,
                total_tokens=120,
                cached_tokens=80,
            ),
        ),
        # Cached tokens with cost
        (
            litellm.types.utils.Usage(
                prompt_tokens=100,
                completion_tokens=20,
                total_tokens=120,
                prompt_tokens_details={"cached_tokens": 80},
            ),
            0.5,
            Usage(
                input_tokens=100,
                output_tokens=20,
                total_tokens=120,
                cost=0.5,
                cached_tokens=80,
            ),
        ),
    ],
)
def test_usage_from_response(config, mock_task, litellm_usage, cost, expected_usage):
    """Test usage_from_response with various combinations of usage data and cost"""
    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)

    # Create a mock response
    response = Mock(spec=ModelResponse)
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
        assert result.cached_tokens == expected_usage.cached_tokens

    # Verify the response was queried correctly
    response.get.assert_called_once_with("usage", None)


def test_usage_from_response_prompt_details_without_cached_tokens(config, mock_task):
    """Test that a warning is logged when prompt_tokens_details lacks cached_tokens attribute"""
    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)

    # Create a usage object with prompt_tokens_details that lacks cached_tokens
    usage = litellm.types.utils.Usage(
        prompt_tokens=100,
        completion_tokens=20,
        total_tokens=120,
    )
    # Manually set prompt_tokens_details to a truthy object without cached_tokens attr
    usage.prompt_tokens_details = Mock(spec=[])  # spec=[] means no attributes

    response = Mock(spec=ModelResponse)
    response.get.return_value = usage
    response._hidden_params = {"response_cost": None}

    with patch("kiln_ai.adapters.model_adapters.litellm_adapter.logger") as mock_logger:
        result = adapter.usage_from_response(response)

    assert result.input_tokens == 100
    assert result.output_tokens == 20
    assert result.total_tokens == 120
    assert result.cached_tokens is None
    mock_logger.warning.assert_called_once()
    assert "prompt_tokens_details has unexpected type" in str(
        mock_logger.warning.call_args
    )


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


@pytest.mark.parametrize(
    "kwargs_in,expected",
    [
        ({}, []),
        ({"tools": []}, ["tools"]),
        ({"tool_choice": "auto"}, ["tool_choice"]),
        ({"tools": [], "tool_choice": "auto"}, ["tools", "tool_choice"]),
        ({"allowed_openai_params": ["custom_param"]}, ["custom_param"]),
        (
            {"tools": [], "allowed_openai_params": ["custom_param"]},
            ["custom_param", "tools"],
        ),
    ],
)
def test_allowed_openai_params_for_completion_kwargs_independent_keys(
    config, mock_task, kwargs_in, expected
):
    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)
    result = adapter._allowed_openai_params_for_completion_kwargs(kwargs_in)
    assert sorted(result) == sorted(expected)


def test_allowed_openai_params_raises_for_non_list(config, mock_task):
    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)
    with pytest.raises(ValueError, match="expected list"):
        adapter._allowed_openai_params_for_completion_kwargs(
            {"allowed_openai_params": "not_a_list"}
        )


def test_allowed_openai_params_raises_for_non_string_items(config, mock_task):
    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)
    with pytest.raises(ValueError, match="items are not strings"):
        adapter._allowed_openai_params_for_completion_kwargs(
            {"allowed_openai_params": ["valid", 123]}
        )


@pytest.mark.asyncio
async def test_build_completion_kwargs_includes_tools(
    config, mock_task, mock_math_tools
):
    """Test build_completion_kwargs includes tools when available_tools has tools"""
    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)
    mock_provider = Mock()
    mock_provider.temp_top_p_exclusive = False
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
    assert isinstance(kwargs["allowed_openai_params"], list)
    assert sorted(kwargs["allowed_openai_params"]) == sorted(["tool_choice", "tools"])

    # Verify tools are properly formatted
    for tool in kwargs["tools"]:
        assert "type" in tool
        assert tool["type"] == "function"
        assert "function" in tool


@pytest.mark.asyncio
async def test_build_completion_kwargs_omits_allowed_openai_params_without_tools(
    config, mock_task
):
    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)
    mock_provider = Mock()
    mock_provider.temp_top_p_exclusive = False
    messages = [{"role": "user", "content": "Hello"}]

    with (
        patch.object(adapter, "model_provider", return_value=mock_provider),
        patch.object(adapter, "litellm_model_id", return_value="openai/test-model"),
        patch.object(adapter, "build_extra_body", return_value={}),
        patch.object(adapter, "response_format_options", return_value={}),
        patch.object(adapter, "available_tools", return_value=[]),
    ):
        kwargs = await adapter.build_completion_kwargs(mock_provider, messages, None)

    assert "allowed_openai_params" not in kwargs


@pytest.mark.asyncio
async def test_build_completion_kwargs_merges_allowed_openai_params(
    config, mock_task, mock_math_tools
):
    """Test that allowed_openai_params from additional_body_options are merged with internally computed ones."""
    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)
    adapter._additional_body_options = {
        "allowed_openai_params": ["tools", "custom_param"],
    }
    mock_provider = Mock()
    mock_provider.temp_top_p_exclusive = False
    messages = [{"role": "user", "content": "Hello"}]

    with (
        patch.object(adapter, "model_provider", return_value=mock_provider),
        patch.object(adapter, "litellm_model_id", return_value="openai/test-model"),
        patch.object(adapter, "build_extra_body", return_value={}),
        patch.object(adapter, "response_format_options", return_value={}),
        patch.object(adapter, "available_tools", return_value=mock_math_tools),
    ):
        kwargs = await adapter.build_completion_kwargs(mock_provider, messages, None)

    assert sorted(kwargs["allowed_openai_params"]) == [
        "custom_param",
        "tool_choice",
        "tools",
    ]


@pytest.mark.asyncio
async def test_build_completion_kwargs_preserves_existing_allowed_openai_params_without_tools(
    config, mock_task
):
    """Test that allowed_openai_params from additional_body_options are preserved even when no tools are present."""
    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)
    adapter._additional_body_options = {
        "allowed_openai_params": ["custom_param"],
    }
    mock_provider = Mock()
    mock_provider.temp_top_p_exclusive = False
    messages = [{"role": "user", "content": "Hello"}]

    with (
        patch.object(adapter, "model_provider", return_value=mock_provider),
        patch.object(adapter, "litellm_model_id", return_value="openai/test-model"),
        patch.object(adapter, "build_extra_body", return_value={}),
        patch.object(adapter, "response_format_options", return_value={}),
        patch.object(adapter, "available_tools", return_value=[]),
    ):
        kwargs = await adapter.build_completion_kwargs(mock_provider, messages, None)

    assert kwargs["allowed_openai_params"] == ["custom_param"]


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
    mock_provider.temp_top_p_exclusive = False
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
    provider.default_thinking_level = None
    provider.openrouter_reasoning_object = False
    provider.require_openrouter_reasoning = False
    provider.gemini_reasoning_enabled = False
    provider.anthropic_extended_thinking = False
    provider.r1_openrouter_options = False
    provider.logprobs_openrouter_options = False
    provider.openrouter_skip_required_parameters = False
    provider.siliconflow_enable_thinking = enable_thinking

    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)

    extra_body = adapter.build_extra_body(provider)

    assert extra_body["enable_thinking"] == enable_thinking


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "temperature,top_p,should_raise,expected_temp,expected_top_p",
    [
        (1.0, 1.0, False, None, None),
        (0.7, 1.0, False, 0.7, None),
        (1.0, 0.9, False, None, 0.9),
        (0.7, 0.9, True, None, None),
        (0.5, 0.5, True, None, None),
    ],
)
async def test_build_completion_kwargs_temp_top_p_exclusive(
    config, mock_task, temperature, top_p, should_raise, expected_temp, expected_top_p
):
    """Test build_completion_kwargs with temp_top_p_exclusive provider flag"""
    config.run_config_properties.temperature = temperature
    config.run_config_properties.top_p = top_p

    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)
    mock_provider = Mock()
    mock_provider.temp_top_p_exclusive = True
    messages = [{"role": "user", "content": "Hello"}]

    with (
        patch.object(adapter, "model_provider", return_value=mock_provider),
        patch.object(adapter, "litellm_model_id", return_value="anthropic/test-model"),
        patch.object(adapter, "build_extra_body", return_value={}),
        patch.object(adapter, "response_format_options", return_value={}),
    ):
        if should_raise:
            with pytest.raises(
                ValueError,
                match="top_p and temperature can not both have custom values",
            ):
                await adapter.build_completion_kwargs(mock_provider, messages, None)
        else:
            kwargs = await adapter.build_completion_kwargs(
                mock_provider, messages, None
            )

            if expected_temp is None:
                assert "temperature" not in kwargs
            else:
                assert kwargs["temperature"] == expected_temp

            if expected_top_p is None:
                assert "top_p" not in kwargs
            else:
                assert kwargs["top_p"] == expected_top_p


@pytest.mark.asyncio
async def test_build_completion_kwargs_temp_top_p_not_exclusive(config, mock_task):
    """Test build_completion_kwargs with temp_top_p_exclusive=False allows both params"""
    config.run_config_properties.temperature = 0.7
    config.run_config_properties.top_p = 0.9

    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)
    mock_provider = Mock()
    mock_provider.temp_top_p_exclusive = False
    messages = [{"role": "user", "content": "Hello"}]

    with (
        patch.object(adapter, "model_provider", return_value=mock_provider),
        patch.object(adapter, "litellm_model_id", return_value="openai/test-model"),
        patch.object(adapter, "build_extra_body", return_value={}),
        patch.object(adapter, "response_format_options", return_value={}),
    ):
        kwargs = await adapter.build_completion_kwargs(mock_provider, messages, None)

        assert kwargs["temperature"] == 0.7
        assert kwargs["top_p"] == 0.9


@pytest.mark.asyncio
async def test_array_input_converted_to_json(tmp_path, config):
    """Test that array inputs are converted to JSON and passed to the model"""
    project_path = tmp_path / "test_project" / "project.kiln"
    project_path.parent.mkdir()

    project = Project(name="Test Project", path=str(project_path))
    project.save_to_file()

    array_schema = {
        "type": "array",
        "items": {"type": "integer"},
        "description": "A list of integers",
    }

    task = Task(
        name="Array Test Task",
        instruction="Process the array of numbers",
        parent=project,
        input_json_schema=json.dumps(array_schema),
    )
    task.save_to_file()

    config.run_config_properties.model_name = "gpt-4o-mini"
    config.run_config_properties.model_provider_name = ModelProviderName.openai
    adapter = LiteLlmAdapter(config=config, kiln_task=task)

    mock_response = ModelResponse(
        model="gpt-4o-mini",
        choices=[
            {
                "message": {
                    "content": "Processed the array successfully",
                }
            }
        ],
    )

    mock_config_obj = Mock()
    mock_config_obj.open_ai_api_key = "mock_api_key"
    mock_config_obj.user_id = "test_user"

    with (
        patch.object(
            LiteLlmAdapter,
            "acompletion_checking_response",
            new=AsyncMock(return_value=(mock_response, mock_response.choices[0])),
        ),
        patch("kiln_ai.utils.config.Config.shared", return_value=mock_config_obj),
    ):
        array_input = [1, 2, 3, 4, 5]
        run = await adapter.invoke(array_input)

        assert run.output.output == "Processed the array successfully"
        assert run.trace is not None
        assert len(run.trace) >= 2

        user_message = None
        for message in run.trace:
            if message["role"] == "user":
                user_message = message
                break

        assert user_message is not None
        content = user_message.get("content")
        assert content is not None
        assert isinstance(content, str)
        parsed_content = json.loads(content)
        assert parsed_content == [1, 2, 3, 4, 5]


@pytest.mark.asyncio
async def test_dict_input_converted_to_json(tmp_path, config):
    """Test that dict inputs are converted to JSON and passed to the model"""
    project_path = tmp_path / "test_project" / "project.kiln"
    project_path.parent.mkdir()

    project = Project(name="Test Project", path=str(project_path))
    project.save_to_file()

    dict_schema = {
        "type": "object",
        "properties": {
            "x": {"type": "integer"},
            "y": {"type": "integer"},
        },
        "required": ["x", "y"],
    }

    task = Task(
        name="Dict Test Task",
        instruction="Process the coordinates",
        parent=project,
        input_json_schema=json.dumps(dict_schema),
    )
    task.save_to_file()

    config.run_config_properties.model_name = "gpt-4o-mini"
    config.run_config_properties.model_provider_name = ModelProviderName.openai
    adapter = LiteLlmAdapter(config=config, kiln_task=task)

    mock_response = ModelResponse(
        model="gpt-4o-mini",
        choices=[
            {
                "message": {
                    "content": "Processed the coordinates successfully",
                }
            }
        ],
    )

    mock_config_obj = Mock()
    mock_config_obj.open_ai_api_key = "mock_api_key"
    mock_config_obj.user_id = "test_user"

    with (
        patch.object(
            LiteLlmAdapter,
            "acompletion_checking_response",
            new=AsyncMock(return_value=(mock_response, mock_response.choices[0])),
        ),
        patch("kiln_ai.utils.config.Config.shared", return_value=mock_config_obj),
    ):
        dict_input = {"x": 10, "y": 20}
        run = await adapter.invoke(dict_input)

        assert run.output.output == "Processed the coordinates successfully"
        assert run.trace is not None
        assert len(run.trace) >= 2

        user_message = None
        for message in run.trace:
            if message["role"] == "user":
                user_message = message
                break

        assert user_message is not None
        content = user_message.get("content")
        assert content is not None
        assert isinstance(content, str)
        parsed_content = json.loads(content)
        assert parsed_content == {"x": 10, "y": 20}


@pytest.mark.asyncio
async def test_run_with_prior_trace_uses_multiturn_formatter(mock_task):
    config = LiteLlmConfig(
        base_url="https://api.test.com",
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="test-model",
            model_provider_name="openai_compatible",
            prompt_id="simple_prompt_builder",
            structured_output_mode="json_schema",
        ),
        default_headers={"X-Test": "test"},
        additional_body_options={"api_key": "test_key"},
    )
    prior_trace = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)

    build_chat_formatter_calls = []

    original_build = adapter.build_chat_formatter

    def capturing_build(input, prior_trace_arg=None):
        build_chat_formatter_calls.append((input, prior_trace_arg))
        return original_build(input, prior_trace_arg)

    adapter.build_chat_formatter = capturing_build

    async def mock_run_model_turn(
        provider, prior_messages, top_logprobs, skip_response_format
    ):
        extended = list(prior_messages)
        extended.append({"role": "assistant", "content": "How can I help?"})
        return ModelTurnResult(
            assistant_message="How can I help?",
            all_messages=extended,
            model_response=None,
            model_choice=None,
            usage=Usage(),
        )

    adapter._run_model_turn = mock_run_model_turn

    run_output, _ = await adapter._run("follow-up", prior_trace=prior_trace)

    assert len(build_chat_formatter_calls) == 1
    assert build_chat_formatter_calls[0][0] == "follow-up"
    assert build_chat_formatter_calls[0][1] == prior_trace

    assert run_output.trace is not None
    assert len(run_output.trace) == 4
    assert run_output.trace[0]["content"] == "hi"
    assert run_output.trace[1]["content"] == "hello"
    assert run_output.trace[2]["content"] == "follow-up"
    assert run_output.trace[3]["content"] == "How can I help?"


@pytest.mark.asyncio
async def test_run_with_prior_trace_preserves_tool_calls(mock_task):
    """Prior trace containing tool calls should be passed through to the model and preserved in the output trace."""
    config = LiteLlmConfig(
        base_url="https://api.test.com",
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="test-model",
            model_provider_name="openai_compatible",
            prompt_id="simple_prompt_builder",
            structured_output_mode="json_schema",
        ),
        default_headers={"X-Test": "test"},
        additional_body_options={"api_key": "test_key"},
    )

    prior_trace = [
        {"role": "system", "content": "Use the math tools."},
        {"role": "user", "content": "4"},
        {
            "role": "assistant",
            "content": "",
            "reasoning_content": "Let me multiply 4 by 7.\n",
            "tool_calls": [
                {
                    "id": "call_abc123",
                    "function": {"arguments": '{"a": 4, "b": 7}', "name": "multiply"},
                    "type": "function",
                }
            ],
        },
        {
            "content": "28",
            "role": "tool",
            "tool_call_id": "call_abc123",
            "kiln_task_tool_data": None,
        },
        {
            "role": "assistant",
            "content": "",
            "reasoning_content": "Now add 144.\n",
            "tool_calls": [
                {
                    "id": "call_def456",
                    "function": {"arguments": '{"a": 28, "b": 144}', "name": "add"},
                    "type": "function",
                }
            ],
        },
        {
            "content": "172",
            "role": "tool",
            "tool_call_id": "call_def456",
            "kiln_task_tool_data": None,
        },
        {
            "role": "assistant",
            "content": "There were 172 distinct species of giant tortoises.",
            "reasoning_content": "Now I have 172.\n",
        },
    ]
    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)

    captured_messages = []

    async def mock_run_model_turn(
        provider, prior_messages, top_logprobs, skip_response_format
    ):
        captured_messages.extend(prior_messages)
        extended = list(prior_messages)
        extended.append({"role": "assistant", "content": '{"test": "response"}'})
        return ModelTurnResult(
            assistant_message='{"test": "response"}',
            all_messages=extended,
            model_response=None,
            model_choice=None,
            usage=Usage(),
        )

    adapter._run_model_turn = mock_run_model_turn

    run_output, _ = await adapter._run("what else?", prior_trace=prior_trace)

    assert run_output.trace is not None
    # 7 prior trace messages + 1 new user + 1 new assistant = 9
    assert len(run_output.trace) == 9

    # Verify tool call messages are preserved in the trace
    assistant_with_tools = run_output.trace[2]
    assert assistant_with_tools["role"] == "assistant"
    assert assistant_with_tools["tool_calls"][0]["id"] == "call_abc123"
    assert assistant_with_tools["tool_calls"][0]["function"]["name"] == "multiply"
    assert assistant_with_tools["reasoning_content"] == "Let me multiply 4 by 7.\n"

    tool_response = run_output.trace[3]
    assert tool_response["role"] == "tool"
    assert tool_response["tool_call_id"] == "call_abc123"
    assert tool_response["content"] == "28"

    second_tool_call = run_output.trace[4]
    assert second_tool_call["tool_calls"][0]["id"] == "call_def456"
    assert second_tool_call["tool_calls"][0]["function"]["name"] == "add"

    second_tool_response = run_output.trace[5]
    assert second_tool_response["role"] == "tool"
    assert second_tool_response["tool_call_id"] == "call_def456"
    assert second_tool_response["content"] == "172"

    # Verify the tool call messages were passed to _run_model_turn (i.e., sent to the model)
    assert any(
        m.get("tool_calls") is not None
        for m in captured_messages
        if isinstance(m, dict)
    )
    assert any(
        m.get("role") == "tool" for m in captured_messages if isinstance(m, dict)
    )


@pytest.mark.asyncio
async def test_structured_output_with_return_on_tool_call_and_resume(
    mock_task, mock_math_tools
):
    """Two-turn round-trip: first invoke stops at a tool call, second invoke resumes with the
    result and returns a validated structured output dict."""
    config = LiteLlmConfig(
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="test-model",
            model_provider_name="openai_compatible",
            prompt_id="simple_prompt_builder",
            structured_output_mode="json_schema",
        ),
        default_headers={"X-Test": "test"},
        additional_body_options={"api_key": "test_key"},
    )
    adapter = LiteLlmAdapter(
        config=config,
        kiln_task=mock_task,
        base_adapter_config=AdapterConfig(return_on_tool_call=True),
    )

    tool_call = ChatCompletionMessageToolCall(
        id="call_test_multiply",
        type="function",
        function=Function(name="multiply", arguments='{"a": 3, "b": 7}'),
    )

    call_count = 0

    async def mock_run_model_turn(
        provider, prior_messages, top_logprobs, skip_response_format
    ):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            extended = list(prior_messages)
            extended.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_test_multiply",
                            "function": {
                                "arguments": '{"a": 3, "b": 7}',
                                "name": "multiply",
                            },
                            "type": "function",
                        }
                    ],
                }
            )
            return ModelTurnResult(
                assistant_message="",
                all_messages=extended,
                model_response=None,
                model_choice=None,
                usage=Usage(),
                interrupted_by_tool_calls=[tool_call],
            )
        else:
            json_response = '{"test": "structured_response"}'
            extended = list(prior_messages)
            extended.append({"role": "assistant", "content": json_response})
            return ModelTurnResult(
                assistant_message=json_response,
                all_messages=extended,
                model_response=None,
                model_choice=None,
                usage=Usage(),
            )

    adapter._run_model_turn = mock_run_model_turn

    with patch.object(adapter, "available_tools", return_value=mock_math_tools):
        task_run = await adapter.invoke(input="3 * 7 = ?")

    assert task_run.is_toolcall_pending, "First invoke should have pending tool calls"
    assert task_run.trace is not None
    last_msg = task_run.trace[-1]
    assert last_msg.get("role") == "assistant"
    assert last_msg.get("tool_calls") is not None
    assert last_msg["tool_calls"][0]["id"] == "call_test_multiply"

    with patch.object(adapter, "available_tools", return_value=mock_math_tools):
        task_run2 = await adapter.invoke(
            input={"tool_call_id": "call_test_multiply", "content": "21"},
            prior_trace=task_run.trace,
        )

    assert not task_run2.is_toolcall_pending, "Second invoke should be complete"
    assert json.loads(task_run2.output.output) == {"test": "structured_response"}, (
        f"Expected structured dict output, got: {task_run2.output.output}"
    )

    # Verify trace structure: assistant+tool_calls → tool response → final assistant
    assert task_run2.trace is not None
    roles = [m.get("role") for m in task_run2.trace]
    assert "tool" in roles, "Trace must have a tool response message"
    tool_msgs = [m for m in task_run2.trace if m.get("role") == "tool"]
    assert any(m.get("tool_call_id") == "call_test_multiply" for m in tool_msgs), (
        "Tool response must carry the correct tool_call_id"
    )
    final_msg = task_run2.trace[-1]
    assert final_msg.get("role") == "assistant"
    assert not final_msg.get("tool_calls"), (
        "Final message must not have pending tool_calls"
    )
    assert final_msg.get("content"), "Final message must have non-empty content"


def _lookup_weather_unmanaged_tool(name: str = "lookup_weather") -> UnmanagedKilnTool:
    return UnmanagedKilnTool(
        tool_id="kiln_unmanaged::lookup_weather",
        name=name,
        description="Look up weather for a location",
        parameters_schema={
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City name"},
            },
            "required": ["location"],
        },
    )


def _sdk_unmanaged_multiply_tool() -> UnmanagedKilnTool:
    return UnmanagedKilnTool(
        tool_id="kiln_unmanaged::sdk_unmanaged_multiply",
        name="sdk_unmanaged_multiply",
        description="Multiply two numbers. Use for all arithmetic.",
        parameters_schema={
            "type": "object",
            "properties": {
                "a": {"type": "number"},
                "b": {"type": "number"},
            },
            "required": ["a", "b"],
        },
    )


def test_unmanaged_tools_invalid_type_raises(mock_task, config):
    with pytest.raises(TypeError, match="must be a KilnToolInterface instance"):
        LiteLlmAdapter(
            config=config,
            kiln_task=mock_task,
            base_adapter_config=AdapterConfig(
                return_on_tool_call=True,
                unmanaged_tools=[object()],  # type: ignore[list-item]
            ),
        )


@pytest.mark.asyncio
async def test_litellm_tools_raises_when_duplicate_unmanaged_tool_names(
    mock_task, config
):
    adapter = LiteLlmAdapter(
        config=config,
        kiln_task=mock_task,
        base_adapter_config=AdapterConfig(
            return_on_tool_call=True,
            unmanaged_tools=[
                _lookup_weather_unmanaged_tool("dup"),
                UnmanagedKilnTool(
                    tool_id="kiln_unmanaged::lookup_weather_2",
                    name="dup",
                    description="other",
                    parameters_schema={
                        "type": "object",
                        "properties": {"x": {"type": "string"}},
                        "required": ["x"],
                    },
                ),
            ],
        ),
    )
    with pytest.raises(ValueError, match="Duplicate tool name"):
        await adapter.litellm_tools()


@pytest.mark.asyncio
async def test_litellm_tools_merges_unmanaged_definitions(mock_task, config):
    adapter = LiteLlmAdapter(
        config=config,
        kiln_task=mock_task,
        base_adapter_config=AdapterConfig(
            return_on_tool_call=True,
            unmanaged_tools=[_lookup_weather_unmanaged_tool()],
        ),
    )
    with patch.object(adapter, "available_tools", return_value=[]):
        tools = await adapter.litellm_tools()
    assert len(tools) == 1
    assert tools[0]["function"]["name"] == "lookup_weather"


@pytest.mark.asyncio
async def test_litellm_tools_raises_when_unmanaged_collides_with_registry(
    mock_task, config
):
    config.run_config_properties = KilnAgentRunConfigProperties(
        model_name="test-model",
        model_provider_name="openrouter",
        prompt_id="simple_prompt_builder",
        structured_output_mode=StructuredOutputMode.json_schema,
        tools_config=ToolsRunConfig(tools=[KilnBuiltInToolId.ADD_NUMBERS]),
    )
    adapter = LiteLlmAdapter(
        config=config,
        kiln_task=mock_task,
        base_adapter_config=AdapterConfig(
            return_on_tool_call=True,
            unmanaged_tools=[_lookup_weather_unmanaged_tool("add")],
        ),
    )
    with pytest.raises(ValueError, match="Duplicate tool name"):
        await adapter.litellm_tools()


@pytest.mark.asyncio
async def test_build_completion_kwargs_includes_unmanaged_tools(mock_task, config):
    adapter = LiteLlmAdapter(
        config=config,
        kiln_task=mock_task,
        base_adapter_config=AdapterConfig(
            return_on_tool_call=True,
            unmanaged_tools=[_lookup_weather_unmanaged_tool()],
        ),
    )
    mock_provider = Mock()
    mock_provider.temp_top_p_exclusive = False
    messages = [{"role": "user", "content": "Hello"}]

    with (
        patch.object(adapter, "model_provider", return_value=mock_provider),
        patch.object(adapter, "litellm_model_id", return_value="openai/test-model"),
        patch.object(adapter, "build_extra_body", return_value={}),
        patch.object(adapter, "response_format_options", return_value={}),
        patch.object(adapter, "available_tools", return_value=[]),
    ):
        kwargs = await adapter.build_completion_kwargs(mock_provider, messages, None)

    assert "tools" in kwargs
    names = [t["function"]["name"] for t in kwargs["tools"]]
    assert "lookup_weather" in names
    assert kwargs["tool_choice"] == "auto"


@pytest.mark.asyncio
async def test_litellm_tools_merges_registry_then_unmanaged_order(
    mock_task, config, mock_math_tools
):
    adapter = LiteLlmAdapter(
        config=config,
        kiln_task=mock_task,
        base_adapter_config=AdapterConfig(
            return_on_tool_call=True,
            unmanaged_tools=[_lookup_weather_unmanaged_tool("extra_client_tool")],
        ),
    )
    with patch.object(adapter, "available_tools", return_value=mock_math_tools):
        tools = await adapter.litellm_tools()
    names = [t["function"]["name"] for t in tools]
    assert names == ["add", "subtract", "multiply", "divide", "extra_client_tool"]


@pytest.mark.asyncio
async def test_litellm_tools_unmanaged_toolcall_definitions_are_fresh_each_call(
    mock_task, config
):
    ext = _lookup_weather_unmanaged_tool()
    adapter = LiteLlmAdapter(
        config=config,
        kiln_task=mock_task,
        base_adapter_config=AdapterConfig(
            return_on_tool_call=True,
            unmanaged_tools=[ext],
        ),
    )
    with patch.object(adapter, "available_tools", return_value=[]):
        first = await adapter.litellm_tools()
    first[0]["function"]["name"] = "mutated_name"
    with patch.object(adapter, "available_tools", return_value=[]):
        second = await adapter.litellm_tools()
    assert second[0]["function"]["name"] == "lookup_weather"


@pytest.mark.asyncio
async def test_build_completion_kwargs_json_schema_allows_unmanaged_with_registry_tools(
    mock_task, config, mock_math_tools
):
    config.run_config_properties.structured_output_mode = (
        StructuredOutputMode.json_schema
    )
    adapter = LiteLlmAdapter(
        config=config,
        kiln_task=mock_task,
        base_adapter_config=AdapterConfig(
            return_on_tool_call=True,
            unmanaged_tools=[_lookup_weather_unmanaged_tool("client_only_tool")],
        ),
    )
    mock_provider = Mock()
    mock_provider.temp_top_p_exclusive = False
    messages = [{"role": "user", "content": "Hello"}]

    with (
        patch.object(adapter, "model_provider", return_value=mock_provider),
        patch.object(adapter, "litellm_model_id", return_value="openai/test-model"),
        patch.object(adapter, "build_extra_body", return_value={}),
        patch.object(adapter, "available_tools", return_value=mock_math_tools),
    ):
        kwargs = await adapter.build_completion_kwargs(mock_provider, messages, None)

    names = [t["function"]["name"] for t in kwargs["tools"]]
    assert set(names) == {
        "add",
        "subtract",
        "multiply",
        "divide",
        "client_only_tool",
    }
    assert "response_format" in kwargs


@pytest.mark.asyncio
async def test_unmanaged_tools_only_return_on_tool_call_and_resume_mocked(
    mock_task,
):
    """Unmanaged-only KilnTool instances (no registry tools): interrupt then resume, fully mocked."""
    config = LiteLlmConfig(
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="test-model",
            model_provider_name="openai_compatible",
            prompt_id="simple_prompt_builder",
            structured_output_mode="json_schema",
        ),
        default_headers={"X-Test": "test"},
        additional_body_options={"api_key": "test_key"},
    )
    adapter = LiteLlmAdapter(
        config=config,
        kiln_task=mock_task,
        base_adapter_config=AdapterConfig(
            return_on_tool_call=True,
            unmanaged_tools=[_sdk_unmanaged_multiply_tool()],
        ),
    )

    tool_call = ChatCompletionMessageToolCall(
        id="call_sdk_unmanaged_multiply",
        type="function",
        function=Function(name="sdk_unmanaged_multiply", arguments='{"a": 3, "b": 7}'),
    )

    call_count = 0

    async def mock_run_model_turn(
        provider, prior_messages, top_logprobs, skip_response_format
    ):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            extended = list(prior_messages)
            extended.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_sdk_unmanaged_multiply",
                            "function": {
                                "arguments": '{"a": 3, "b": 7}',
                                "name": "sdk_unmanaged_multiply",
                            },
                            "type": "function",
                        }
                    ],
                }
            )
            return ModelTurnResult(
                assistant_message="",
                all_messages=extended,
                model_response=None,
                model_choice=None,
                usage=Usage(),
                interrupted_by_tool_calls=[tool_call],
            )
        json_response = '{"test": "structured_response"}'
        extended = list(prior_messages)
        extended.append({"role": "assistant", "content": json_response})
        return ModelTurnResult(
            assistant_message=json_response,
            all_messages=extended,
            model_response=None,
            model_choice=None,
            usage=Usage(),
        )

    adapter._run_model_turn = mock_run_model_turn

    with patch.object(adapter, "available_tools", return_value=[]):
        task_run = await adapter.invoke(input="3 * 7 = ?")

    assert task_run.is_toolcall_pending
    assert task_run.trace is not None
    last = task_run.trace[-1]
    assert last.get("tool_calls") is not None
    assert last["tool_calls"][0]["function"]["name"] == "sdk_unmanaged_multiply"

    with patch.object(adapter, "available_tools", return_value=[]):
        task_run2 = await adapter.invoke(
            input={
                "tool_call_id": "call_sdk_unmanaged_multiply",
                "content": "21",
            },
            prior_trace=task_run.trace,
        )

    assert not task_run2.is_toolcall_pending
    assert json.loads(task_run2.output.output) == {"test": "structured_response"}


async def test_build_completion_kwargs_no_caching_by_default(config, mock_task):
    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)
    mock_provider = Mock()
    mock_provider.temp_top_p_exclusive = False
    messages = [{"role": "user", "content": "Hello"}]

    with (
        patch.object(adapter, "model_provider", return_value=mock_provider),
        patch.object(adapter, "litellm_model_id", return_value="openai/test-model"),
        patch.object(adapter, "build_extra_body", return_value={}),
        patch.object(adapter, "response_format_options", return_value={}),
    ):
        kwargs = await adapter.build_completion_kwargs(
            mock_provider, messages, top_logprobs=None
        )

    assert "cache_control_injection_points" not in kwargs


async def test_build_completion_kwargs_with_automatic_prompt_caching(config, mock_task):
    adapter = LiteLlmAdapter(
        config=config,
        kiln_task=mock_task,
        base_adapter_config=AdapterConfig(automatic_prompt_caching=True),
    )
    mock_provider = Mock()
    mock_provider.temp_top_p_exclusive = False
    messages = [{"role": "user", "content": "Hello"}]

    with (
        patch.object(adapter, "model_provider", return_value=mock_provider),
        patch.object(adapter, "litellm_model_id", return_value="openai/test-model"),
        patch.object(adapter, "build_extra_body", return_value={}),
        patch.object(adapter, "response_format_options", return_value={}),
    ):
        kwargs = await adapter.build_completion_kwargs(
            mock_provider, messages, top_logprobs=None
        )

    assert kwargs["cache_control_injection_points"] == [
        {"location": "message", "index": -1}
    ]


@pytest.mark.asyncio
async def test_process_tool_calls_propagates_error_fields(config, mock_task):
    """Test that is_error and error_message from ToolCallResult propagate to the tool message wrapper."""
    from kiln_ai.datamodel.tool_id import ToolId
    from kiln_ai.tools.base_tool import (
        KilnToolInterface,
        ToolCallContext,
        ToolCallDefinition,
        ToolCallResult,
    )

    class FakeErrorTool(KilnToolInterface):
        async def run(
            self, context: ToolCallContext | None = None, **kwargs
        ) -> ToolCallResult:
            return ToolCallResult(
                output="something went wrong",
                is_error=True,
                error_message="something went wrong",
            )

        async def toolcall_definition(self) -> ToolCallDefinition:
            return {
                "type": "function",
                "function": {
                    "name": "error_tool",
                    "description": "A tool that errors",
                    "parameters": {"type": "object", "properties": {}},
                },
            }

        async def id(self) -> ToolId:
            return "error_tool"

        async def name(self) -> str:
            return "error_tool"

        async def description(self) -> str:
            return "A tool that errors"

    class FakeSuccessTool(KilnToolInterface):
        async def run(
            self, context: ToolCallContext | None = None, **kwargs
        ) -> ToolCallResult:
            return ToolCallResult(output="all good")

        async def toolcall_definition(self) -> ToolCallDefinition:
            return {
                "type": "function",
                "function": {
                    "name": "success_tool",
                    "description": "A tool that succeeds",
                    "parameters": {"type": "object", "properties": {}},
                },
            }

        async def id(self) -> ToolId:
            return "success_tool"

        async def name(self) -> str:
            return "success_tool"

        async def description(self) -> str:
            return "A tool that succeeds"

    adapter = LiteLlmAdapter(config=config, kiln_task=mock_task)

    error_tool_call = ChatCompletionMessageToolCall(
        id="call_err",
        type="function",
        function=Function(name="error_tool", arguments="{}"),
    )
    success_tool_call = ChatCompletionMessageToolCall(
        id="call_ok",
        type="function",
        function=Function(name="success_tool", arguments="{}"),
    )

    with patch.object(
        adapter,
        "available_tools",
        return_value=[FakeErrorTool(), FakeSuccessTool()],
    ):
        _, messages = await adapter.process_tool_calls(
            [error_tool_call, success_tool_call]
        )

    assert len(messages) == 2

    error_msg = next(m for m in messages if m["tool_call_id"] == "call_err")
    assert error_msg["content"] == "something went wrong"
    assert error_msg["is_error"] is True
    assert error_msg["error_message"] == "something went wrong"

    success_msg = next(m for m in messages if m["tool_call_id"] == "call_ok")
    assert success_msg["content"] == "all good"
    assert success_msg.get("is_error") is None
    assert success_msg.get("error_message") is None


class TestLatencyTracking:
    """Tests for LLM call latency tracking in _run_model_turn and trace messages."""

    @pytest.fixture
    def adapter(self, config, mock_task):
        return LiteLlmAdapter(config=config, kiln_task=mock_task)

    @pytest.fixture
    def simple_response(self):
        return ModelResponse(
            model="test-model",
            choices=[{"message": {"content": "Hello!", "tool_calls": None}}],
        )

    @pytest.fixture
    def provider(self):
        from kiln_ai.adapters.ml_model_list import KilnModelProvider

        return KilnModelProvider(
            name=ModelProviderName.openrouter, model_id="test-model"
        )

    @pytest.mark.asyncio
    async def test_run_model_turn_sets_latency_on_usage(
        self, adapter, simple_response, provider
    ):
        """_run_model_turn() should set total_llm_latency_ms on usage."""
        monotonic_values = [0.0, 0.5]  # 500ms call
        with patch.object(adapter, "build_completion_kwargs", return_value={}):
            with patch.object(
                adapter,
                "acompletion_checking_response",
                return_value=(simple_response, simple_response.choices[0]),
            ):
                with patch(
                    "kiln_ai.adapters.model_adapters.litellm_adapter.time.monotonic",
                    side_effect=monotonic_values,
                ):
                    result = await adapter._run_model_turn(
                        provider, [{"role": "user", "content": "Hi"}], None, False
                    )

        assert result.usage.total_llm_latency_ms == 500

    @pytest.mark.asyncio
    async def test_run_model_turn_sets_latency_on_trace_message(
        self, adapter, simple_response, provider
    ):
        """_run_model_turn() should attach _latency_ms to the response message."""
        monotonic_values = [0.0, 0.25]  # 250ms
        with patch.object(adapter, "build_completion_kwargs", return_value={}):
            with patch.object(
                adapter,
                "acompletion_checking_response",
                return_value=(simple_response, simple_response.choices[0]),
            ):
                with patch(
                    "kiln_ai.adapters.model_adapters.litellm_adapter.time.monotonic",
                    side_effect=monotonic_values,
                ):
                    result = await adapter._run_model_turn(
                        provider, [{"role": "user", "content": "Hi"}], None, False
                    )

        assistant_msg = result.all_messages[-1]
        assert getattr(assistant_msg, "_latency_ms", None) == 250

    @pytest.mark.asyncio
    async def test_run_model_turn_accumulates_latency_across_tool_calls(
        self, adapter, provider
    ):
        """Latency should accumulate across multiple tool-call iterations."""
        tool_response = ModelResponse(
            model="test-model",
            choices=[
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "task_response",
                                    "arguments": '{"test": "result"}',
                                },
                            }
                        ],
                    }
                }
            ],
        )

        monotonic_values = [0.0, 0.3]  # 300ms
        with patch.object(adapter, "build_completion_kwargs", return_value={}):
            with patch.object(
                adapter,
                "acompletion_checking_response",
                return_value=(tool_response, tool_response.choices[0]),
            ):
                with patch(
                    "kiln_ai.adapters.model_adapters.litellm_adapter.time.monotonic",
                    side_effect=monotonic_values,
                ):
                    result = await adapter._run_model_turn(
                        provider, [{"role": "user", "content": "Hi"}], None, False
                    )

        assert result.usage.total_llm_latency_ms == 300

    def test_litellm_message_to_trace_message_includes_latency(self, adapter):
        """litellm_message_to_trace_message should include latency_ms when _latency_ms is set."""
        from litellm.types.utils import Message as LiteLLMMessage

        msg = LiteLLMMessage(role="assistant", content="Hello")
        msg._latency_ms = 123  # type: ignore[attr-defined]

        trace_msg = adapter.litellm_message_to_trace_message(msg)
        assert trace_msg["latency_ms"] == 123

    def test_litellm_message_to_trace_message_no_latency(self, adapter):
        """litellm_message_to_trace_message should omit latency_ms when _latency_ms is not set."""
        from litellm.types.utils import Message as LiteLLMMessage

        msg = LiteLLMMessage(role="assistant", content="Hello")

        trace_msg = adapter.litellm_message_to_trace_message(msg)
        assert "latency_ms" not in trace_msg
