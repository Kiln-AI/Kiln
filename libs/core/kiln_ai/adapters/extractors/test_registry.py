from unittest.mock import patch

import pytest

from kiln_ai.adapters.extractors.litellm_extractor import LitellmExtractor
from kiln_ai.adapters.extractors.registry import extractor_adapter_from_type
from kiln_ai.adapters.ml_model_list import ModelProviderName
from kiln_ai.datamodel.extraction import ExtractorConfig, ExtractorType


def test_extractor_adapter_from_type():
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


@patch("kiln_ai.adapters.extractors.registry.get_provider_auth_details")
def test_extractor_adapter_from_type_uses_auth_details(mock_get_auth):
    """Test that extractor receives auth details from provider_tools."""
    mock_auth_details = {"api_key": "test-key", "base_url": "https://test.com"}
    mock_get_auth.return_value = mock_auth_details

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
    assert extractor.provider_auth == mock_auth_details
    mock_get_auth.assert_called_once_with(ModelProviderName.openai)


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
    "provider_name", ["openai", "anthropic", "gemini_api", "amazon_bedrock"]
)
def test_extractor_adapter_from_type_different_providers(provider_name):
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
