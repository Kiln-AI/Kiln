from unittest.mock import AsyncMock, patch

import pytest
from google import genai
from google.genai import types

from conftest import MockFileFactoryMimeType
from kiln_ai.adapters.extractors.base_extractor import ExtractionOutput, OutputFormat
from kiln_ai.adapters.extractors.gemini_extractor import (
    ExtractorConfig,
    GeminiExtractor,
    Kind,
)
from kiln_ai.datamodel.extraction import ExtractorType
from kiln_ai.utils.config import Config

PROMPTS_FOR_KIND: dict[str, str] = {
    "document": "prompt for documents",
    "image": "prompt for images",
    "video": "prompt for videos",
    "audio": "prompt for audio",
}


@pytest.fixture
def mock_gemini_client():
    return AsyncMock()


@pytest.fixture
def mock_gemini_extractor(mock_gemini_client):
    return GeminiExtractor(
        mock_gemini_client,
        ExtractorConfig(
            name="mock",
            extractor_type=ExtractorType.GEMINI,
            properties={
                "prompt_document": PROMPTS_FOR_KIND["document"],
                "prompt_image": PROMPTS_FOR_KIND["image"],
                "prompt_video": PROMPTS_FOR_KIND["video"],
                "prompt_audio": PROMPTS_FOR_KIND["audio"],
                "model_name": "gemini-2.0-flash",
            },
        ),
    )


@pytest.mark.parametrize(
    "mime_type, kind",
    [
        # documents
        ("application/pdf", Kind.DOCUMENT),
        ("text/markdown", Kind.DOCUMENT),
        ("text/plain", Kind.DOCUMENT),
        ("text/html", Kind.DOCUMENT),
        ("text/css", Kind.DOCUMENT),
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


async def test_extract_success(mock_gemini_extractor):
    with (
        patch(
            "pathlib.Path.read_bytes",
            return_value=b"test content",
        ),
    ):
        # mock the gemini client call
        mock_gemini_client = AsyncMock()
        mock_gemini_client.aio.models.generate_content.return_value = AsyncMock(
            text="extracted content"
        )
        mock_gemini_extractor.gemini_client = mock_gemini_client

        # test the extract method
        assert await mock_gemini_extractor.extract(
            path="test.pdf",
            mime_type="application/pdf",
        ) == ExtractionOutput(
            is_passthrough=False,
            content="extracted content",
            content_format=OutputFormat.MARKDOWN,
        )

        # check the gemini client was called with the correct arguments
        mock_gemini_client.aio.models.generate_content.assert_called_once_with(
            model="gemini-2.0-flash",
            contents=[
                types.Part.from_bytes(
                    data=b"test content", mime_type="application/pdf"
                ),
                PROMPTS_FOR_KIND[Kind.DOCUMENT],
            ],
        )


async def test_extract_failure_from_gemini(mock_gemini_extractor):
    with patch(
        "pathlib.Path.read_bytes",
        return_value=b"test content",
    ):
        mock_gemini_client = AsyncMock()
        mock_gemini_client.aio.models.generate_content.side_effect = Exception(
            "error from gemini"
        )
        mock_gemini_extractor.gemini_client = mock_gemini_client

        with pytest.raises(Exception, match="error from gemini"):
            await mock_gemini_extractor.extract(
                path="test.pdf",
                mime_type="application/pdf",
            )

        mock_gemini_client.aio.models.generate_content.assert_called_once_with(
            model="gemini-2.0-flash",
            contents=[
                types.Part.from_bytes(
                    data=b"test content", mime_type="application/pdf"
                ),
                PROMPTS_FOR_KIND[Kind.DOCUMENT],
            ],
        )


async def test_extract_failure_from_bytes_read(mock_gemini_extractor):
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
        mock_gemini_client = AsyncMock()
        mock_gemini_client.aio.models.generate_content.return_value = AsyncMock(
            text="extracted content"
        )
        mock_gemini_extractor.gemini_client = mock_gemini_client

        # test the extract method
        with pytest.raises(ValueError, match="error from read_bytes"):
            await mock_gemini_extractor.extract(
                path="test.pdf",
                mime_type="application/pdf",
            )

        mock_gemini_client.aio.models.generate_content.assert_not_called()


async def test_extract_failure_unsupported_mime_type(mock_gemini_extractor):
    # spy on the get mime type
    with patch(
        "mimetypes.guess_type",
        return_value=(None, None),
    ):
        with pytest.raises(ValueError, match="Unsupported MIME type"):
            await mock_gemini_extractor.extract(
                path="test.unsupported",
                mime_type="unsupported/mimetype",
            )


SUPPORTED_MODELS = [
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
]


def paid_gemini_extractor(model_name: str):
    return GeminiExtractor(
        extractor_config=ExtractorConfig(
            name="paid-gemini",
            extractor_type=ExtractorType.GEMINI,
            properties={
                "model_name": model_name,
                "prompt_document": "Return a short paragraph summarizing the document. Start your answer with the word 'Document summary:'.",
                "prompt_image": "Return a short paragraph summarizing the image. Start your answer with the word 'Image summary:'.",
                "prompt_video": "Return a short paragraph summarizing the video. Start your answer with the word 'Video summary:'.",
                "prompt_audio": "Return a short paragraph summarizing the audio. Start your answer with the word 'Audio summary:'.",
            },
            passthrough_mimetypes=[
                # we want all mimetypes to go to Gemini to be sure we're testing the API call
            ],
        ),
        gemini_client=genai.Client(
            api_key=Config.shared().gemini_api_key,
        ),
    )


@pytest.mark.paid
@pytest.mark.parametrize("model_name", SUPPORTED_MODELS)
async def test_extract_document_pdf(model_name, mock_file_factory):
    test_pdf_file = mock_file_factory(MockFileFactoryMimeType.PDF)
    extractor = paid_gemini_extractor(model_name=model_name)
    output = await extractor.extract(
        path=str(test_pdf_file),
        mime_type="application/pdf",
    )
    assert not output.is_passthrough
    assert output.content_format == OutputFormat.MARKDOWN
    assert "Document summary:" in output.content


@pytest.mark.paid
@pytest.mark.parametrize("model_name", SUPPORTED_MODELS)
async def test_extract_html(model_name, mock_file_factory):
    test_html_file = mock_file_factory(MockFileFactoryMimeType.HTML)
    extractor = paid_gemini_extractor(model_name=model_name)
    output = await extractor.extract(
        path=str(test_html_file),
        mime_type="text/html",
    )
    assert not output.is_passthrough
    assert output.content_format == OutputFormat.MARKDOWN
    assert "Document summary:" in output.content


@pytest.mark.paid
@pytest.mark.parametrize("model_name", SUPPORTED_MODELS)
async def test_extract_md(model_name, mock_file_factory):
    test_md_file = mock_file_factory(MockFileFactoryMimeType.MD)
    extractor = paid_gemini_extractor(model_name=model_name)
    output = await extractor.extract(
        path=str(test_md_file),
        mime_type="text/markdown",
    )
    assert not output.is_passthrough
    assert output.content_format == OutputFormat.MARKDOWN
    assert "Document summary:" in output.content


@pytest.mark.paid
@pytest.mark.parametrize("model_name", SUPPORTED_MODELS)
async def test_extract_txt(model_name, mock_file_factory):
    test_txt_file = mock_file_factory(MockFileFactoryMimeType.TXT)
    extractor = paid_gemini_extractor(model_name=model_name)
    output = await extractor.extract(
        path=str(test_txt_file),
        mime_type="text/plain",
    )
    assert not output.is_passthrough
    assert output.content_format == OutputFormat.MARKDOWN
    assert "Document summary:" in output.content


@pytest.mark.paid
@pytest.mark.parametrize("model_name", SUPPORTED_MODELS)
async def test_extract_image_png(model_name, mock_file_factory):
    test_image_file = mock_file_factory(MockFileFactoryMimeType.PNG)
    extractor = paid_gemini_extractor(model_name=model_name)
    output = await extractor.extract(
        path=str(test_image_file),
        mime_type="image/png",
    )
    assert not output.is_passthrough
    assert output.content_format == OutputFormat.MARKDOWN
    assert "Image summary:" in output.content


@pytest.mark.paid
@pytest.mark.parametrize("model_name", SUPPORTED_MODELS)
async def test_extract_image_jpeg(model_name, mock_file_factory):
    test_image_file = mock_file_factory(MockFileFactoryMimeType.JPEG)
    extractor = paid_gemini_extractor(model_name=model_name)
    output = await extractor.extract(
        path=str(test_image_file),
        mime_type="image/jpeg",
    )
    assert not output.is_passthrough
    assert output.content_format == OutputFormat.MARKDOWN
    assert "Image summary:" in output.content


@pytest.mark.paid
@pytest.mark.parametrize("model_name", SUPPORTED_MODELS)
async def test_extract_video_mp4(model_name, mock_file_factory):
    test_video_file = mock_file_factory(MockFileFactoryMimeType.MP4)
    extractor = paid_gemini_extractor(model_name=model_name)
    output = await extractor.extract(
        path=str(test_video_file),
        mime_type="video/mp4",
    )
    assert not output.is_passthrough
    assert output.content_format == OutputFormat.MARKDOWN
    assert "Video summary:" in output.content


@pytest.mark.paid
@pytest.mark.parametrize("model_name", SUPPORTED_MODELS)
async def test_extract_video_mov(model_name, mock_file_factory):
    test_video_file = mock_file_factory(MockFileFactoryMimeType.MOV)
    extractor = paid_gemini_extractor(model_name=model_name)
    output = await extractor.extract(
        path=str(test_video_file),
        mime_type="video/quicktime",
    )
    assert not output.is_passthrough
    assert output.content_format == OutputFormat.MARKDOWN
    assert "Video summary:" in output.content


@pytest.mark.paid
@pytest.mark.parametrize("model_name", SUPPORTED_MODELS)
async def test_extract_audio_ogg(model_name, mock_file_factory):
    test_audio_file = mock_file_factory(MockFileFactoryMimeType.OGG)
    extractor = paid_gemini_extractor(model_name=model_name)
    output = await extractor.extract(
        path=str(test_audio_file),
        mime_type="audio/ogg",
    )
    assert not output.is_passthrough
    assert output.content_format == OutputFormat.MARKDOWN
    assert "Audio summary:" in output.content


@pytest.mark.paid
@pytest.mark.parametrize("model_name", SUPPORTED_MODELS)
async def test_extract_audio_mp3(model_name, mock_file_factory):
    test_audio_file = mock_file_factory(MockFileFactoryMimeType.MP3)
    extractor = paid_gemini_extractor(model_name=model_name)
    output = await extractor.extract(
        path=str(test_audio_file),
        mime_type="audio/mpeg",
    )
    assert not output.is_passthrough
    assert output.content_format == OutputFormat.MARKDOWN
    assert "Audio summary:" in output.content


@pytest.mark.paid
@pytest.mark.parametrize("model_name", SUPPORTED_MODELS)
async def test_extract_audio_wav(model_name, mock_file_factory):
    test_audio_file = mock_file_factory(MockFileFactoryMimeType.WAV)
    extractor = paid_gemini_extractor(model_name=model_name)
    output = await extractor.extract(
        path=str(test_audio_file),
        mime_type="audio/wav",
    )
    assert not output.is_passthrough
    assert output.content_format == OutputFormat.MARKDOWN
    assert "Audio summary:" in output.content


@pytest.mark.paid
@pytest.mark.parametrize("model_name", SUPPORTED_MODELS)
async def test_provider_bad_request(tmp_path, model_name):
    # write corrupted PDF file to temp files
    temp_file = tmp_path / "corrupted_file.pdf"
    temp_file.write_bytes(b"invalid file")

    extractor = paid_gemini_extractor(model_name=model_name)

    with pytest.raises(ValueError, match="Error extracting .*corrupted_file.pdf: "):
        await extractor.extract(
            path=temp_file.as_posix(),
            mime_type="application/pdf",
        )
