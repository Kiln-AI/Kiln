import pytest

from kiln_ai.adapters.extractors.gemini_extractor import GeminiExtractor
from kiln_ai.adapters.extractors.registry import extractor_adapter_from_type
from kiln_ai.datamodel.extraction import ExtractorType


def test_extractor_adapter_from_type():
    assert extractor_adapter_from_type(ExtractorType.gemini) == GeminiExtractor


def test_extractor_adapter_from_type_invalid():
    with pytest.raises(ValueError):
        extractor_adapter_from_type("invalid-type")  # type: ignore
