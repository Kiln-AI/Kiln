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
        self, file_info: FileInfoInternal, custom_prompt: str | None
    ) -> ExtractionOutput:
        return ExtractionOutput(
            is_passthrough=False,
            content="mock concrete extractor output",
            content_format=ExtractionFormat.MARKDOWN,
        )


@pytest.fixture
def mock_extractor():
    return MockBaseExtractor(BaseExtractorConfig())


def mock_extractor_with_passthroughs(
    mimetypes: list[str], output_format: ExtractionFormat
):
    return MockBaseExtractor(
        BaseExtractorConfig(
            passthrough_mimetypes=mimetypes, output_format=output_format
        )
    )


def test_load_file_bytes(mock_extractor):
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(b"test")
        temp_file_path = temp_file.name
    assert mock_extractor._load_file_bytes(temp_file_path) == b"test"


def test_load_file_bytes_failure(mock_extractor):
    with patch(
        "kiln_ai.adapters.extractors.base_extractor.file_utils.load_file_bytes",
        side_effect=Exception,
    ):
        with pytest.raises(ValueError):
            mock_extractor._load_file_bytes("nonexistent.txt")


def test_load_file_text(mock_extractor):
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(b"test")
        temp_file_path = temp_file.name
    assert mock_extractor._load_file_text(temp_file_path) == "test"


def test_load_file_text_failure(mock_extractor):
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
    assert mock_extractor._get_mime_type(path) == expected_mime_type


def test_get_mime_type_failure(mock_extractor):
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
        assert result.is_passthrough
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
        assert result.is_passthrough
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

        assert not result.is_passthrough
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
    with pytest.raises(ValueError):
        BaseExtractorConfig(passthrough_mimetypes=passthrough_mimetypes)


def test_default_output_format():
    config = BaseExtractorConfig()
    assert config.output_format == ExtractionFormat.MARKDOWN


def test_extract_failure_from_concrete_extractor(mock_extractor):
    with patch.object(
        mock_extractor,
        "_extract",
        side_effect=Exception("error from concrete extractor"),
    ):
        with pytest.raises(ValueError):
            mock_extractor.extract(
                file_info=FileInfo(path="test.txt"), custom_prompt=None
            )
