from os import getenv
from unittest.mock import Mock, patch

import pytest

from kiln_ai import datamodel
from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.ml_model_list import ModelProviderName
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig
from kiln_ai.adapters.model_adapters.litellm_adapter import (
    LiteLlmAdapter,
    LiteLlmConfig,
)
from kiln_ai.adapters.provider_tools import Config, kiln_model_provider_from
from kiln_ai.datamodel.task import RunConfigProperties


@pytest.fixture
def mock_config():
    with patch("kiln_ai.adapters.provider_tools.Config") as mock:
        mock.shared.return_value.open_ai_api_key = "test-openai-key"
        mock.shared.return_value.open_router_api_key = "test-openrouter-key"
        yield mock


@pytest.fixture
def basic_task():
    return datamodel.Task(
        task_id="test-task",
        task_type="test",
        input_text="test input",
        name="test-task",
        instruction="test-task",
    )


@pytest.fixture
def mock_finetune_from_id():
    with patch("kiln_ai.adapters.provider_tools.finetune_from_id") as mock:
        mock.return_value.provider = ModelProviderName.openai
        mock.return_value.fine_tune_model_id = "test-model"
        mock.return_value.data_strategy = "final_only"
        yield mock


def test_openai_adapter_creation(mock_config, basic_task):
    with patch(
        "kiln_ai.adapters.adapter_registry.get_provider_auth_details"
    ) as mock_auth:
        mock_auth.return_value = {"api_key": "test-openai-key"}

        adapter = adapter_for_task(
            kiln_task=basic_task,
            run_config_properties=RunConfigProperties(
                model_name="gpt-4",
                model_provider_name=ModelProviderName.openai,
                prompt_id="simple_prompt_builder",
                structured_output_mode="json_schema",
            ),
        )

        # Verify the new auth system is used
        mock_auth.assert_called_once_with(ModelProviderName.openai)

        # Verify adapter configuration
        assert isinstance(adapter, LiteLlmAdapter)
        assert adapter.config.run_config_properties.model_name == "gpt-4"
        assert adapter.config.additional_body_options == {"api_key": "test-openai-key"}
        assert (
            adapter.config.run_config_properties.model_provider_name
            == ModelProviderName.openai
        )
        assert adapter.config.base_url is None  # OpenAI url is default
        assert adapter.config.default_headers is None


def test_openrouter_adapter_creation(mock_config, basic_task):
    with patch(
        "kiln_ai.adapters.adapter_registry.get_provider_auth_details"
    ) as mock_auth:
        mock_auth.return_value = {
            "api_key": "test-openrouter-key",
            "base_url": "https://openrouter.ai/api/v1",
            "default_headers": {
                "HTTP-Referer": "https://getkiln.ai/openrouter",
                "X-Title": "KilnAI",
            },
        }

        adapter = adapter_for_task(
            kiln_task=basic_task,
            run_config_properties=RunConfigProperties(
                model_name="anthropic/claude-3-opus",
                model_provider_name=ModelProviderName.openrouter,
                prompt_id="simple_prompt_builder",
                structured_output_mode="json_schema",
            ),
        )

        # Verify the new auth system is used
        mock_auth.assert_called_once_with(ModelProviderName.openrouter)

        # Verify adapter configuration including complex auth (headers + base_url)
        assert isinstance(adapter, LiteLlmAdapter)
        assert (
            adapter.config.run_config_properties.model_name == "anthropic/claude-3-opus"
        )
        assert adapter.config.additional_body_options == {
            "api_key": "test-openrouter-key"
        }
        assert adapter.config.base_url == "https://openrouter.ai/api/v1"
        assert adapter.config.default_headers == {
            "HTTP-Referer": "https://getkiln.ai/openrouter",
            "X-Title": "KilnAI",
        }
        assert (
            adapter.config.run_config_properties.model_provider_name
            == ModelProviderName.openrouter
        )
    assert adapter.config.default_headers == {
        "HTTP-Referer": "https://getkiln.ai/openrouter",
        "X-Title": "KilnAI",
    }


@pytest.mark.parametrize(
    "provider",
    [
        ModelProviderName.groq,
        ModelProviderName.amazon_bedrock,
        ModelProviderName.ollama,
        ModelProviderName.fireworks_ai,
    ],
)
def test_openai_compatible_adapter_creation(mock_config, basic_task, provider):
    adapter = adapter_for_task(
        kiln_task=basic_task,
        run_config_properties=RunConfigProperties(
            model_name="test-model",
            model_provider_name=provider,
            prompt_id="simple_prompt_builder",
            structured_output_mode="json_schema",
        ),
    )

    assert isinstance(adapter, LiteLlmAdapter)
    assert adapter.run_config.model_name == "test-model"


# TODO should run for all cases
def test_custom_prompt_builder(mock_config, basic_task):
    adapter = adapter_for_task(
        kiln_task=basic_task,
        run_config_properties=RunConfigProperties(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_chain_of_thought_prompt_builder",
            structured_output_mode="json_schema",
        ),
    )

    assert adapter.run_config.prompt_id == "simple_chain_of_thought_prompt_builder"


# TODO should run for all cases
def test_tags_passed_through(mock_config, basic_task):
    tags = ["test-tag-1", "test-tag-2"]
    adapter = adapter_for_task(
        kiln_task=basic_task,
        run_config_properties=RunConfigProperties(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
            structured_output_mode="json_schema",
        ),
        base_adapter_config=AdapterConfig(
            default_tags=tags,
        ),
    )

    assert adapter.base_adapter_config.default_tags == tags


def test_invalid_provider(mock_config, basic_task):
    with pytest.raises(ValueError, match="Input should be"):
        adapter_for_task(
            kiln_task=basic_task,
            run_config_properties=RunConfigProperties(
                model_name="test-model",
                model_provider_name="invalid",
                prompt_id="simple_prompt_builder",
                structured_output_mode="json_schema",
            ),
        )


@patch("kiln_ai.adapters.adapter_registry.lite_llm_config_for_openai_compatible")
def test_openai_compatible_adapter(mock_compatible_config, mock_config, basic_task):
    mock_compatible_config.return_value.model_name = "test-model"
    mock_compatible_config.return_value.additional_body_options = {
        "api_key": "test-key"
    }
    mock_compatible_config.return_value.base_url = "https://test.com/v1"
    mock_compatible_config.return_value.provider_name = "CustomProvider99"
    mock_compatible_config.return_value.run_config_properties = RunConfigProperties(
        model_name="provider::test-model",
        model_provider_name=ModelProviderName.openai_compatible,
        prompt_id="simple_prompt_builder",
        structured_output_mode="json_schema",
    )

    adapter = adapter_for_task(
        kiln_task=basic_task,
        run_config_properties=RunConfigProperties(
            model_name="provider::test-model",
            model_provider_name=ModelProviderName.openai_compatible,
            prompt_id="simple_prompt_builder",
            structured_output_mode="json_schema",
        ),
    )

    assert isinstance(adapter, LiteLlmAdapter)
    mock_compatible_config.assert_called_once()
    assert adapter.config == mock_compatible_config.return_value


def test_custom_openai_compatible_provider(mock_config, basic_task):
    adapter = adapter_for_task(
        kiln_task=basic_task,
        run_config_properties=RunConfigProperties(
            model_name="openai::test-model",
            model_provider_name=ModelProviderName.kiln_custom_registry,
            prompt_id="simple_prompt_builder",
            structured_output_mode="json_schema",
        ),
    )

    assert isinstance(adapter, LiteLlmAdapter)
    assert adapter.config.run_config_properties.model_name == "openai::test-model"
    assert adapter.config.additional_body_options == {"api_key": "test-openai-key"}
    assert adapter.config.base_url is None  # openai is none
    assert (
        adapter.config.run_config_properties.model_provider_name
        == ModelProviderName.kiln_custom_registry
    )


async def test_fine_tune_provider(mock_config, basic_task, mock_finetune_from_id):
    adapter = adapter_for_task(
        kiln_task=basic_task,
        run_config_properties=RunConfigProperties(
            model_name="proj::task::tune",
            model_provider_name=ModelProviderName.kiln_fine_tune,
            prompt_id="simple_prompt_builder",
            structured_output_mode="json_schema",
        ),
    )

    mock_finetune_from_id.assert_called_once_with("proj::task::tune")
    assert isinstance(adapter, LiteLlmAdapter)
    assert (
        adapter.config.run_config_properties.model_provider_name
        == ModelProviderName.kiln_fine_tune
    )
    # Kiln model name here, but the underlying openai model id below
    assert adapter.config.run_config_properties.model_name == "proj::task::tune"

    provider = kiln_model_provider_from(
        "proj::task::tune", provider_name=ModelProviderName.kiln_fine_tune
    )
    # The actual model name from the fine tune object
    assert provider.model_id == "test-model"


@pytest.fixture
def mock_get_provider_auth_details():
    """Mock get_provider_auth_details to return predictable auth details."""
    with patch("kiln_ai.adapters.adapter_registry.get_provider_auth_details") as mock:
        yield mock


@pytest.fixture
def mock_lite_llm_config_for_openai_compatible():
    """Mock lite_llm_config_for_openai_compatible for testing."""
    with patch(
        "kiln_ai.adapters.adapter_registry.lite_llm_config_for_openai_compatible"
    ) as mock:
        yield mock


def test_adapter_for_task_core_provider_mapping(
    mock_get_provider_auth_details, basic_task
):
    """Test adapter_for_task correctly maps virtual providers to core providers."""
    # Mock auth details for the underlying provider
    mock_get_provider_auth_details.return_value = {"api_key": "test-openai-key"}

    # Use a virtual provider that should map to openai
    with patch("kiln_ai.adapters.adapter_registry.core_provider") as mock_core_provider:
        mock_core_provider.return_value = ModelProviderName.openai

        adapter = adapter_for_task(
            kiln_task=basic_task,
            run_config_properties=RunConfigProperties(
                model_name="proj::task::tune",
                model_provider_name=ModelProviderName.kiln_fine_tune,
                prompt_id="simple_prompt_builder",
                structured_output_mode="json_schema",
            ),
        )

        # Verify core_provider was called to map virtual to actual provider
        mock_core_provider.assert_called_once_with(
            "proj::task::tune", ModelProviderName.kiln_fine_tune
        )

        # Verify auth was fetched for the mapped core provider
        mock_get_provider_auth_details.assert_called_once_with(ModelProviderName.openai)

        # Verify adapter is created correctly
        assert isinstance(adapter, LiteLlmAdapter)
        assert adapter.config.additional_body_options == {"api_key": "test-openai-key"}


def test_adapter_for_task_preserves_run_config_properties(
    mock_get_provider_auth_details, basic_task
):
    """Test adapter_for_task preserves all run config properties correctly."""
    mock_get_provider_auth_details.return_value = {"api_key": "test-key"}

    run_config_props = RunConfigProperties(
        model_name="gpt-4",
        model_provider_name=ModelProviderName.openai,
        prompt_id="simple_prompt_builder",
        structured_output_mode="function_calling",
        temperature=0.7,
        top_p=0.9,
    )

    adapter = adapter_for_task(
        kiln_task=basic_task,
        run_config_properties=run_config_props,
    )

    # Verify all run config properties are preserved
    assert adapter.config.run_config_properties.model_name == "gpt-4"
    assert (
        adapter.config.run_config_properties.model_provider_name
        == ModelProviderName.openai
    )
    assert adapter.config.run_config_properties.prompt_id == "simple_prompt_builder"
    assert (
        adapter.config.run_config_properties.structured_output_mode
        == "function_calling"
    )
    assert adapter.config.run_config_properties.temperature == 0.7
    assert adapter.config.run_config_properties.top_p == 0.9


def test_adapter_for_task_with_base_adapter_config(
    mock_get_provider_auth_details, basic_task
):
    """Test adapter_for_task correctly passes through base_adapter_config."""
    mock_get_provider_auth_details.return_value = {"api_key": "test-key"}

    base_config = AdapterConfig(
        allow_saving=False,
        top_logprobs=5,
        default_tags=["test-tag-1", "test-tag-2"],
    )

    adapter = adapter_for_task(
        kiln_task=basic_task,
        run_config_properties=RunConfigProperties(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
            structured_output_mode="json_schema",
        ),
        base_adapter_config=base_config,
    )

    # Verify base adapter config is preserved
    assert adapter.base_adapter_config == base_config
    assert adapter.base_adapter_config.allow_saving is False
    assert adapter.base_adapter_config.top_logprobs == 5
    assert adapter.base_adapter_config.default_tags == ["test-tag-1", "test-tag-2"]


@pytest.fixture
def comprehensive_mock_config():
    """Mock all config values for comprehensive testing."""
    config_instance = Mock()

    # Set up all config values that the original switch used
    config_instance.open_router_api_key = "test-openrouter-key"
    config_instance.open_ai_api_key = "test-openai-key"
    config_instance.groq_api_key = "test-groq-key"
    config_instance.bedrock_access_key = "test-aws-access-key"
    config_instance.bedrock_secret_key = "test-aws-secret-key"
    config_instance.ollama_base_url = "http://test-ollama:11434"
    config_instance.fireworks_api_key = "test-fireworks-key"
    config_instance.anthropic_api_key = "test-anthropic-key"
    config_instance.gemini_api_key = "test-gemini-key"
    config_instance.vertex_project_id = "test-vertex-project"
    config_instance.vertex_location = "us-central1"
    config_instance.together_api_key = "test-together-key"
    config_instance.azure_openai_api_key = "test-azure-key"
    config_instance.azure_openai_endpoint = "https://test.openai.azure.com"
    config_instance.huggingface_api_key = "test-hf-key"

    # Mock both import locations - the refactored code uses provider_tools.Config
    # and the original switch recreation uses local Config import
    with (
        patch("kiln_ai.adapters.provider_tools.Config") as provider_tools_mock,
        patch("kiln_ai.adapters.test_adapter_registry.Config") as test_mock,
    ):
        provider_tools_mock.shared.return_value = config_instance
        test_mock.shared.return_value = config_instance

        yield provider_tools_mock


def create_config_declarative(
    provider_name: ModelProviderName, run_config_properties: RunConfigProperties
) -> LiteLlmConfig:
    """Regression test, but also easier to verify the config is what we expect for each provider."""
    match provider_name:
        case ModelProviderName.openrouter:
            return LiteLlmConfig(
                run_config_properties=run_config_properties,
                base_url=getenv("OPENROUTER_BASE_URL")
                or "https://openrouter.ai/api/v1",
                default_headers={
                    "HTTP-Referer": "https://getkiln.ai/openrouter",
                    "X-Title": "KilnAI",
                },
                additional_body_options={
                    "api_key": Config.shared().open_router_api_key,
                },
            )
        case ModelProviderName.openai:
            return LiteLlmConfig(
                run_config_properties=run_config_properties,
                additional_body_options={
                    "api_key": Config.shared().open_ai_api_key,
                },
            )
        case ModelProviderName.groq:
            return LiteLlmConfig(
                run_config_properties=run_config_properties,
                additional_body_options={
                    "api_key": Config.shared().groq_api_key,
                },
            )
        case ModelProviderName.amazon_bedrock:
            return LiteLlmConfig(
                run_config_properties=run_config_properties,
                additional_body_options={
                    "aws_access_key_id": Config.shared().bedrock_access_key,
                    "aws_secret_access_key": Config.shared().bedrock_secret_key,
                    "aws_region_name": "us-west-2",
                },
            )
        case ModelProviderName.ollama:
            ollama_base_url = (
                Config.shared().ollama_base_url or "http://localhost:11434"
            )
            return LiteLlmConfig(
                run_config_properties=run_config_properties,
                base_url=ollama_base_url + "/v1",
                additional_body_options={
                    "api_key": "NA",
                },
            )
        case ModelProviderName.fireworks_ai:
            return LiteLlmConfig(
                run_config_properties=run_config_properties,
                additional_body_options={
                    "api_key": Config.shared().fireworks_api_key,
                },
            )
        case ModelProviderName.anthropic:
            return LiteLlmConfig(
                run_config_properties=run_config_properties,
                additional_body_options={
                    "api_key": Config.shared().anthropic_api_key,
                },
            )
        case ModelProviderName.gemini_api:
            return LiteLlmConfig(
                run_config_properties=run_config_properties,
                additional_body_options={
                    "api_key": Config.shared().gemini_api_key,
                },
            )
        case ModelProviderName.vertex:
            return LiteLlmConfig(
                run_config_properties=run_config_properties,
                additional_body_options={
                    "vertex_project": Config.shared().vertex_project_id,
                    "vertex_location": Config.shared().vertex_location,
                },
            )
        case ModelProviderName.together_ai:
            return LiteLlmConfig(
                run_config_properties=run_config_properties,
                additional_body_options={
                    "api_key": Config.shared().together_api_key,
                },
            )
        case ModelProviderName.azure_openai:
            return LiteLlmConfig(
                base_url=Config.shared().azure_openai_endpoint,
                run_config_properties=run_config_properties,
                additional_body_options={
                    "api_key": Config.shared().azure_openai_api_key,
                    "api_version": "2025-02-01-preview",
                },
            )
        case ModelProviderName.huggingface:
            return LiteLlmConfig(
                run_config_properties=run_config_properties,
                additional_body_options={
                    "api_key": Config.shared().huggingface_api_key,
                },
            )
        case _:
            raise ValueError(f"Test setup error: unsupported provider {provider_name}")


@pytest.mark.parametrize(
    "provider_name,model_name",
    [
        (ModelProviderName.openrouter, "anthropic/claude-3-opus"),
        (ModelProviderName.openai, "gpt-4"),
        (ModelProviderName.groq, "llama3-8b-8192"),
        (ModelProviderName.amazon_bedrock, "anthropic.claude-3-opus-20240229-v1:0"),
        (ModelProviderName.ollama, "llama3.2"),
        (
            ModelProviderName.fireworks_ai,
            "accounts/fireworks/models/llama-v3p1-8b-instruct",
        ),
        (ModelProviderName.anthropic, "claude-3-opus-20240229"),
        (ModelProviderName.gemini_api, "gemini-1.5-pro"),
        (ModelProviderName.vertex, "gemini-1.5-pro"),
        (ModelProviderName.together_ai, "meta-llama/Llama-3.2-3B-Instruct-Turbo"),
        (ModelProviderName.azure_openai, "gpt-4"),
        (ModelProviderName.huggingface, "microsoft/DialoGPT-medium"),
    ],
)
def test_adapter_for_task_matches_original_switch(
    comprehensive_mock_config, basic_task, provider_name, model_name
):
    """
    Regression test: Verify refactored adapter_for_task produces identical results
    to the original switch statement for all providers.
    """
    # Standard run config properties for testing
    run_config_props = RunConfigProperties(
        model_name=model_name,
        model_provider_name=provider_name,
        prompt_id="simple_prompt_builder",
        structured_output_mode="json_schema",
    )

    # Get the adapter from the new refactored function
    adapter = adapter_for_task(
        kiln_task=basic_task,
        run_config_properties=run_config_props,
    )

    # Create what the original switch would have produced
    expected_config = create_config_declarative(provider_name, run_config_props)

    # Compare the configurations field by field
    actual_config = adapter.config

    assert actual_config.run_config_properties == expected_config.run_config_properties
    assert actual_config.base_url == expected_config.base_url
    assert actual_config.default_headers == expected_config.default_headers
    assert (
        actual_config.additional_body_options == expected_config.additional_body_options
    )


@patch.dict(
    "os.environ", {"OPENROUTER_BASE_URL": "https://custom-openrouter.example.com"}
)
def test_adapter_for_task_matches_original_switch_openrouter_env_var(
    comprehensive_mock_config, basic_task
):
    """
    Test that OpenRouter respects the OPENROUTER_BASE_URL environment variable
    exactly like the original switch statement did.
    """
    run_config_props = RunConfigProperties(
        model_name="anthropic/claude-3-opus",
        model_provider_name=ModelProviderName.openrouter,
        prompt_id="simple_prompt_builder",
        structured_output_mode="json_schema",
    )

    # Get adapter from refactored function
    adapter = adapter_for_task(
        kiln_task=basic_task,
        run_config_properties=run_config_props,
    )

    # Create what original switch would have produced
    expected_config = create_config_declarative(
        ModelProviderName.openrouter, run_config_props
    )

    # Both should use the custom environment variable
    assert adapter.config.base_url == "https://custom-openrouter.example.com"
    assert adapter.config.base_url == expected_config.base_url


def test_adapter_for_task_matches_original_switch_ollama_default_url(
    comprehensive_mock_config, basic_task
):
    """
    Test that Ollama falls back to default URL when none configured,
    exactly like the original switch statement did.
    """
    # Override mock to return None for ollama_base_url
    comprehensive_mock_config.shared.return_value.ollama_base_url = None

    run_config_props = RunConfigProperties(
        model_name="llama3.2",
        model_provider_name=ModelProviderName.ollama,
        prompt_id="simple_prompt_builder",
        structured_output_mode="json_schema",
    )

    # Get adapter from refactored function
    adapter = adapter_for_task(
        kiln_task=basic_task,
        run_config_properties=run_config_props,
    )

    # Create what original switch would have produced
    expected_config = create_config_declarative(
        ModelProviderName.ollama, run_config_props
    )

    # Both should use the default localhost URL
    assert adapter.config.base_url == "http://localhost:11434/v1"
    assert adapter.config.base_url == expected_config.base_url


def test_adapter_for_task_openai_compatible_bypasses_regression_test(
    comprehensive_mock_config, basic_task
):
    """
    Verify that OpenAI compatible providers still bypass the normal auth logic
    and use lite_llm_config_for_openai_compatible, just like the original.
    """
    with patch(
        "kiln_ai.adapters.adapter_registry.lite_llm_config_for_openai_compatible"
    ) as mock_openai_compat:
        mock_config = LiteLlmConfig(
            run_config_properties=RunConfigProperties(
                model_name="test-model",
                model_provider_name=ModelProviderName.openai_compatible,
                prompt_id="simple_prompt_builder",
                structured_output_mode="json_schema",
            ),
            base_url="https://custom-api.com/v1",
            additional_body_options={"api_key": "custom-key"},
        )
        mock_openai_compat.return_value = mock_config

        run_config_props = RunConfigProperties(
            model_name="custom::test-model",
            model_provider_name=ModelProviderName.openai_compatible,
            prompt_id="simple_prompt_builder",
            structured_output_mode="json_schema",
        )

        adapter = adapter_for_task(
            kiln_task=basic_task,
            run_config_properties=run_config_props,
        )

        # Verify it uses the special config function (same as original)
        mock_openai_compat.assert_called_once()
        assert adapter.config == mock_config
