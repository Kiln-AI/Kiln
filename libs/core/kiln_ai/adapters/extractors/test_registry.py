from unittest.mock import patch

import pytest

from kiln_ai.adapters.extractors.litellm_extractor import LitellmExtractor
from kiln_ai.adapters.extractors.registry import extractor_adapter_from_type
from kiln_ai.adapters.ml_model_list import ModelProviderName
from kiln_ai.adapters.provider_tools import LiteLlmCoreConfig
from kiln_ai.datamodel.extraction import ExtractorConfig, ExtractorType


@pytest.fixture
def mock_provider_configs():
    with patch("kiln_ai.utils.config.Config.shared") as mock_config:
        mock_config.return_value.open_ai_api_key = "test-openai-key"
        mock_config.return_value.gemini_api_key = "test-gemini-key"
        mock_config.return_value.anthropic_api_key = "test-anthropic-key"
        mock_config.return_value.bedrock_access_key = "test-amazon-bedrock-key"
        mock_config.return_value.bedrock_secret_key = "test-amazon-bedrock-secret-key"
        mock_config.return_value.fireworks_api_key = "test-fireworks-key"
        mock_config.return_value.groq_api_key = "test-groq-key"
        mock_config.return_value.huggingface_api_key = "test-huggingface-key"
        yield mock_config


def test_extractor_adapter_from_type(mock_provider_configs):
    extractor = extractor_adapter_from_type(
        ExtractorType.LITELLM,
        ExtractorConfig(
            name="test-extractor",
            extractor_type=ExtractorType.LITELLM,
            model_provider_name="gemini_api",
            model_name="gemini-2.0-flash",
            properties={
                "prompt_document": "Extract the text from the document",
                "prompt_image": "Extract the text from the image",
                "prompt_video": "Extract the text from the video",
                "prompt_audio": "Extract the text from the audio",
            },
        ),
    )
    assert isinstance(extractor, LitellmExtractor)
    assert extractor.extractor_config.model_name == "gemini-2.0-flash"
    assert extractor.extractor_config.model_provider_name == "gemini_api"


@patch("kiln_ai.adapters.extractors.registry.lite_llm_core_config_for_provider")
def test_extractor_adapter_from_type_uses_litellm_core_config(
    mock_get_litellm_core_config,
):
    """Test that extractor receives auth details from provider_tools."""
    mock_litellm_core_config = LiteLlmCoreConfig(
        base_url="https://test.com",
        additional_body_options={"api_key": "test-key"},
        default_headers={},
    )
    mock_get_litellm_core_config.return_value = mock_litellm_core_config

    extractor = extractor_adapter_from_type(
        ExtractorType.LITELLM,
        ExtractorConfig(
            name="test-extractor",
            extractor_type=ExtractorType.LITELLM,
            model_provider_name="openai",
            model_name="gpt-4",
            properties={
                "prompt_document": "Extract the text from the document",
                "prompt_image": "Extract the text from the image",
                "prompt_video": "Extract the text from the video",
                "prompt_audio": "Extract the text from the audio",
            },
        ),
    )

    assert isinstance(extractor, LitellmExtractor)
    assert extractor.litellm_core_config == mock_litellm_core_config
    mock_get_litellm_core_config.assert_called_once_with(ModelProviderName.openai)


def test_extractor_adapter_from_type_invalid_provider():
    """Test that invalid model provider names raise a clear error."""
    with pytest.raises(
        ValueError, match="Unsupported model provider name: invalid_provider"
    ):
        extractor_adapter_from_type(
            ExtractorType.LITELLM,
            ExtractorConfig(
                name="test-extractor",
                extractor_type=ExtractorType.LITELLM,
                model_provider_name="invalid_provider",
                model_name="some-model",
                properties={
                    "prompt_document": "Extract the text from the document",
                    "prompt_image": "Extract the text from the image",
                    "prompt_video": "Extract the text from the video",
                    "prompt_audio": "Extract the text from the audio",
                },
            ),
        )


def test_extractor_adapter_from_type_invalid():
    with pytest.raises(ValueError, match="Unhandled enum value: fake_type"):
        extractor_adapter_from_type(
            "fake_type",
            ExtractorConfig(
                name="test-extractor",
                extractor_type=ExtractorType.LITELLM,
                model_provider_name="invalid_provider",
                model_name="some-model",
                properties={
                    "prompt_document": "Extract the text from the document",
                    "prompt_image": "Extract the text from the image",
                    "prompt_video": "Extract the text from the video",
                    "prompt_audio": "Extract the text from the audio",
                },
            ),
        )


@pytest.mark.parametrize(
    "provider_name",
    [
        "openai",
        "anthropic",
        "gemini_api",
        "amazon_bedrock",
        "fireworks_ai",
        "groq",
        "huggingface",
    ],
)
def test_extractor_adapter_from_type_different_providers(
    provider_name, mock_provider_configs
):
    """Test that different providers work correctly."""
    extractor = extractor_adapter_from_type(
        ExtractorType.LITELLM,
        ExtractorConfig(
            name="test-extractor",
            extractor_type=ExtractorType.LITELLM,
            model_provider_name=provider_name,
            model_name="test-model",
            properties={
                "prompt_document": "Extract the text from the document",
                "prompt_image": "Extract the text from the image",
                "prompt_video": "Extract the text from the video",
                "prompt_audio": "Extract the text from the audio",
            },
        ),
    )

    assert isinstance(extractor, LitellmExtractor)
    assert extractor.extractor_config.model_provider_name == provider_name
