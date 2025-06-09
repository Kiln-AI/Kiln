from unittest.mock import MagicMock, patch

import pytest

from kiln_ai.adapters.extractors.gemini_extractor import GeminiExtractor
from kiln_ai.adapters.extractors.registry import extractor_adapter_from_type
from kiln_ai.datamodel.extraction import ExtractorConfig, ExtractorType


def test_extractor_adapter_from_type():
    with patch(
        "kiln_ai.adapters.extractors.gemini_extractor.genai.Client"
    ) as mock_genai_client:
        mock_genai_client.return_value = MagicMock()

        extractor = extractor_adapter_from_type(
            ExtractorType.GEMINI,
            ExtractorConfig(
                name="test-extractor",
                extractor_type=ExtractorType.GEMINI,
                properties={
                    "model_name": "gemini-2.0-flash",
                    "prompt_for_kind": {
                        "document": "Extract the text from the document",
                        "image": "Extract the text from the image",
                        "video": "Extract the text from the video",
                        "audio": "Extract the text from the audio",
                    },
                },
            ),
        )
        assert isinstance(extractor, GeminiExtractor)
        assert extractor.model_name == "gemini-2.0-flash"
        assert extractor.gemini_client is not None


def test_extractor_adapter_from_type_invalid():
    with pytest.raises(ValueError):
        extractor_adapter_from_type("invalid-type", {})
