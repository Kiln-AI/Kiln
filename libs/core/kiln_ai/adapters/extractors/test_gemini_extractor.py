from pathlib import Path
from unittest.mock import MagicMock

import pytest
from google import genai
from google.genai import types

from kiln_ai.adapters.extractors.base_extractor import (
    ExtractionFormat,
    ExtractionOutput,
    FileInfo,
    FileInfoInternal,
)
from kiln_ai.adapters.extractors.gemini_extractor import (
    GeminiExtractor,
    GeminiExtractorConfig,
    Kind,
)
from kiln_ai.utils.config import Config

PROMPTS_FOR_KIND = {
    Kind.DOCUMENT: "prompt for documents",
    Kind.IMAGE: "prompt for images",
    Kind.VIDEO: "prompt for videos",
    Kind.AUDIO: "prompt for audio",
}


@pytest.fixture
def mock_gemini_client():
    return MagicMock()


@pytest.fixture
def mock_gemini_extractor_config_with_kind_prompts():
    return GeminiExtractorConfig(
        default_prompt="default prompt",
        prompt_for_kind=PROMPTS_FOR_KIND,
        model="fake-model",
    )


@pytest.fixture
def mock_gemini_extractor_config_no_kind_prompts():
    return GeminiExtractorConfig(
        default_prompt="default prompt",
        model="fake-model",
    )


@pytest.fixture
def mock_gemini_extractor_with_kind_prompts(
    mock_gemini_client, mock_gemini_extractor_config_with_kind_prompts
):
    return GeminiExtractor(
        mock_gemini_client, mock_gemini_extractor_config_with_kind_prompts
    )


@pytest.fixture
def mock_gemini_extractor_no_kind_prompts(
    mock_gemini_client, mock_gemini_extractor_config_no_kind_prompts
):
    return GeminiExtractor(
        mock_gemini_client, mock_gemini_extractor_config_no_kind_prompts
    )


@pytest.fixture
def mock_gemini_extractor_with_kind_prompts_default_and_custom_prompt(
    mock_gemini_client, mock_gemini_extractor_config_with_kind_prompts
):
    config = mock_gemini_extractor_config_with_kind_prompts
    config.default_prompt = "default prompt"
    config.custom_prompt = "custom prompt"
    return GeminiExtractor(
        mock_gemini_client,
        config,
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
def test_get_kind_from_mime_type(
    mock_gemini_extractor_with_kind_prompts, mime_type, kind
):
    """Test that the kind is correctly inferred from the mime type."""
    assert (
        mock_gemini_extractor_with_kind_prompts._get_kind_from_mime_type(mime_type)
        == kind
    )


def test_get_kind_from_mime_type_unsupported(mock_gemini_extractor_with_kind_prompts):
    """Test that an error is raised for unsupported mime types."""
    with pytest.raises(ValueError):
        mock_gemini_extractor_with_kind_prompts._get_kind_from_mime_type(
            "unsupported/mimetype"
        )


@pytest.mark.parametrize(
    "kind",
    [
        Kind.DOCUMENT,
        Kind.IMAGE,
        Kind.VIDEO,
        Kind.AUDIO,
    ],
)
def test_get_prompt_for_kind(mock_gemini_extractor_with_kind_prompts, kind: Kind):
    """Test that the prompt is correctly inferred from the kind."""
    assert (
        mock_gemini_extractor_with_kind_prompts._get_prompt_for_kind(kind)
        == PROMPTS_FOR_KIND[kind]
    )


@pytest.mark.parametrize(
    "kind",
    [
        Kind.DOCUMENT,
        Kind.IMAGE,
        Kind.VIDEO,
        Kind.AUDIO,
    ],
)
def test_get_prompt_for_kind_no_kind_prompts(
    mock_gemini_extractor_no_kind_prompts, kind: Kind
):
    assert (
        mock_gemini_extractor_no_kind_prompts._get_prompt_for_kind(kind)
        == "default prompt"
    )


def test_extract_success_no_custom_prompt(mock_gemini_extractor_with_kind_prompts):
    # mock the gemini client call
    mock_gemini_client = MagicMock()
    mock_gemini_client.models.generate_content.return_value = MagicMock(
        text="extracted content"
    )
    mock_gemini_extractor_with_kind_prompts.gemini_client = mock_gemini_client

    # mock the bytes loading
    mock_load_file_bytes = MagicMock()
    mock_load_file_bytes.return_value = b"test content"
    mock_gemini_extractor_with_kind_prompts._load_file_bytes = mock_load_file_bytes

    # test the extract method
    assert mock_gemini_extractor_with_kind_prompts.extract(
        FileInfoInternal(path="test.pdf", mime_type="application/pdf"),
    ) == ExtractionOutput(
        is_passthrough=False,
        content="extracted content",
        content_format=ExtractionFormat.MARKDOWN,
    )

    # check the gemini client was called with the correct arguments
    mock_gemini_client.models.generate_content.assert_called_once_with(
        model="fake-model",
        contents=[
            types.Part.from_bytes(data=b"test content", mime_type="application/pdf"),
            PROMPTS_FOR_KIND[Kind.DOCUMENT],
        ],
    )


def test_extract_success_with_custom_prompt(
    mock_gemini_extractor_with_kind_prompts_default_and_custom_prompt,
):
    extractor = mock_gemini_extractor_with_kind_prompts_default_and_custom_prompt
    # mock the gemini client call
    mock_gemini_client = MagicMock()
    mock_gemini_client.models.generate_content.return_value = MagicMock(
        text="extracted content"
    )
    extractor.gemini_client = mock_gemini_client

    # mock the bytes loading
    mock_load_file_bytes = MagicMock()
    mock_load_file_bytes.return_value = b"test content"
    extractor._load_file_bytes = mock_load_file_bytes

    # test the extract method
    assert extractor.extract(
        FileInfoInternal(path="test.pdf", mime_type="application/pdf"),
    ) == ExtractionOutput(
        is_passthrough=False,
        content="extracted content",
        content_format=ExtractionFormat.MARKDOWN,
    )

    # check the gemini client was called with the correct arguments
    mock_gemini_client.models.generate_content.assert_called_once_with(
        model="fake-model",
        contents=[
            types.Part.from_bytes(data=b"test content", mime_type="application/pdf"),
            "custom prompt",
        ],
    )


def test_extract_failure_from_gemini(mock_gemini_extractor_with_kind_prompts):
    # mock the gemini client call
    mock_gemini_client = MagicMock()
    mock_gemini_client.models.generate_content.side_effect = Exception(
        "error from gemini"
    )
    mock_gemini_extractor_with_kind_prompts.gemini_client = mock_gemini_client

    # mock the bytes loading
    mock_load_file_bytes = MagicMock()
    mock_load_file_bytes.return_value = b"test content"
    mock_gemini_extractor_with_kind_prompts._load_file_bytes = mock_load_file_bytes

    # test the extract method
    with pytest.raises(Exception):
        mock_gemini_extractor_with_kind_prompts.extract(
            FileInfoInternal(path="test.pdf", mime_type="application/pdf"),
        )


def test_extract_failure_from_file_utils(mock_gemini_extractor_with_kind_prompts):
    """Test that the extract method works."""

    # mock the gemini client call
    mock_gemini_client = MagicMock()
    mock_gemini_client.models.generate_content.return_value = MagicMock(
        text="extracted content"
    )
    mock_gemini_extractor_with_kind_prompts.gemini_client = mock_gemini_client

    # mock the bytes loading
    mock_load_file_bytes = MagicMock()
    mock_load_file_bytes.side_effect = Exception("error from file_utils")
    mock_gemini_extractor_with_kind_prompts._load_file_bytes = mock_load_file_bytes

    # test the extract method
    with pytest.raises(Exception):
        mock_gemini_extractor_with_kind_prompts.extract(
            FileInfoInternal(path="test.pdf", mime_type="application/pdf"),
        )


SUPPORTED_MODELS = ["gemini-2.0-flash"]


def paid_gemini_extractor(model_name: str):
    return GeminiExtractor(
        config=GeminiExtractorConfig(
            model=model_name,
            output_format=ExtractionFormat.MARKDOWN,
            prompt_for_kind={
                Kind.DOCUMENT: "Return a short paragraph summarizing the document. Start your answer with the word 'Document summary:'.",
                Kind.IMAGE: "Return a short paragraph summarizing the image. Start your answer with the word 'Image summary:'.",
                Kind.VIDEO: "Return a short paragraph summarizing the video. Start your answer with the word 'Video summary:'.",
                Kind.AUDIO: "Return a short paragraph summarizing the audio. Start your answer with the word 'Audio summary:'.",
            },
            default_prompt="Return a short paragraph summarizing the document. Start your answer with the word 'Default summary:'.",
            passthrough_mimetypes=[
                "text/plain",
                "text/markdown",
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
    assert output.is_passthrough == False
    assert output.content_format == ExtractionFormat.MARKDOWN
    assert "Document summary:" in output.content


@pytest.mark.paid
@pytest.mark.parametrize("model_name", SUPPORTED_MODELS)
def test_extract_image(model_name, test_data_dir):
    extractor = paid_gemini_extractor(model_name=model_name)
    output = extractor.extract(
        file_info=FileInfo(path=str(test_data_dir / "kodim23.png")),
    )
    assert output.is_passthrough == False
    assert output.content_format == ExtractionFormat.MARKDOWN
    assert "Image summary:" in output.content


@pytest.mark.paid
@pytest.mark.parametrize("model_name", SUPPORTED_MODELS)
def test_extract_video(model_name, test_data_dir):
    extractor = paid_gemini_extractor(model_name=model_name)
    output = extractor.extract(
        file_info=FileInfo(path=str(test_data_dir / "big_buck_bunny_sample.mp4")),
    )
    assert output.is_passthrough == False
    assert output.content_format == ExtractionFormat.MARKDOWN
    assert "Video summary:" in output.content


@pytest.mark.paid
@pytest.mark.parametrize("model_name", SUPPORTED_MODELS)
def test_extract_audio(model_name, test_data_dir):
    extractor = paid_gemini_extractor(model_name=model_name)
    output = extractor.extract(
        file_info=FileInfo(path=str(test_data_dir / "poacher.ogg")),
    )
    assert output.is_passthrough == False
    assert output.content_format == ExtractionFormat.MARKDOWN
    assert "Audio summary:" in output.content


@pytest.mark.paid
@pytest.mark.parametrize("model_name", SUPPORTED_MODELS)
def test_provider_bad_request(tmp_path, model_name):
    # write corrupted PDF file to temp files
    temp_file = tmp_path / "corrupted_file.pdf"
    temp_file.write_bytes(b"invalid file")

    extractor = paid_gemini_extractor(model_name=model_name)

    with pytest.raises(ValueError):
        extractor.extract(
            file_info=FileInfo(path=temp_file.as_posix()),
        )
