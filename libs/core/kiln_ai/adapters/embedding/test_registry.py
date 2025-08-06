from unittest.mock import patch

import pytest

from kiln_ai.adapters.embedding.litellm_embedding_adapter import LitellmEmbeddingAdapter
from kiln_ai.adapters.embedding.registry import embedding_adapter_from_type
from kiln_ai.adapters.ml_model_list import ModelProviderName
from kiln_ai.adapters.provider_tools import LiteLlmCoreConfig
from kiln_ai.datamodel.embedding import EmbeddingConfig


@pytest.fixture
def mock_provider_configs():
    with patch("kiln_ai.utils.config.Config.shared") as mock_config:
        mock_config.return_value.open_ai_api_key = "test-openai-key"
        mock_config.return_value.gemini_api_key = "test-gemini-key"
        yield mock_config


def test_embedding_adapter_from_type(mock_provider_configs):
    """Test basic embedding adapter creation with valid config."""
    embedding_config = EmbeddingConfig(
        name="test-embedding",
        model_provider_name=ModelProviderName.gemini_api,
        model_name="text-embedding-003",
        properties={"dimensions": 768},
    )

    adapter = embedding_adapter_from_type(embedding_config)

    assert isinstance(adapter, LitellmEmbeddingAdapter)
    assert adapter.embedding_config.model_name == "text-embedding-003"
    assert adapter.embedding_config.model_provider_name == ModelProviderName.gemini_api


@patch("kiln_ai.adapters.embedding.registry.lite_llm_core_config_for_provider")
def test_embedding_adapter_from_type_uses_litellm_core_config(
    mock_get_litellm_core_config,
):
    """Test that embedding adapter receives auth details from provider_tools."""
    mock_litellm_core_config = LiteLlmCoreConfig(
        base_url="https://test.com",
        additional_body_options={"api_key": "test-key"},
        default_headers={},
    )
    mock_get_litellm_core_config.return_value = mock_litellm_core_config

    embedding_config = EmbeddingConfig(
        name="test-embedding",
        model_provider_name=ModelProviderName.openai,
        model_name="text-embedding-3-small",
        properties={"dimensions": 1536},
    )

    adapter = embedding_adapter_from_type(embedding_config)

    assert isinstance(adapter, LitellmEmbeddingAdapter)
    assert adapter.litellm_core_config == mock_litellm_core_config
    mock_get_litellm_core_config.assert_called_once()


def test_embedding_adapter_from_type_invalid_provider():
    """Test that invalid model provider names raise a clear error."""
    # Create a valid config first, then test the enum conversion logic
    embedding_config = EmbeddingConfig(
        name="test-embedding",
        model_provider_name=ModelProviderName.openai,
        model_name="some-model",
        properties={"dimensions": 768},
    )

    # Mock the ModelProviderName constructor to simulate an invalid provider
    with patch("kiln_ai.adapters.embedding.registry.ModelProviderName") as mock_enum:
        mock_enum.side_effect = ValueError("Invalid provider")

        with pytest.raises(
            ValueError,
            match="Unsupported model provider name: ModelProviderName.openai",
        ):
            embedding_adapter_from_type(embedding_config)


def test_embedding_adapter_from_type_no_config_found(mock_provider_configs):
    """Test that missing provider configuration raises an error."""
    with patch(
        "kiln_ai.adapters.embedding.registry.lite_llm_core_config_for_provider"
    ) as mock_lite_llm_core_config_for_provider:
        mock_lite_llm_core_config_for_provider.return_value = None

        embedding_config = EmbeddingConfig(
            name="test-embedding",
            model_provider_name=ModelProviderName.openai,
            model_name="text-embedding-3-small",
            properties={"dimensions": 1536},
        )

        with pytest.raises(
            ValueError, match="No configuration found for core provider:"
        ):
            embedding_adapter_from_type(embedding_config)


@pytest.mark.parametrize(
    "provider_name",
    [
        ModelProviderName.openai,
        ModelProviderName.gemini_api,
    ],
)
def test_embedding_adapter_from_type_different_providers(
    provider_name, mock_provider_configs
):
    """Test that different providers work correctly."""
    embedding_config = EmbeddingConfig(
        name="test-embedding",
        model_provider_name=provider_name,
        model_name="test-model",
        properties={"dimensions": 768},
    )

    adapter = embedding_adapter_from_type(embedding_config)

    assert isinstance(adapter, LitellmEmbeddingAdapter)
    assert adapter.embedding_config.model_provider_name == provider_name


def test_embedding_adapter_from_type_with_description(mock_provider_configs):
    """Test embedding adapter creation with description."""
    embedding_config = EmbeddingConfig(
        name="test-embedding",
        description="Test embedding configuration",
        model_provider_name=ModelProviderName.openai,
        model_name="text-embedding-3-small",
        properties={"dimensions": 1536},
    )

    adapter = embedding_adapter_from_type(embedding_config)

    assert isinstance(adapter, LitellmEmbeddingAdapter)
    assert adapter.embedding_config.description == "Test embedding configuration"


def test_embedding_adapter_from_type_with_additional_properties(
    mock_provider_configs,
):
    """Test embedding adapter creation with additional properties."""
    embedding_config = EmbeddingConfig(
        name="test-embedding",
        model_provider_name=ModelProviderName.openai,
        model_name="text-embedding-3-small",
        properties={
            "dimensions": 1536,
            "batch_size": 100,
            "max_retries": 3,
        },
    )

    adapter = embedding_adapter_from_type(embedding_config)

    assert isinstance(adapter, LitellmEmbeddingAdapter)
    assert adapter.embedding_config.properties["batch_size"] == 100
    assert adapter.embedding_config.properties["max_retries"] == 3
