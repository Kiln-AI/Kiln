from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from litellm.types.utils import Choices, ModelResponse

from conftest import MockFileFactoryMimeType
from kiln_ai.adapters.extractors.base_extractor import ExtractionInput, OutputFormat
from kiln_ai.adapters.extractors.encoding import to_base64_url
from kiln_ai.adapters.extractors.litellm_extractor import (
    ExtractorConfig,
    Kind,
    LitellmExtractor,
    encode_file_litellm_format,
)
from kiln_ai.adapters.ml_model_list import built_in_models
from kiln_ai.adapters.provider_tools import LiteLlmCoreConfig
from kiln_ai.datamodel.extraction import ExtractorType

PROMPTS_FOR_KIND: dict[str, str] = {
    "document": "prompt for documents",
    "image": "prompt for images",
    "video": "prompt for videos",
    "audio": "prompt for audio",
}


@pytest.fixture
def mock_litellm_extractor():
    return LitellmExtractor(
        ExtractorConfig(
            name="mock",
            extractor_type=ExtractorType.LITELLM,
            model_name="gpt_4o",
            model_provider_name="openai",
            properties={
                "prompt_document": PROMPTS_FOR_KIND["document"],
                "prompt_image": PROMPTS_FOR_KIND["image"],
                "prompt_video": PROMPTS_FOR_KIND["video"],
                "prompt_audio": PROMPTS_FOR_KIND["audio"],
            },
        ),
        litellm_core_config=LiteLlmCoreConfig(
            base_url="https://test.com",
            additional_body_options={"api_key": "test-key"},
            default_headers={},
        ),
    )


@pytest.fixture
def mock_litellm_core_config():
    return LiteLlmCoreConfig(
        base_url="https://test.com",
        additional_body_options={"api_key": "test-key"},
        default_headers={},
    )


@pytest.mark.parametrize(
    "mime_type, kind",
    [
        # documents
        ("application/pdf", Kind.DOCUMENT),
        ("text/markdown", Kind.DOCUMENT),
        ("text/md", Kind.DOCUMENT),
        ("text/plain", Kind.DOCUMENT),
        ("text/html", Kind.DOCUMENT),
        ("text/csv", Kind.DOCUMENT),
        # images
        ("image/png", Kind.IMAGE),
        ("image/jpeg", Kind.IMAGE),
        ("image/jpg", Kind.IMAGE),
        # videos
        ("video/mp4", Kind.VIDEO),
        ("video/mov", Kind.VIDEO),
        ("video/quicktime", Kind.VIDEO),
        # audio
        ("audio/mpeg", Kind.AUDIO),
        ("audio/ogg", Kind.AUDIO),
        ("audio/wav", Kind.AUDIO),
    ],
)
def test_get_kind_from_mime_type(mock_litellm_extractor, mime_type, kind):
    """Test that the kind is correctly inferred from the mime type."""
    assert mock_litellm_extractor._get_kind_from_mime_type(mime_type) == kind


def test_get_kind_from_mime_type_unsupported(mock_litellm_extractor):
    assert (
        mock_litellm_extractor._get_kind_from_mime_type("unsupported/mimetype") is None
    )


@pytest.mark.parametrize(
    "mime_type, expected_content",
    [
        (MockFileFactoryMimeType.TXT, "Content from text file"),
        (MockFileFactoryMimeType.MD, "Content from markdown file"),
        (MockFileFactoryMimeType.HTML, "Content from html file"),
        (MockFileFactoryMimeType.CSV, "Content from csv file"),
        (MockFileFactoryMimeType.PNG, "Content from image file"),
        (MockFileFactoryMimeType.JPG, "Content from image file"),
        (MockFileFactoryMimeType.MP4, "Content from video file"),
        (MockFileFactoryMimeType.MP3, "Content from audio file"),
    ],
)
async def test_extract_success(
    mock_file_factory, mock_litellm_extractor, mime_type, expected_content
):
    """Test successful extraction for non-PDF file types."""
    # Create a mock file of the specified type
    test_file = mock_file_factory(mime_type)

    # Mock response for single file extraction
    mock_response = AsyncMock(spec=ModelResponse)
    mock_choice = AsyncMock(spec=Choices)
    mock_message = AsyncMock()
    mock_message.content = expected_content
    mock_choice.message = mock_message
    mock_response.choices = [mock_choice]

    with patch("litellm.acompletion", return_value=mock_response) as mock_acompletion:
        result = await mock_litellm_extractor.extract(
            ExtractionInput(
                path=str(test_file),
                mime_type=mime_type.value,
            )
        )

    # Verify that the completion was called once (single file)
    assert mock_acompletion.call_count == 1

    # Verify the output contains the expected content
    assert expected_content in result.content

    assert not result.is_passthrough
    assert result.content_format == OutputFormat.MARKDOWN


def test_build_completion_kwargs_with_all_options(mock_file_factory):
    """Test that _build_completion_kwargs properly includes all litellm_core_config options."""
    litellm_core_config = LiteLlmCoreConfig(
        base_url="https://custom-api.example.com",
        additional_body_options={"custom_param": "value", "timeout": "30"},
        default_headers={"Authorization": "Bearer custom-token"},
    )

    extractor = LitellmExtractor(
        ExtractorConfig(
            name="test",
            extractor_type=ExtractorType.LITELLM,
            model_name="gpt_4o",
            model_provider_name="openai",
            properties={
                "prompt_document": "prompt for documents",
                "prompt_image": "prompt for images",
                "prompt_video": "prompt for videos",
                "prompt_audio": "prompt for audio",
            },
        ),
        litellm_core_config=litellm_core_config,
    )

    extraction_input = ExtractionInput(
        path=str(mock_file_factory(MockFileFactoryMimeType.PDF)),
        mime_type="application/pdf",
    )

    completion_kwargs = extractor._build_completion_kwargs(
        "test prompt", extraction_input
    )

    # Verify all completion kwargs are included
    assert completion_kwargs["base_url"] == "https://custom-api.example.com"
    assert completion_kwargs["custom_param"] == "value"
    assert completion_kwargs["timeout"] == "30"
    assert completion_kwargs["default_headers"] == {
        "Authorization": "Bearer custom-token"
    }

    # Verify basic structure is maintained
    assert "model" in completion_kwargs
    assert "messages" in completion_kwargs


def test_build_completion_kwargs_with_partial_options(mock_file_factory):
    """Test that _build_completion_kwargs works when only some options are set."""
    litellm_core_config = LiteLlmCoreConfig(
        base_url=None,
        additional_body_options={"timeout": "30"},
        default_headers=None,
    )

    extractor = LitellmExtractor(
        ExtractorConfig(
            name="test",
            extractor_type=ExtractorType.LITELLM,
            model_name="gpt_4o",
            model_provider_name="openai",
            properties={
                "prompt_document": "prompt for documents",
                "prompt_image": "prompt for images",
                "prompt_video": "prompt for videos",
                "prompt_audio": "prompt for audio",
            },
        ),
        litellm_core_config=litellm_core_config,
    )

    extraction_input = ExtractionInput(
        path=str(mock_file_factory(MockFileFactoryMimeType.PDF)),
        mime_type="application/pdf",
    )

    completion_kwargs = extractor._build_completion_kwargs(
        "test prompt", extraction_input
    )

    # Verify only the set options are included
    assert completion_kwargs["timeout"] == "30"
    assert "base_url" not in completion_kwargs
    assert "default_headers" not in completion_kwargs

    # Verify basic structure is maintained
    assert "model" in completion_kwargs
    assert "messages" in completion_kwargs


def test_build_completion_kwargs_with_empty_options(mock_file_factory):
    """Test that _build_completion_kwargs works when all options are None/empty."""
    litellm_core_config = LiteLlmCoreConfig(
        base_url=None,
        additional_body_options=None,
        default_headers=None,
    )

    extractor = LitellmExtractor(
        ExtractorConfig(
            name="test",
            extractor_type=ExtractorType.LITELLM,
            model_name="gpt_4o",
            model_provider_name="openai",
            properties={
                "prompt_document": "prompt for documents",
                "prompt_image": "prompt for images",
                "prompt_video": "prompt for videos",
                "prompt_audio": "prompt for audio",
            },
        ),
        litellm_core_config=litellm_core_config,
    )

    extraction_input = ExtractionInput(
        path=str(mock_file_factory(MockFileFactoryMimeType.PDF)),
        mime_type="application/pdf",
    )

    completion_kwargs = extractor._build_completion_kwargs(
        "test prompt", extraction_input
    )

    # Verify no completion kwargs are included
    assert "base_url" not in completion_kwargs
    assert "default_headers" not in completion_kwargs

    # Verify basic structure is maintained
    assert "model" in completion_kwargs
    assert "messages" in completion_kwargs


def test_build_completion_kwargs_messages_structure(mock_file_factory):
    """Test that the messages structure in completion_kwargs is correct."""
    litellm_core_config = LiteLlmCoreConfig()

    extractor = LitellmExtractor(
        ExtractorConfig(
            name="test",
            extractor_type=ExtractorType.LITELLM,
            model_name="gpt_4o",
            model_provider_name="openai",
            properties={
                "prompt_document": "prompt for documents",
                "prompt_image": "prompt for images",
                "prompt_video": "prompt for videos",
                "prompt_audio": "prompt for audio",
            },
        ),
        litellm_core_config=litellm_core_config,
    )

    extraction_input = ExtractionInput(
        path=str(mock_file_factory(MockFileFactoryMimeType.PDF)),
        mime_type="application/pdf",
    )

    completion_kwargs = extractor._build_completion_kwargs(
        "test prompt", extraction_input
    )

    # Verify messages structure
    messages = completion_kwargs["messages"]
    assert len(messages) == 1
    assert messages[0]["role"] == "user"

    content = messages[0]["content"]
    assert len(content) == 2

    # First content item should be text
    assert content[0]["type"] == "text"
    assert content[0]["text"] == "test prompt"

    # Second content item should be file
    assert content[1]["type"] == "file"
    assert "file" in content[1]
    assert "file_data" in content[1]["file"]


async def test_extract_failure_from_litellm(mock_file_factory, mock_litellm_extractor):
    test_pdf_file = mock_file_factory(MockFileFactoryMimeType.PDF)

    with (
        patch("pathlib.Path.read_bytes", return_value=b"test content"),
        patch("litellm.acompletion", side_effect=Exception("error from litellm")),
        patch(
            "kiln_ai.adapters.extractors.litellm_extractor.LitellmExtractor.litellm_model_slug",
            return_value="provider-name/model-name",
        ),
    ):
        # Mock litellm to raise an exception
        with pytest.raises(Exception, match="error from litellm"):
            await mock_litellm_extractor.extract(
                extraction_input=ExtractionInput(
                    path=str(test_pdf_file),
                    mime_type="application/pdf",
                )
            )


async def test_extract_failure_from_bytes_read(mock_litellm_extractor):
    with (
        patch(
            "mimetypes.guess_type",
            return_value=("application/pdf", None),
        ),
        patch(
            "pathlib.Path.read_bytes",
            side_effect=Exception("error from read_bytes"),
        ),
        patch(
            "kiln_ai.adapters.extractors.litellm_extractor.LitellmExtractor.litellm_model_slug",
            return_value="provider-name/model-name",
        ),
    ):
        # test the extract method
        with pytest.raises(
            ValueError, match="Error extracting test.pdf: Failed to split PDF test.pdf:"
        ):
            await mock_litellm_extractor.extract(
                extraction_input=ExtractionInput(
                    path="test.pdf",
                    mime_type="application/pdf",
                )
            )


async def test_extract_failure_unsupported_mime_type(mock_litellm_extractor):
    # spy on the get mime type
    with patch(
        "mimetypes.guess_type",
        return_value=(None, None),
    ):
        with pytest.raises(ValueError, match="Unsupported MIME type"):
            await mock_litellm_extractor.extract(
                extraction_input=ExtractionInput(
                    path="test.unsupported",
                    mime_type="unsupported/mimetype",
                )
            )


def test_litellm_model_slug_success(mock_litellm_extractor):
    """Test that litellm_model_slug returns the correct model slug."""
    # Mock the built_in_models_from_provider function to return a valid model provider
    mock_model_provider = AsyncMock()
    mock_model_provider.name = "test-provider"

    # Mock the get_litellm_provider_info function to return provider info with model ID
    mock_provider_info = AsyncMock()
    mock_provider_info.litellm_model_id = "test-provider/test-model"

    with (
        patch(
            "kiln_ai.adapters.extractors.litellm_extractor.built_in_models_from_provider",
            return_value=mock_model_provider,
        ) as mock_built_in_models,
        patch(
            "kiln_ai.adapters.extractors.litellm_extractor.get_litellm_provider_info",
            return_value=mock_provider_info,
        ) as mock_get_provider_info,
    ):
        result = mock_litellm_extractor.litellm_model_slug()

        assert result == "test-provider/test-model"

        # Verify the functions were called with correct arguments
        mock_built_in_models.assert_called_once()
        mock_get_provider_info.assert_called_once_with(mock_model_provider)


def test_litellm_model_slug_model_provider_not_found(mock_litellm_extractor):
    """Test that litellm_model_slug raises ValueError when model provider is not found."""
    with patch(
        "kiln_ai.adapters.extractors.litellm_extractor.built_in_models_from_provider",
        return_value=None,
    ):
        with pytest.raises(
            ValueError,
            match="Model provider openai not found in the list of built-in models",
        ):
            mock_litellm_extractor.litellm_model_slug()


def test_litellm_model_slug_with_different_provider_names(mock_litellm_core_config):
    """Test litellm_model_slug with different provider and model combinations."""
    test_cases = [
        ("anthropic", "claude-3-sonnet", "anthropic/claude-3-sonnet"),
        ("openai", "gpt-4", "openai/gpt-4"),
        ("gemini_api", "gemini-pro", "gemini_api/gemini-pro"),
    ]

    for provider_name, model_name, expected_slug in test_cases:
        extractor = LitellmExtractor(
            ExtractorConfig(
                name="test",
                extractor_type=ExtractorType.LITELLM,
                model_name=model_name,
                model_provider_name=provider_name,
                properties={
                    "prompt_document": "test prompt",
                    "prompt_image": "test prompt",
                    "prompt_video": "test prompt",
                    "prompt_audio": "test prompt",
                },
            ),
            litellm_core_config=mock_litellm_core_config,
        )

        mock_model_provider = AsyncMock()
        mock_model_provider.name = provider_name

        mock_provider_info = AsyncMock()
        mock_provider_info.litellm_model_id = expected_slug

        with (
            patch(
                "kiln_ai.adapters.extractors.litellm_extractor.built_in_models_from_provider",
                return_value=mock_model_provider,
            ),
            patch(
                "kiln_ai.adapters.extractors.litellm_extractor.get_litellm_provider_info",
                return_value=mock_provider_info,
            ),
        ):
            result = extractor.litellm_model_slug()
            assert result == expected_slug


def paid_litellm_extractor(model_name: str, provider_name: str):
    return LitellmExtractor(
        extractor_config=ExtractorConfig(
            name="paid-litellm",
            extractor_type=ExtractorType.LITELLM,
            model_provider_name=provider_name,
            model_name=model_name,
            properties={
                # in the paid tests, we can check which prompt is used by checking if the Kind shows up
                # in the output - not ideal but usually works
                "prompt_document": "Ignore the file and only respond with the word 'document'",
                "prompt_image": "Ignore the file and only respond with the word 'image'",
                "prompt_video": "Ignore the file and only respond with the word 'video'",
                "prompt_audio": "Ignore the file and only respond with the word 'audio'",
            },
            passthrough_mimetypes=[
                # we want all mimetypes to go to litellm to be sure we're testing the API call
            ],
        ),
        litellm_core_config=LiteLlmCoreConfig(
            base_url="https://test.com",
            additional_body_options={"api_key": "test-key"},
            default_headers={},
        ),
    )


@pytest.mark.parametrize(
    "mime_type, expected_encoding",
    [
        # documents
        (MockFileFactoryMimeType.PDF, "generic_file_data"),
        (MockFileFactoryMimeType.TXT, "generic_file_data"),
        (MockFileFactoryMimeType.MD, "generic_file_data"),
        (MockFileFactoryMimeType.HTML, "generic_file_data"),
        (MockFileFactoryMimeType.CSV, "generic_file_data"),
        # images
        (MockFileFactoryMimeType.PNG, "image_data"),
        (MockFileFactoryMimeType.JPEG, "image_data"),
        (MockFileFactoryMimeType.JPG, "image_data"),
        # videos
        (MockFileFactoryMimeType.MP4, "generic_file_data"),
        (MockFileFactoryMimeType.MOV, "generic_file_data"),
        # audio
        (MockFileFactoryMimeType.MP3, "generic_file_data"),
        (MockFileFactoryMimeType.OGG, "generic_file_data"),
        (MockFileFactoryMimeType.WAV, "generic_file_data"),
    ],
)
def test_encode_file_litellm_format(mock_file_factory, mime_type, expected_encoding):
    test_file = mock_file_factory(mime_type)
    encoded = encode_file_litellm_format(Path(test_file), mime_type)

    # there are two types of ways of including files, image_url is a special case
    # and it also works with the generic file_data encoding, but LiteLLM docs are
    # not clear on this, so best to go with the more specific image_url encoding
    if expected_encoding == "image_data":
        assert encoded == {
            "type": "image_url",
            "image_url": {
                "url": to_base64_url(mime_type, Path(test_file).read_bytes()),
            },
        }
    elif expected_encoding == "generic_file_data":
        assert encoded == {
            "type": "file",
            "file": {
                "file_data": to_base64_url(mime_type, Path(test_file).read_bytes()),
            },
        }
    else:
        raise ValueError(f"Unsupported encoding: {expected_encoding}")


def get_all_models_support_doc_extraction(
    must_support_mime_types: list[str] | None = None,
):
    model_provider_pairs = []
    for model in built_in_models:
        for provider in model.providers:
            if not provider.model_id:
                # it's possible for models to not have an ID (fine-tune only model)
                continue
            if provider.supports_doc_extraction:
                if (
                    provider.multimodal_mime_types is None
                    or must_support_mime_types is None
                ):
                    continue
                # check that the model supports all the mime types
                if all(
                    mime_type in provider.multimodal_mime_types
                    for mime_type in must_support_mime_types
                ):
                    model_provider_pairs.append((model.name, provider.name))
    return model_provider_pairs


@pytest.mark.paid
@pytest.mark.parametrize(
    "model_name,provider_name",
    get_all_models_support_doc_extraction(
        must_support_mime_types=[
            MockFileFactoryMimeType.PDF,
            MockFileFactoryMimeType.TXT,
            MockFileFactoryMimeType.MD,
            MockFileFactoryMimeType.HTML,
            MockFileFactoryMimeType.CSV,
            MockFileFactoryMimeType.PNG,
            MockFileFactoryMimeType.JPEG,
            MockFileFactoryMimeType.JPG,
            MockFileFactoryMimeType.MP4,
            MockFileFactoryMimeType.MOV,
            MockFileFactoryMimeType.MP3,
            MockFileFactoryMimeType.OGG,
            MockFileFactoryMimeType.WAV,
        ]
    ),
)
@pytest.mark.parametrize(
    "mime_type,expected_substring_in_output",
    [
        # documents
        (MockFileFactoryMimeType.PDF, "document"),
        (MockFileFactoryMimeType.TXT, "document"),
        (MockFileFactoryMimeType.MD, "document"),
        (MockFileFactoryMimeType.HTML, "document"),
        (MockFileFactoryMimeType.CSV, "document"),
        # images
        (MockFileFactoryMimeType.PNG, "image"),
        (MockFileFactoryMimeType.JPEG, "image"),
        (MockFileFactoryMimeType.JPG, "image"),
        # videos
        (MockFileFactoryMimeType.MP4, "video"),
        (MockFileFactoryMimeType.MOV, "video"),
        # audio
        (MockFileFactoryMimeType.MP3, "audio"),
        (MockFileFactoryMimeType.OGG, "audio"),
        (MockFileFactoryMimeType.WAV, "audio"),
    ],
)
async def test_extract_document_success(
    model_name,
    provider_name,
    mime_type,
    expected_substring_in_output,
    mock_file_factory,
):
    test_file = mock_file_factory(mime_type)
    extractor = paid_litellm_extractor(
        model_name=model_name, provider_name=provider_name
    )
    output = await extractor.extract(
        extraction_input=ExtractionInput(
            path=str(test_file),
            mime_type=mime_type,
        )
    )
    assert not output.is_passthrough
    assert output.content_format == OutputFormat.MARKDOWN
    assert expected_substring_in_output.lower() in output.content.lower()


@pytest.mark.paid
@pytest.mark.parametrize(
    "model_name,provider_name",
    get_all_models_support_doc_extraction(
        must_support_mime_types=[MockFileFactoryMimeType.PDF]
    ),
)
@pytest.mark.parametrize(
    "mime_type,expected_substring_in_output",
    [
        (MockFileFactoryMimeType.PDF, "document"),
    ],
)
async def test_extract_document_success_pdf(
    model_name,
    provider_name,
    mime_type,
    expected_substring_in_output,
    mock_file_factory,
):
    test_file = mock_file_factory(mime_type)
    extractor = paid_litellm_extractor(
        model_name=model_name, provider_name=provider_name
    )
    output = await extractor.extract(
        extraction_input=ExtractionInput(
            path=str(test_file),
            mime_type=mime_type,
        )
    )
    assert not output.is_passthrough
    assert output.content_format == OutputFormat.MARKDOWN
    assert expected_substring_in_output.lower() in output.content.lower()


async def test_extract_pdf_page_by_page(mock_file_factory, mock_litellm_extractor):
    """Test that PDFs are processed page by page with page numbers in output."""
    test_file = mock_file_factory(MockFileFactoryMimeType.PDF)

    # Mock responses for each page (PDF has 2 pages)
    mock_responses = []
    for i in range(2):  # PDF has 2 pages
        mock_response = AsyncMock(spec=ModelResponse)
        mock_choice = AsyncMock(spec=Choices)
        mock_message = AsyncMock()
        mock_message.content = f"Content from page {i + 1}"
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_responses.append(mock_response)

    with patch("litellm.acompletion", side_effect=mock_responses) as mock_acompletion:
        result = await mock_litellm_extractor.extract(
            ExtractionInput(
                path=str(test_file),
                mime_type="application/pdf",
            )
        )

    # Verify that the completion was called multiple times (once per page)
    assert mock_acompletion.call_count == 2

    # Verify the output contains content from both pages
    assert "Content from page 1" in result.content
    assert "Content from page 2" in result.content

    assert not result.is_passthrough
    assert result.content_format == OutputFormat.MARKDOWN


async def test_extract_pdf_page_by_page_error_handling(
    mock_file_factory, mock_litellm_extractor
):
    """Test that PDF page processing handles errors gracefully."""
    test_file = mock_file_factory(MockFileFactoryMimeType.PDF)

    # Mock the first page to succeed, second to fail
    mock_response1 = AsyncMock(spec=ModelResponse)
    mock_choice1 = AsyncMock(spec=Choices)
    mock_message1 = AsyncMock()
    mock_message1.content = "Content from page 1"
    mock_choice1.message = mock_message1
    mock_response1.choices = [mock_choice1]

    with patch(
        "litellm.acompletion", side_effect=[mock_response1, Exception("API Error")]
    ) as mock_acompletion:
        with pytest.raises(Exception, match="API Error"):
            await mock_litellm_extractor.extract(
                ExtractionInput(
                    path=str(test_file),
                    mime_type="application/pdf",
                )
            )

    # Verify that the completion was called at least once before failing
    assert mock_acompletion.call_count >= 1


@pytest.mark.paid
@pytest.mark.parametrize(
    "model_name,provider_name", get_all_models_support_doc_extraction()
)
async def test_provider_bad_request(tmp_path, model_name, provider_name):
    # write corrupted PDF file to temp files
    temp_file = tmp_path / "corrupted_file.pdf"
    temp_file.write_bytes(b"invalid file")

    extractor = paid_litellm_extractor(
        model_name=model_name, provider_name=provider_name
    )

    with pytest.raises(ValueError, match="Error extracting .*corrupted_file.pdf: "):
        await extractor.extract(
            extraction_input=ExtractionInput(
                path=temp_file.as_posix(),
                mime_type="application/pdf",
            )
        )
