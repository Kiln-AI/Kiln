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
    def _extract(self, file_info: FileInfoInternal) -> ExtractionOutput:
        return ExtractionOutput(
            is_passthrough=False,
            content="mock concrete extractor output",
            content_format=ExtractionFormat.MARKDOWN,
        )


@pytest.fixture
def mock_extractor():
    return MockBaseExtractor(BaseExtractorConfig())


def mock_extractor_with_passthroughs(
    mimetypes: list[ExtractionFormat], output_format: ExtractionFormat
):
    return MockBaseExtractor(
        BaseExtractorConfig(
            passthrough_mimetypes=mimetypes, output_format=output_format
        )
    )


def test_should_passthrough():
    extractor = MockBaseExtractor(
        BaseExtractorConfig(
            passthrough_mimetypes=[
                ExtractionFormat.TEXT,
                ExtractionFormat.MARKDOWN,
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
        [ExtractionFormat.TEXT, ExtractionFormat.MARKDOWN], ExtractionFormat.TEXT
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
        patch(
            "pathlib.Path.read_text",
            return_value=b"test content",
        ),
        patch(
            "mimetypes.guess_type",
            return_value=("text/plain", None),
        ),
    ):
        result = extractor.extract(file_info=FileInfo(path="test.txt"))

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
        [ExtractionFormat.TEXT, ExtractionFormat.MARKDOWN], output_format
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
        patch(
            "mimetypes.guess_type",
            return_value=("text/plain", None),
        ),
    ):
        result = extractor.extract(file_info=FileInfo(path="test.txt"))

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
        patch(
            "mimetypes.guess_type",
            return_value=(mime_type, None),
        ),
    ):
        # first we call the base class extract method
        result = extractor.extract(file_info=FileInfo(path=path))

        # then we call the subclass _extract method and add validated mime_type
        mock_extract.assert_called_once_with(
            FileInfoInternal(path=path, mime_type=mime_type)
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
def test_validate_passthrough_mime_types(passthrough_mimetypes: list[ExtractionFormat]):
    config = BaseExtractorConfig(passthrough_mimetypes=passthrough_mimetypes)
    assert config.passthrough_mimetypes == passthrough_mimetypes


@pytest.mark.parametrize(
    "passthrough_mimetypes",
    [
        ["image/png"],
        ["image/png", "text/markdown"],
        ["audio/mpeg"],
        ["video/mp4"],
    ],
)
def test_validate_passthrough_mime_types_failure(
    passthrough_mimetypes,
):
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
        with pytest.raises(ValueError, match="error from concrete extractor"):
            mock_extractor.extract(file_info=FileInfo(path="test.txt"))


def test_extract_failure_from_mime_type_guess():
    extractor = MockBaseExtractor(BaseExtractorConfig())
    with patch(
        "mimetypes.guess_type",
        return_value=(None, None),
    ):
        with pytest.raises(
            ValueError, match="Error extracting .*: Unable to guess file mime type"
        ):
            extractor.extract(file_info=FileInfo(path="test-xyz"))
