import tempfile
from unittest.mock import patch

import pytest

from kiln_ai.adapters.extractors.base_extractor import (
    BaseExtractor,
    BaseExtractorConfig,
    ExtractionFormat,
    ExtractionOutput,
    FileInfo,
    FileInfoInternal,
)


class MockBaseExtractor(BaseExtractor):
    def _extract(
        self, file_info: FileInfo, custom_prompt: str | None
    ) -> ExtractionOutput:
        """
        Returns a fixed extraction output for testing purposes.
        
        Args:
            file_info: Information about the file to extract from.
            custom_prompt: Optional custom prompt for extraction.
        
        Returns:
            An ExtractionOutput with mock content and Markdown format.
        """
        return ExtractionOutput(
            is_passthrough=False,
            content="mock concrete extractor output",
            content_format=ExtractionFormat.MARKDOWN,
        )


@pytest.fixture
def mock_extractor():
    """
    Pytest fixture that returns a MockBaseExtractor instance with default configuration.
    """
    return MockBaseExtractor(BaseExtractorConfig())


def mock_extractor_with_passthroughs(
    mimetypes: list[str], output_format: ExtractionFormat
):
    """
    Creates a mock extractor instance configured with specified passthrough MIME types and output format.
    
    Args:
        mimetypes: List of MIME types to be treated as passthrough.
        output_format: The output format to use for passthrough extraction.
    
    Returns:
        An instance of MockBaseExtractor with the given configuration.
    """
    return MockBaseExtractor(
        BaseExtractorConfig(
            passthrough_mimetypes=mimetypes, output_format=output_format
        )
    )


def test_load_file_bytes(mock_extractor):
    # write a test file to the temp directory
    """
    Tests that _load_file_bytes correctly reads and returns the contents of a file as bytes.
    """
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(b"test")
        temp_file_path = temp_file.name
    assert mock_extractor._load_file_bytes(temp_file_path) == b"test"


def test_load_file_bytes_failure(mock_extractor):
    """
    Tests that _load_file_bytes raises ValueError when file loading fails.
    """
    with patch(
        "kiln_ai.adapters.extractors.base_extractor.file_utils.load_file_bytes",
        side_effect=Exception,
    ):
        with pytest.raises(ValueError):
            mock_extractor._load_file_bytes("nonexistent.txt")


def test_load_file_text(mock_extractor):
    # write a test file to the temp directory
    """
    Tests that the _load_file_text method correctly reads and returns file contents as a string.
    """
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(b"test")
        temp_file_path = temp_file.name
    assert mock_extractor._load_file_text(temp_file_path) == "test"


def test_load_file_text_failure(mock_extractor):
    """
    Tests that _load_file_text raises ValueError when file reading fails.
    """
    with patch(
        "kiln_ai.adapters.extractors.base_extractor.file_utils.load_file_text",
        side_effect=Exception,
    ):
        with pytest.raises(ValueError):
            mock_extractor._load_file_text("nonexistent.txt")


# parametrize for txt -> text/plain, png -> image/png, etc.
@pytest.mark.parametrize(
    "path, expected_mime_type",
    [
        ("test.txt", "text/plain"),
        ("test.png", "image/png"),
        ("test.pdf", "application/pdf"),
    ],
)
def test_get_mime_type(mock_extractor, path: str, expected_mime_type: str):
    """
    Tests that the extractor correctly determines the MIME type for a given file path.
    
    Args:
        path: The file path whose MIME type is to be detected.
        expected_mime_type: The expected MIME type string.
    """
    assert mock_extractor._get_mime_type(path) == expected_mime_type


def test_get_mime_type_failure(mock_extractor):
    """
    Tests that _get_mime_type raises ValueError when MIME type detection fails.
    """
    with patch(
        "kiln_ai.adapters.extractors.base_extractor.file_utils.get_mime_type",
        side_effect=Exception,
    ):
        with pytest.raises(ValueError):
            mock_extractor._get_mime_type("nonexistent.some-unknown-file-type")


def test_should_passthrough():
    extractor = MockBaseExtractor(
        BaseExtractorConfig(
            passthrough_mimetypes=[
                "text/plain",
                "text/markdown",
            ]
        )
    )

    # should passthrough
    assert extractor._should_passthrough("text/plain")
    assert extractor._should_passthrough("text/markdown")

    # should not passthrough
    assert not extractor._should_passthrough("image/png")
    assert not extractor._should_passthrough("application/pdf")
    assert not extractor._should_passthrough("text/html")
    assert not extractor._should_passthrough("image/jpeg")


def test_extract_passthrough():
    """
    Tests that when a file's MIME type is configured for passthrough, the extractor skips
    the concrete extraction method and returns the file's contents directly with the
    correct passthrough output format.
    """
    extractor = mock_extractor_with_passthroughs(
        ["text/plain", "text/markdown"], ExtractionFormat.TEXT
    )
    with (
        patch.object(
            extractor,
            "_extract",
            return_value=ExtractionOutput(
                is_passthrough=False,
                content="mock concrete extractor output",
                content_format=ExtractionFormat.TEXT,
            ),
        ) as mock_extract,
        patch.object(extractor, "_load_file_text", return_value="test content"),
        patch.object(extractor, "_get_mime_type", return_value="text/plain"),
    ):
        result = extractor.extract(
            file_info=FileInfo(path="test.txt"), custom_prompt=None
        )

        # Verify _extract was not called
        mock_extract.assert_not_called()

        # Verify correct passthrough result
        assert result.is_passthrough == True
        assert result.content == "test content"
        assert result.content_format == ExtractionFormat.TEXT


@pytest.mark.parametrize(
    "output_format",
    [
        ExtractionFormat.TEXT,
        ExtractionFormat.MARKDOWN,
    ],
)
def test_extract_passthrough_output_format(output_format: ExtractionFormat):
    """
    Tests that passthrough extraction returns content with the configured output format.
    
    Verifies that when a file's MIME type is set for passthrough, the extractor bypasses
    the concrete extraction method and returns the file content with the specified output
    format.
    """
    extractor = mock_extractor_with_passthroughs(
        ["text/plain", "text/markdown"], output_format
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
        patch.object(extractor, "_load_file_text", return_value="test content"),
        patch.object(extractor, "_get_mime_type", return_value="text/plain"),
    ):
        result = extractor.extract(
            file_info=FileInfo(path="test.txt"), custom_prompt=None
        )

        # Verify _extract was not called
        mock_extract.assert_not_called()

        # Verify correct passthrough result
        assert result.is_passthrough == True
        assert result.content == "test content"
        assert result.content_format == output_format


@pytest.mark.parametrize(
    "path, mime_type, output_format",
    [
        ("test.mp3", "audio/mpeg", ExtractionFormat.TEXT),
        ("test.png", "image/png", ExtractionFormat.TEXT),
        ("test.pdf", "application/pdf", ExtractionFormat.TEXT),
        ("test.txt", "text/plain", ExtractionFormat.MARKDOWN),
        ("test.txt", "text/markdown", ExtractionFormat.MARKDOWN),
        ("test.html", "text/html", ExtractionFormat.MARKDOWN),
        ("test.csv", "text/csv", ExtractionFormat.MARKDOWN),
    ],
)
def test_extract_non_passthrough(
    path: str, mime_type: str, output_format: ExtractionFormat
):
    """
    Verifies that files with non-passthrough MIME types invoke the subclass's _extract method and return its output.
    
    Ensures the extract method calls the concrete _extract implementation with the correct file info and returns the expected ExtractionOutput for non-passthrough files.
    """
    extractor = MockBaseExtractor(BaseExtractorConfig(output_format=output_format))

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
        patch.object(extractor, "_get_mime_type", return_value=mime_type),
    ):
        # first we call the base class extract method
        result = extractor.extract(file_info=FileInfo(path=path), custom_prompt=None)

        # then we call the subclass _extract method and add validated mime_type
        mock_extract.assert_called_once_with(
            FileInfoInternal(path=path, mime_type=mime_type), None
        )

        assert result.is_passthrough == False
        assert result.content == "mock concrete extractor output"
        assert result.content_format == output_format


@pytest.mark.parametrize(
    "passthrough_mimetypes",
    [
        ["text/plain"],
        ["text/markdown"],
        ["text/plain", "text/markdown"],
    ],
)
def test_validate_passthrough_mime_types(passthrough_mimetypes: list[str]):
    """
    Tests that BaseExtractorConfig accepts text-based passthrough MIME types without error.
    """
    config = BaseExtractorConfig(passthrough_mimetypes=passthrough_mimetypes)
    assert config.passthrough_mimetypes == passthrough_mimetypes


@pytest.mark.parametrize(
    "passthrough_mimetypes",
    [
        ["image/png"],
        ["image/png", "text/html"],
        ["audio/mpeg"],
        ["video/mp4"],
    ],
)
def test_validate_passthrough_mime_types_failure(passthrough_mimetypes: list[str]):
    """
    Tests that BaseExtractorConfig raises ValueError when configured with non-text passthrough MIME types.
    """
    with pytest.raises(ValueError):
        BaseExtractorConfig(passthrough_mimetypes=passthrough_mimetypes)


def test_default_output_format():
    """
    Verifies that the default output format in BaseExtractorConfig is MARKDOWN.
    """
    config = BaseExtractorConfig()
    assert config.output_format == ExtractionFormat.MARKDOWN


def test_extract_failure_from_concrete_extractor(mock_extractor):
    """
    Tests that the extract method raises a ValueError when the concrete extractor implementation fails.
    """
    with patch.object(
        mock_extractor,
        "_extract",
        side_effect=Exception("error from concrete extractor"),
    ):
        with pytest.raises(ValueError):
            mock_extractor.extract(
                file_info=FileInfo(path="test.txt"), custom_prompt=None
            )
