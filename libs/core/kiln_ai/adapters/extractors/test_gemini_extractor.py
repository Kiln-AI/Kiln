import tempfile
from unittest.mock import MagicMock

import pytest
from google.genai import types

from kiln_ai.adapters.extractors.base_extractor import (
    ExtractionFormat,
    ExtractionOutput,
    FileInfoInternal,
)
from kiln_ai.adapters.extractors.gemini_extractor import (
    GeminiExtractor,
    GeminiExtractorConfig,
    Kind,
)

PROMPTS_FOR_KIND = {
    Kind.DOCUMENT: "prompt for documents",
    Kind.IMAGE: "prompt for images",
    Kind.VIDEO: "prompt for videos",
    Kind.AUDIO: "prompt for audio",
}


@pytest.fixture
def mock_gemini_client():
    """
    Provides a MagicMock instance simulating a Gemini client for testing purposes.
    """
    return MagicMock()


@pytest.fixture
def mock_gemini_extractor_config_with_kind_prompts():
    """
    Creates a GeminiExtractorConfig with a default prompt, kind-specific prompts, and a fake model name.

    Returns:
        GeminiExtractorConfig: Configuration containing a default prompt, a dictionary of prompts for each Kind, and a model identifier.
    """
    return GeminiExtractorConfig(
        default_prompt="default prompt",
        prompt_for_kind=PROMPTS_FOR_KIND,
        model="fake-model",
    )


@pytest.fixture
def mock_gemini_extractor_config_no_kind_prompts():
    """
    Provides a GeminiExtractorConfig with only a default prompt and model, without kind-specific prompts.

    Returns:
        GeminiExtractorConfig: Configuration containing a default prompt and model name.
    """
    return GeminiExtractorConfig(
        default_prompt="default prompt",
        model="fake-model",
    )


@pytest.fixture
def mock_gemini_extractor_with_kind_prompts(
    mock_gemini_client, mock_gemini_extractor_config_with_kind_prompts
):
    """
    Pytest fixture that provides a GeminiExtractor instance configured with kind-specific prompts.
    """
    return GeminiExtractor(
        mock_gemini_client, mock_gemini_extractor_config_with_kind_prompts
    )


@pytest.fixture
def mock_gemini_extractor_no_kind_prompts(
    mock_gemini_client, mock_gemini_extractor_config_no_kind_prompts
):
    """
    Pytest fixture that provides a GeminiExtractor instance configured without kind-specific prompts.
    """
    return GeminiExtractor(
        mock_gemini_client, mock_gemini_extractor_config_no_kind_prompts
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
    """
    Tests that the default prompt is used when no kind-specific prompts are configured.
    """
    assert (
        mock_gemini_extractor_no_kind_prompts._get_prompt_for_kind(kind)
        == "default prompt"
    )


def test_extract_success(mock_gemini_extractor_with_kind_prompts):
    """
    Tests that the extract method returns the expected ExtractionOutput and calls the Gemini client with the correct arguments when extraction succeeds.
    """

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
        "custom prompt",
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
    """
    Tests that the extract method raises an exception when the Gemini client fails during content generation.
    """

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
            "custom prompt",
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
            "custom prompt",
        )
