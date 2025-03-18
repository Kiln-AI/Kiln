from unittest.mock import patch

import pytest

from kiln_ai import datamodel
from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.ml_model_list import ModelProviderName
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig
from kiln_ai.adapters.model_adapters.litellm_adapter import LiteLlmAdapter
from kiln_ai.adapters.prompt_builders import BasePromptBuilder
from kiln_ai.adapters.provider_tools import kiln_model_provider_from


@pytest.fixture
def mock_config():
    with patch("kiln_ai.adapters.adapter_registry.Config") as mock:
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
        yield mock


def test_openai_adapter_creation(mock_config, basic_task):
    adapter = adapter_for_task(
        kiln_task=basic_task, model_name="gpt-4", provider=ModelProviderName.openai
    )

    assert isinstance(adapter, LiteLlmAdapter)
    assert adapter.config.model_name == "gpt-4"
    assert adapter.config.additional_body_options == {"api_key": "test-openai-key"}
    assert adapter.config.provider_name == ModelProviderName.openai
    assert adapter.config.base_url is None  # OpenAI url is default
    assert adapter.config.default_headers is None


def test_openrouter_adapter_creation(mock_config, basic_task):
    adapter = adapter_for_task(
        kiln_task=basic_task,
        model_name="anthropic/claude-3-opus",
        provider=ModelProviderName.openrouter,
    )

    assert isinstance(adapter, LiteLlmAdapter)
    assert adapter.config.model_name == "anthropic/claude-3-opus"
    assert adapter.config.additional_body_options == {"api_key": "test-openrouter-key"}
    assert adapter.config.provider_name == ModelProviderName.openrouter
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
        kiln_task=basic_task, model_name="test-model", provider=provider
    )

    assert isinstance(adapter, LiteLlmAdapter)
    assert adapter.run_config.model_name == "test-model"


# TODO should run for all cases
def test_custom_prompt_builder(mock_config, basic_task):
    adapter = adapter_for_task(
        kiln_task=basic_task,
        model_name="gpt-4",
        provider=ModelProviderName.openai,
        prompt_id="simple_chain_of_thought_prompt_builder",
    )

    assert adapter.run_config.prompt_id == "simple_chain_of_thought_prompt_builder"


# TODO should run for all cases
def test_tags_passed_through(mock_config, basic_task):
    tags = ["test-tag-1", "test-tag-2"]
    adapter = adapter_for_task(
        kiln_task=basic_task,
        model_name="gpt-4",
        provider=ModelProviderName.openai,
        base_adapter_config=AdapterConfig(
            default_tags=tags,
        ),
    )

    assert adapter.base_adapter_config.default_tags == tags


def test_invalid_provider(mock_config, basic_task):
    with pytest.raises(ValueError, match="Unhandled enum value"):
        adapter_for_task(
            kiln_task=basic_task, model_name="test-model", provider="invalid"
        )


@patch("kiln_ai.adapters.adapter_registry.lite_llm_config")
def test_openai_compatible_adapter(mock_compatible_config, mock_config, basic_task):
    mock_compatible_config.return_value.model_name = "test-model"
    mock_compatible_config.return_value.additional_body_options = {
        "api_key": "test-key"
    }
    mock_compatible_config.return_value.base_url = "https://test.com/v1"
    mock_compatible_config.return_value.provider_name = "CustomProvider99"

    adapter = adapter_for_task(
        kiln_task=basic_task,
        model_name="provider::test-model",
        provider=ModelProviderName.openai_compatible,
    )

    assert isinstance(adapter, LiteLlmAdapter)
    mock_compatible_config.assert_called_once_with("provider::test-model")
    assert adapter.config == mock_compatible_config.return_value


def test_custom_openai_compatible_provider(mock_config, basic_task):
    adapter = adapter_for_task(
        kiln_task=basic_task,
        model_name="openai::test-model",
        provider=ModelProviderName.kiln_custom_registry,
    )

    assert isinstance(adapter, LiteLlmAdapter)
    assert adapter.config.model_name == "openai::test-model"
    assert adapter.config.additional_body_options == {"api_key": "test-openai-key"}
    assert adapter.config.base_url is None  # openai is none
    assert adapter.config.provider_name == ModelProviderName.kiln_custom_registry


async def test_fine_tune_provider(mock_config, basic_task, mock_finetune_from_id):
    adapter = adapter_for_task(
        kiln_task=basic_task,
        model_name="proj::task::tune",
        provider=ModelProviderName.kiln_fine_tune,
    )

    mock_finetune_from_id.assert_called_once_with("proj::task::tune")
    assert isinstance(adapter, LiteLlmAdapter)
    assert adapter.config.provider_name == ModelProviderName.kiln_fine_tune
    # Kiln model name here, but the underlying openai model id below
    assert adapter.config.model_name == "proj::task::tune"

    provider = kiln_model_provider_from(
        "proj::task::tune", provider_name=ModelProviderName.kiln_fine_tune
    )
    # The actual model name from the fine tune object
    assert provider.model_id == "test-model"
