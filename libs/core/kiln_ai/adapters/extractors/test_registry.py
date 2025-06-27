import pytest

from kiln_ai.adapters.extractors.litellm_extractor import LitellmExtractor
from kiln_ai.adapters.extractors.registry import extractor_adapter_from_type
from kiln_ai.datamodel.extraction import ExtractorConfig, ExtractorType


def test_extractor_adapter_from_type():
    extractor = extractor_adapter_from_type(
        ExtractorType.LITELLM,
        ExtractorConfig(
            name="test-extractor",
            extractor_type=ExtractorType.LITELLM,
            properties={
                "model_provider_name": "gemini",
                "model_name": "gemini-2.0-flash",
                "prompt_document": "Extract the text from the document",
                "prompt_image": "Extract the text from the image",
                "prompt_video": "Extract the text from the video",
                "prompt_audio": "Extract the text from the audio",
            },
        ),
    )
    assert isinstance(extractor, LitellmExtractor)
    assert extractor.extractor_config.properties["model_name"] == "gemini-2.0-flash"
    assert extractor.extractor_config.properties["model_provider_name"] == "gemini"


def test_extractor_adapter_from_type_invalid():
    with pytest.raises(ValueError):
        extractor_adapter_from_type("invalid-type", {})
