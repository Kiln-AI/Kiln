from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from google import genai
from google.genai import types

from kiln_ai.adapters.extractors.base_extractor import (
    ExtractionOutput,
    FileInfo,
    FileInfoInternal,
    OutputFormat,
)
from kiln_ai.adapters.extractors.gemini_extractor import (
    ExtractorConfig,
    GeminiExtractor,
    Kind,
)
from kiln_ai.utils.config import Config

PROMPTS_FOR_KIND: dict[str, str] = {
    "document": "prompt for documents",
    "image": "prompt for images",
    "video": "prompt for videos",
    "audio": "prompt for audio",
}


@pytest.fixture
def mock_gemini_client():
    return MagicMock()


@pytest.fixture
def mock_gemini_extractor(mock_gemini_client):
    return GeminiExtractor(
        mock_gemini_client,
        ExtractorConfig(
            name="mock",
            properties={
                "prompt_for_kind": PROMPTS_FOR_KIND,
                "model_name": "fake-model",
            },
        ),
    )


@pytest.fixture
def test_data_dir():
    """Return the path to the test data directory."""
    return Path(__file__).parent.parent.parent / "tests" / "data"


@pytest.mark.parametrize(
    "mime_type, kind",
    [
        # documents
        ("application/pdf", Kind.DOCUMENT),
        ("text/markdown", Kind.DOCUMENT),
        ("text/plain", Kind.DOCUMENT),
        ("text/html", Kind.DOCUMENT),
        ("text/css", Kind.DOCUMENT),
        ("text/csv", Kind.DOCUMENT),
        ("text/xml", Kind.DOCUMENT),
        ("text/rtf", Kind.DOCUMENT),
        # images
        ("image/png", Kind.IMAGE),
        ("image/jpeg", Kind.IMAGE),
        ("image/webp", Kind.IMAGE),
        ("image/heic", Kind.IMAGE),
        ("image/heif", Kind.IMAGE),
        # videos
        ("video/mp4", Kind.VIDEO),
        ("video/mpeg", Kind.VIDEO),
        ("video/mov", Kind.VIDEO),
        ("video/avi", Kind.VIDEO),
        ("video/x-flv", Kind.VIDEO),
        ("video/mpg", Kind.VIDEO),
        ("video/webm", Kind.VIDEO),
        ("video/wmv", Kind.VIDEO),
        ("video/3gpp", Kind.VIDEO),
        # audio
        ("audio/mpeg", Kind.AUDIO),
        ("audio/aiff", Kind.AUDIO),
        ("audio/aac", Kind.AUDIO),
        ("audio/ogg", Kind.AUDIO),
        ("audio/flac", Kind.AUDIO),
    ],
)
def test_get_kind_from_mime_type(mock_gemini_extractor, mime_type, kind):
    """Test that the kind is correctly inferred from the mime type."""
    assert mock_gemini_extractor._get_kind_from_mime_type(mime_type) == kind


def test_get_kind_from_mime_type_unsupported(mock_gemini_extractor):
    assert (
        mock_gemini_extractor._get_kind_from_mime_type("unsupported/mimetype") is None
    )


def test_extract_success(mock_gemini_extractor):
    with (
        patch(
            "mimetypes.guess_type",
            return_value=("application/pdf", None),
        ),
        patch(
            "pathlib.Path.read_bytes",
            return_value=b"test content",
        ),
    ):
        # mock the gemini client call
        mock_gemini_client = MagicMock()
        mock_gemini_client.models.generate_content.return_value = MagicMock(
            text="extracted content"
        )
        mock_gemini_extractor.gemini_client = mock_gemini_client

        # test the extract method
        assert mock_gemini_extractor.extract(
            FileInfoInternal(path="test.pdf", mime_type="application/pdf"),
        ) == ExtractionOutput(
            is_passthrough=False,
            content="extracted content",
            content_format=OutputFormat.MARKDOWN,
        )

        # check the gemini client was called with the correct arguments
        mock_gemini_client.models.generate_content.assert_called_once_with(
            model="fake-model",
            contents=[
                types.Part.from_bytes(
                    data=b"test content", mime_type="application/pdf"
                ),
                PROMPTS_FOR_KIND[Kind.DOCUMENT],
            ],
        )


def test_extract_failure_from_gemini(mock_gemini_extractor):
    with patch(
        "pathlib.Path.read_bytes",
        return_value=b"test content",
    ):
        # mock the gemini client call
        mock_models = MagicMock()
        mock_models.generate_content.side_effect = Exception("error from gemini")

        mock_gemini_client = MagicMock()
        mock_gemini_client.models = mock_models

        mock_gemini_extractor.gemini_client = mock_gemini_client

        file_info = FileInfoInternal(path="test.pdf", mime_type="application/pdf")

        with pytest.raises(Exception, match="error from gemini"):
            mock_gemini_extractor.extract(file_info)

        mock_models.generate_content.assert_called_once_with(
            model="fake-model",
            contents=[
                types.Part.from_bytes(
                    data=b"test content", mime_type="application/pdf"
                ),
                PROMPTS_FOR_KIND[Kind.DOCUMENT],
            ],
        )


def test_extract_failure_from_bytes_read(mock_gemini_extractor):
    with (
        patch(
            "mimetypes.guess_type",
            return_value=("application/pdf", None),
        ),
        patch(
            "pathlib.Path.read_bytes",
            side_effect=Exception("error from read_bytes"),
        ),
    ):
        # mock the gemini client call
        mock_gemini_client = MagicMock()
        mock_gemini_client.models.generate_content.return_value = MagicMock(
            text="extracted content"
        )
        mock_gemini_extractor.gemini_client = mock_gemini_client

        # test the extract method
        with pytest.raises(ValueError, match="error from read_bytes"):
            mock_gemini_extractor.extract(
                FileInfoInternal(path="test.pdf", mime_type="application/pdf"),
            )

        mock_gemini_client.models.generate_content.assert_not_called()


def test_extract_failure_unsupported_mime_type(mock_gemini_extractor):
    # spy on the get mime type
    with patch(
        "mimetypes.guess_type",
        return_value=(None, None),
    ):
        with pytest.raises(ValueError, match="Unable to guess file mime type"):
            mock_gemini_extractor.extract(
                FileInfoInternal(
                    path="test.unsupported", mime_type="unsupported/mimetype"
                ),
            )


SUPPORTED_MODELS = ["gemini-2.0-flash"]


def paid_gemini_extractor(model_name: str):
    return GeminiExtractor(
        extractor_config=ExtractorConfig(
            name="paid-gemini",
            properties={
                "model_name": model_name,
                "prompt_for_kind": {
                    "document": "Return a short paragraph summarizing the document. Start your answer with the word 'Document summary:'.",
                    "image": "Return a short paragraph summarizing the image. Start your answer with the word 'Image summary:'.",
                    "video": "Return a short paragraph summarizing the video. Start your answer with the word 'Video summary:'.",
                    "audio": "Return a short paragraph summarizing the audio. Start your answer with the word 'Audio summary:'.",
                },
            },
            passthrough_mimetypes=[
                OutputFormat.TEXT,
                OutputFormat.MARKDOWN,
            ],
        ),
        gemini_client=genai.Client(
            api_key=Config.shared().gemini_api_key,
        ),
    )


@pytest.mark.paid
@pytest.mark.parametrize("model_name", SUPPORTED_MODELS)
def test_extract_document(model_name, test_data_dir):
    extractor = paid_gemini_extractor(model_name=model_name)
    output = extractor.extract(
        file_info=FileInfo(path=str(test_data_dir / "1706.03762v7.pdf")),
    )
    assert not output.is_passthrough
    assert output.content_format == OutputFormat.MARKDOWN
    assert "Document summary:" in output.content


@pytest.mark.paid
@pytest.mark.parametrize("model_name", SUPPORTED_MODELS)
def test_extract_image(model_name, test_data_dir):
    extractor = paid_gemini_extractor(model_name=model_name)
    output = extractor.extract(
        file_info=FileInfo(path=str(test_data_dir / "kodim23.png")),
    )
    assert not output.is_passthrough
    assert output.content_format == OutputFormat.MARKDOWN
    assert "Image summary:" in output.content


@pytest.mark.paid
@pytest.mark.parametrize("model_name", SUPPORTED_MODELS)
def test_extract_video(model_name, test_data_dir):
    extractor = paid_gemini_extractor(model_name=model_name)
    output = extractor.extract(
        file_info=FileInfo(path=str(test_data_dir / "big_buck_bunny_sample.mp4")),
    )
    assert not output.is_passthrough
    assert output.content_format == OutputFormat.MARKDOWN
    assert "Video summary:" in output.content


@pytest.mark.paid
@pytest.mark.parametrize("model_name", SUPPORTED_MODELS)
def test_extract_audio(model_name, test_data_dir):
    extractor = paid_gemini_extractor(model_name=model_name)
    output = extractor.extract(
        file_info=FileInfo(path=str(test_data_dir / "poacher.ogg")),
    )
    assert not output.is_passthrough
    assert output.content_format == OutputFormat.MARKDOWN
    assert "Audio summary:" in output.content


@pytest.mark.paid
@pytest.mark.parametrize("model_name", SUPPORTED_MODELS)
def test_provider_bad_request(tmp_path, model_name):
    # write corrupted PDF file to temp files
    temp_file = tmp_path / "corrupted_file.pdf"
    temp_file.write_bytes(b"invalid file")

    extractor = paid_gemini_extractor(model_name=model_name)

    with pytest.raises(ValueError, match="Error extracting .*corrupted_file.pdf: "):
        extractor.extract(
            file_info=FileInfo(path=temp_file.as_posix()),
        )
