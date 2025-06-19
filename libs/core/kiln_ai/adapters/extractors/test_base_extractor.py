from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from kiln_ai.adapters.extractors.base_extractor import BaseExtractor, ExtractionOutput
from kiln_ai.datamodel.extraction import ExtractorConfig, ExtractorType, OutputFormat


class MockBaseExtractor(BaseExtractor):
    async def _extract(self, path: Path, mime_type: str) -> ExtractionOutput:
        return ExtractionOutput(
            is_passthrough=False,
            content="mock concrete extractor output",
            content_format=OutputFormat.MARKDOWN,
        )


@pytest.fixture
def mock_gemini_properties():
    return {
        "prompt_document": "mock prompt for document",
        "prompt_image": "mock prompt for image",
        "prompt_video": "mock prompt for video",
        "prompt_audio": "mock prompt for audio",
        "model_name": "mock",
    }


@pytest.fixture
def mock_extractor(mock_gemini_properties):
    return MockBaseExtractor(
        ExtractorConfig(
            name="mock",
            extractor_type=ExtractorType.GEMINI,
            output_format=OutputFormat.MARKDOWN,
            properties=mock_gemini_properties,
        )
    )


def mock_extractor_with_passthroughs(
    properties: dict[str, Any],
    mimetypes: list[OutputFormat],
    output_format: OutputFormat,
):
    return MockBaseExtractor(
        ExtractorConfig(
            name="mock",
            extractor_type=ExtractorType.GEMINI,
            passthrough_mimetypes=mimetypes,
            output_format=output_format,
            properties=properties,
        )
    )


def test_should_passthrough(mock_gemini_properties):
    extractor = mock_extractor_with_passthroughs(
        mock_gemini_properties,
        [OutputFormat.TEXT, OutputFormat.MARKDOWN],
        OutputFormat.TEXT,
    )

    # should passthrough
    assert extractor._should_passthrough("text/plain")
    assert extractor._should_passthrough("text/markdown")

    # should not passthrough
    assert not extractor._should_passthrough("image/png")
    assert not extractor._should_passthrough("application/pdf")
    assert not extractor._should_passthrough("text/html")
    assert not extractor._should_passthrough("image/jpeg")


async def test_extract_passthrough(mock_gemini_properties):
    """
    Tests that when a file's MIME type is configured for passthrough, the extractor skips
    the concrete extraction method and returns the file's contents directly with the
    correct passthrough output format.
    """
    extractor = mock_extractor_with_passthroughs(
        mock_gemini_properties,
        [OutputFormat.TEXT, OutputFormat.MARKDOWN],
        OutputFormat.TEXT,
    )
    with (
        patch.object(
            extractor,
            "_extract",
            return_value=ExtractionOutput(
                is_passthrough=False,
                content="mock concrete extractor output",
                content_format=OutputFormat.TEXT,
            ),
        ) as mock_extract,
        patch(
            "pathlib.Path.read_text",
            return_value=b"test content",
        ),
    ):
        result = await extractor.extract(path="test.txt", mime_type="text/plain")

        # Verify _extract was not called
        mock_extract.assert_not_called()

        # Verify correct passthrough result
        assert result.is_passthrough
        assert result.content == "test content"
        assert result.content_format == OutputFormat.TEXT


@pytest.mark.parametrize(
    "output_format",
    [
        "text/plain",
        "text/markdown",
    ],
)
async def test_extract_passthrough_output_format(mock_gemini_properties, output_format):
    extractor = mock_extractor_with_passthroughs(
        mock_gemini_properties,
        [OutputFormat.TEXT, OutputFormat.MARKDOWN],
        output_format,
    )
    with (
        patch.object(
            extractor,
            "_extract",
            return_value=ExtractionOutput(
                is_passthrough=False,
                content="mock concrete extractor output",
                content_format=output_format,
            ),
        ) as mock_extract,
        patch(
            "pathlib.Path.read_text",
            return_value="test content",
        ),
    ):
        result = await extractor.extract(path="test.txt", mime_type="text/plain")

        # Verify _extract was not called
        mock_extract.assert_not_called()

        # Verify correct passthrough result
        assert result.is_passthrough
        assert result.content == "test content"
        assert result.content_format == output_format


@pytest.mark.parametrize(
    "path, mime_type, output_format",
    [
        ("test.mp3", "audio/mpeg", OutputFormat.TEXT),
        ("test.png", "image/png", OutputFormat.TEXT),
        ("test.pdf", "application/pdf", OutputFormat.TEXT),
        ("test.txt", "text/plain", OutputFormat.MARKDOWN),
        ("test.txt", "text/markdown", OutputFormat.MARKDOWN),
        ("test.html", "text/html", OutputFormat.MARKDOWN),
        ("test.csv", "text/csv", OutputFormat.MARKDOWN),
    ],
)
async def test_extract_non_passthrough(
    mock_extractor, path: str, mime_type: str, output_format: OutputFormat
):
    with (
        patch.object(
            mock_extractor,
            "_extract",
            return_value=ExtractionOutput(
                is_passthrough=False,
                content="mock concrete extractor output",
                content_format=output_format,
            ),
        ) as mock_extract,
    ):
        # first we call the base class extract method
        result = await mock_extractor.extract(path=path, mime_type=mime_type)

        # then we call the subclass _extract method and add validated mime_type
        mock_extract.assert_called_once_with(path=Path(path), mime_type=mime_type)

        assert not result.is_passthrough
        assert result.content == "mock concrete extractor output"
        assert result.content_format == output_format


async def test_default_output_format(mock_gemini_properties):
    config = ExtractorConfig(
        name="mock",
        extractor_type=ExtractorType.GEMINI,
        properties=mock_gemini_properties,
    )
    assert config.output_format == OutputFormat.MARKDOWN


async def test_extract_failure_from_concrete_extractor(mock_extractor):
    with patch.object(
        mock_extractor,
        "_extract",
        side_effect=Exception("error from concrete extractor"),
    ):
        with pytest.raises(ValueError, match="error from concrete extractor"):
            await mock_extractor.extract(path="test.txt", mime_type="text/plain")
