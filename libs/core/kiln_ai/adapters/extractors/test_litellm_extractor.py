from pathlib import Path
from typing import List, Tuple
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from litellm.types.utils import Choices, ModelResponse

from conftest import MockFileFactoryMimeType
from kiln_ai.adapters.extractors.base_extractor import ExtractionInput, OutputFormat
from kiln_ai.adapters.extractors.encoding import to_base64_url
from kiln_ai.adapters.extractors.extractor_registry import extractor_adapter_from_type
from kiln_ai.adapters.extractors.litellm_extractor import (
    ExtractorConfig,
    Kind,
    LitellmExtractor,
    encode_file_litellm_format,
)
from kiln_ai.adapters.ml_model_list import (
    ModelName,
    built_in_models,
    built_in_models_from_provider,
)
from kiln_ai.adapters.provider_tools import LiteLlmCoreConfig
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.datamodel.extraction import ExtractorType
from kiln_ai.utils.filesystem_cache import FilesystemCache

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
        patch(
            "kiln_ai.adapters.extractors.litellm_extractor.split_pdf_into_pages",
            side_effect=Exception("error from split_pdf_into_pages"),
        ),
    ):
        # test the extract method
        with pytest.raises(
            ValueError,
            match=r"Error extracting test.pdf: error from split_pdf_into_pages",
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
        result = mock_litellm_extractor.litellm_model_slug

        assert result == "test-provider/test-model"

        # Verify the functions were called with correct arguments
        mock_built_in_models.assert_called_once()
        mock_get_provider_info.assert_called_once_with(mock_model_provider)


@pytest.mark.parametrize(
    "max_parallel_requests, expected_result",
    [
        (10, 10),
        (0, 0),
        # 5 is the current default, it may change in the future if we have
        # a better modeling of rate limit constraints
        (None, 5),
    ],
)
def test_litellm_model_max_parallel_requests(
    mock_litellm_extractor, max_parallel_requests, expected_result
):
    """Test that max_parallel_requests_for_model returns the provider's limit."""
    # Mock the built_in_models_from_provider function to return a valid model provider
    mock_model_provider = MagicMock()
    mock_model_provider.name = "test-provider"
    mock_model_provider.max_parallel_requests = max_parallel_requests

    with (
        patch(
            "kiln_ai.adapters.extractors.litellm_extractor.built_in_models_from_provider",
            return_value=mock_model_provider,
        ) as mock_built_in_models,
    ):
        result = mock_litellm_extractor.max_parallel_requests_for_model

        assert result == expected_result

        mock_built_in_models.assert_called_once()


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
            mock_litellm_extractor.litellm_model_slug


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
            result = extractor.litellm_model_slug
            assert result == expected_slug


def paid_litellm_extractor(model_name: str, provider_name: str):
    extractor = extractor_adapter_from_type(
        ExtractorType.LITELLM,
        ExtractorConfig(
            name="paid-litellm",
            extractor_type=ExtractorType.LITELLM,
            model_provider_name=provider_name,
            model_name=model_name,
            properties={
                "prompt_document": "Transcribe the document.",
                "prompt_image": "Describe the image in detail.",
                "prompt_video": "Transcribe the video and any shapes or objects in the video.",
                "prompt_audio": "Transcribe the audio and any spoken words in the audio.",
            },
            passthrough_mimetypes=[OutputFormat.MARKDOWN, OutputFormat.TEXT],
        ),
    )
    return extractor


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
    only_models: List[ModelName] | None = None,
) -> List[Tuple[str, ModelProviderName]]:
    model_provider_pairs: List[Tuple[str, ModelProviderName]] = []
    for model in built_in_models:
        # convenience arg for when we want to only test a subset of models
        # useful when adding only a handful of new extractor models
        if only_models is not None and model.name not in only_models:
            continue

        for provider in model.providers:
            if not provider.model_id:
                # it's possible for models to not have an ID (fine-tune only model)
                continue
            if provider.supports_doc_extraction:
                if (
                    provider.multimodal_mime_types is None
                    or must_support_mime_types is None
                ):
                    model_provider_pairs.append((model.name, provider.name))
                    continue
                # check that the model supports all the mime types
                if all(
                    mime_type in provider.multimodal_mime_types
                    for mime_type in must_support_mime_types
                ):
                    model_provider_pairs.append((model.name, provider.name))
    return model_provider_pairs


@pytest.mark.parametrize(
    "model_name,provider_name",
    get_all_models_support_doc_extraction(
        must_support_mime_types=None,
        only_models=None,
    ),
)
def test_supports_vision_is_coherent(model_name, provider_name):
    model = built_in_models_from_provider(provider_name, model_name)
    assert model is not None

    vision_mime_types = [
        MockFileFactoryMimeType.JPG,
        MockFileFactoryMimeType.PNG,
        MockFileFactoryMimeType.JPEG,
        MockFileFactoryMimeType.MP4,
        MockFileFactoryMimeType.MOV,
    ]

    if model.supports_vision:
        # a model can only be vision if it is multimodal
        assert model.multimodal_capable

        # a model can only be vision if it supports some image types or video types
        assert model.multimodal_mime_types is not None
        assert any(
            mime_type in model.multimodal_mime_types for mime_type in vision_mime_types
        )

    # any model that supports image or video types is a vision model
    if model.multimodal_mime_types is not None:
        if any(
            mime_type in model.multimodal_mime_types for mime_type in vision_mime_types
        ):
            assert model.supports_vision


@pytest.mark.paid
@pytest.mark.parametrize(
    "model_name,provider_name",
    get_all_models_support_doc_extraction(
        must_support_mime_types=None,
        only_models=None,
    ),
)
@pytest.mark.parametrize(
    "mime_type,text_probe",
    [
        # NOTE:
        # - live model assertions are flaky so we put in a few synonyms that are likely
        # to be in the output (e.g. sometimes the model says "parrot", sometimes it says "bird" or "macaw")
        # - the point of these tests is to ensure it reads the file; sometimes, a provider may accept the
        # file input but in practice not read it, or corrupt it (e.g. OpenRouter does this with videos and audio
        # at the moment, on at least some models)
        #
        # documents
        (MockFileFactoryMimeType.PDF, ["attention"]),
        (MockFileFactoryMimeType.TXT, ["water"]),
        (MockFileFactoryMimeType.MD, ["thermodynamics"]),
        (MockFileFactoryMimeType.HTML, ["ice cube"]),
        (MockFileFactoryMimeType.CSV, ["McConville"]),
        # images
        (MockFileFactoryMimeType.PNG, ["parrot", "bird", "macaw"]),
        (MockFileFactoryMimeType.JPEG, ["earth", "地球"]),
        (MockFileFactoryMimeType.JPG, ["earth", "地球"]),
        # videos
        (MockFileFactoryMimeType.MP4, ["color"]),
        (MockFileFactoryMimeType.MOV, ["color"]),
        # audio
        (MockFileFactoryMimeType.MP3, ["ice cube"]),
        (MockFileFactoryMimeType.OGG, ["ice cube"]),
        (MockFileFactoryMimeType.WAV, ["ice cube"]),
    ],
)
async def test_extract_document_success(
    model_name,
    provider_name,
    mime_type,
    text_probe,
    mock_file_factory,
):
    # get model
    model = built_in_models_from_provider(provider_name, model_name)
    assert model is not None
    if mime_type not in model.multimodal_mime_types:
        pytest.skip(f"Model {model_name} configured to not support {mime_type}")
    if (
        mime_type == MockFileFactoryMimeType.MD
        or mime_type == MockFileFactoryMimeType.TXT
    ):
        pytest.skip(f"Model {model_name} configured to passthrough {mime_type}")

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

    text_probe_str = ", ".join(text_probe)

    # check that any of the expected substrings are in the output
    assert any(
        text_probe.lower() in output.content.lower() for text_probe in text_probe
    ), f"Expected any of [{text_probe_str}] to be in output: {output.content}"


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


async def test_extract_pdf_page_by_page_pdf_as_image(
    mock_file_factory, mock_litellm_extractor, tmp_path
):
    """Test that PDFs are processed page by page as images if the model requires it."""

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

    mock_image_path = tmp_path / "img-test_document-mock.png"
    mock_image_path.write_bytes(b"test image")

    with patch("litellm.acompletion", side_effect=mock_responses) as mock_acompletion:
        # this model requires PDFs to be processed as images
        mock_litellm_extractor.model_provider.multimodal_requires_pdf_as_image = True

        with patch(
            "kiln_ai.adapters.extractors.litellm_extractor.convert_pdf_to_images",
            return_value=[mock_image_path],
        ) as mock_convert:
            result = await mock_litellm_extractor.extract(
                ExtractionInput(
                    path=str(test_file),
                    mime_type="application/pdf",
                )
            )

    # Verify image conversion called once per page
    assert mock_convert.call_count == 2

    # Verify LiteLLM was called with image inputs (not PDF) for each page
    for call in mock_acompletion.call_args_list:
        kwargs = call.kwargs
        content = kwargs["messages"][0]["content"]
        assert content[1]["type"] == "image_url"

    # Verify that the completion was called multiple times (once per page)
    assert mock_acompletion.call_count == 2

    # Verify the output contains content from both pages
    assert "Content from page 1" in result.content
    assert "Content from page 2" in result.content

    assert not result.is_passthrough
    assert result.content_format == OutputFormat.MARKDOWN


async def test_convert_pdf_page_to_image_input_success(
    mock_litellm_extractor, tmp_path
):
    page_dir = tmp_path / "pages"
    page_dir.mkdir()
    page_path = page_dir / "page_1.pdf"
    page_path.write_bytes(b"%PDF-1.4 test")

    mock_image_path = page_dir / "img-page_1.pdf-0.png"
    mock_image_path.write_bytes(b"image-bytes")

    with patch(
        "kiln_ai.adapters.extractors.litellm_extractor.convert_pdf_to_images",
        return_value=[mock_image_path],
    ):
        extraction_input = await mock_litellm_extractor.convert_pdf_page_to_image_input(
            page_path, 0
        )

    assert extraction_input.mime_type == "image/png"
    assert Path(extraction_input.path) == mock_image_path


@pytest.mark.parametrize("returned_count", [0, 2])
async def test_convert_pdf_page_to_image_input_error_on_invalid_count(
    mock_litellm_extractor, tmp_path, returned_count
):
    page_dir = tmp_path / "pages"
    page_dir.mkdir()
    page_path = page_dir / "page_1.pdf"
    page_path.write_bytes(b"%PDF-1.4 test")

    image_paths = []
    if returned_count == 2:
        img1 = page_dir / "img-page_1.pdf-0.png"
        img2 = page_dir / "img-page_1.pdf-1.png"
        img1.write_bytes(b"i1")
        img2.write_bytes(b"i2")
        image_paths = [img1, img2]

    with patch(
        "kiln_ai.adapters.extractors.litellm_extractor.convert_pdf_to_images",
        return_value=image_paths,
    ):
        with pytest.raises(ValueError, match=r"Expected 1 image, got "):
            await mock_litellm_extractor.convert_pdf_page_to_image_input(page_path, 0)


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

    with pytest.raises(ValueError, match=r"Error extracting .*corrupted_file.pdf: "):
        await extractor.extract(
            extraction_input=ExtractionInput(
                path=temp_file.as_posix(),
                mime_type="application/pdf",
            )
        )


# Cache-related tests for PDF processing
@pytest.fixture
def mock_litellm_extractor_with_cache(tmp_path):
    """Create a LitellmExtractor with a filesystem cache for testing."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()  # Ensure cache directory exists
    cache = FilesystemCache(cache_dir)
    return LitellmExtractor(
        ExtractorConfig(
            id="test_extractor_123",  # Required for cache key generation
            name="mock_with_cache",
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
        filesystem_cache=cache,
    )


@pytest.fixture
def mock_litellm_extractor_without_cache():
    """Create a LitellmExtractor without a filesystem cache for testing."""
    return LitellmExtractor(
        ExtractorConfig(
            id="test_extractor_456",  # Required for cache key generation
            name="mock_without_cache",
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
        filesystem_cache=None,  # Explicitly no cache
    )


def test_pdf_page_cache_key_generation(mock_litellm_extractor_with_cache):
    """Test that PDF page cache keys are generated correctly."""
    pdf_path = Path("test_document.pdf")
    page_number = 0

    cache_key = mock_litellm_extractor_with_cache.pdf_page_cache_key(
        pdf_path, page_number
    )

    # Should include extractor ID and a hash of the PDF name and page number
    assert cache_key.startswith("test_extractor_123_")
    assert len(cache_key) > len("test_extractor_123_")  # Should have hash suffix

    # Same PDF and page should generate same key
    cache_key2 = mock_litellm_extractor_with_cache.pdf_page_cache_key(
        pdf_path, page_number
    )
    assert cache_key == cache_key2

    # Different page should generate different key
    cache_key3 = mock_litellm_extractor_with_cache.pdf_page_cache_key(pdf_path, 1)
    assert cache_key != cache_key3


def test_pdf_page_cache_key_requires_extractor_id():
    """Test that PDF page cache key generation requires extractor ID."""
    extractor_config = ExtractorConfig(
        id=None,  # No ID
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
    )

    extractor = LitellmExtractor(
        extractor_config,
        LiteLlmCoreConfig(
            base_url="https://test.com",
            additional_body_options={"api_key": "test-key"},
            default_headers={},
        ),
    )

    with pytest.raises(
        ValueError, match="Extractor config ID is required for PDF page cache key"
    ):
        extractor.pdf_page_cache_key(Path("test.pdf"), 0)


async def test_extract_pdf_with_cache_storage(
    mock_file_factory, mock_litellm_extractor_with_cache
):
    """Test that PDF extraction stores content in cache when cache is available."""
    test_file = mock_file_factory(MockFileFactoryMimeType.PDF)

    # Mock responses for each page (PDF has 2 pages)
    mock_responses = []
    for i in range(2):
        mock_response = AsyncMock(spec=ModelResponse)
        mock_choice = AsyncMock(spec=Choices)
        mock_message = AsyncMock()
        mock_message.content = f"Content from page {i + 1}"
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_responses.append(mock_response)

    with patch("litellm.acompletion", side_effect=mock_responses) as mock_acompletion:
        result = await mock_litellm_extractor_with_cache.extract(
            ExtractionInput(
                path=str(test_file),
                mime_type="application/pdf",
            )
        )

    # Verify that the completion was called for each page
    assert mock_acompletion.call_count == 2

    # Verify content is stored in cache - note that order is not guaranteed since
    # we batch the page extraction requests in parallel
    pdf_path = Path(test_file)
    cached_contents = []
    for i in range(2):
        cached_content = (
            await mock_litellm_extractor_with_cache.get_page_content_from_cache(
                pdf_path, i
            )
        )
        assert cached_content is not None
        cached_contents.append(cached_content)
    assert set(cached_contents) == {"Content from page 1", "Content from page 2"}

    # Verify the output contains content from both pages
    assert "Content from page 1" in result.content
    assert "Content from page 2" in result.content


async def test_extract_pdf_with_cache_retrieval(
    mock_file_factory, mock_litellm_extractor_with_cache
):
    """Test that PDF extraction retrieves content from cache when available."""
    test_file = mock_file_factory(MockFileFactoryMimeType.PDF)
    pdf_path = Path(test_file)

    # Pre-populate cache with content
    for i in range(2):
        cache_key = mock_litellm_extractor_with_cache.pdf_page_cache_key(pdf_path, i)
        await mock_litellm_extractor_with_cache.filesystem_cache.set(
            cache_key, f"Cached content from page {i + 1}".encode("utf-8")
        )

    # Mock responses (should not be called due to cache hits)
    mock_responses = []
    for i in range(2):
        mock_response = AsyncMock(spec=ModelResponse)
        mock_choice = AsyncMock(spec=Choices)
        mock_message = AsyncMock()
        mock_message.content = f"Fresh content from page {i + 1}"
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_responses.append(mock_response)

    with patch("litellm.acompletion", side_effect=mock_responses) as mock_acompletion:
        result = await mock_litellm_extractor_with_cache.extract(
            ExtractionInput(
                path=str(test_file),
                mime_type="application/pdf",
            )
        )

    # Verify that litellm.acompletion was NOT called (cache hits)
    assert mock_acompletion.call_count == 0

    # Verify the output contains cached content, not fresh content
    assert "Cached content from page 1" in result.content
    assert "Cached content from page 2" in result.content
    assert "Fresh content from page 1" not in result.content
    assert "Fresh content from page 2" not in result.content


async def test_extract_pdf_without_cache(
    mock_file_factory, mock_litellm_extractor_without_cache
):
    """Test that PDF extraction works normally when no cache is provided."""
    test_file = mock_file_factory(MockFileFactoryMimeType.PDF)

    # Mock responses for each page (PDF has 2 pages)
    mock_responses = []
    for i in range(2):
        mock_response = AsyncMock(spec=ModelResponse)
        mock_choice = AsyncMock(spec=Choices)
        mock_message = AsyncMock()
        mock_message.content = f"Content from page {i + 1}"
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_responses.append(mock_response)

    with patch("litellm.acompletion", side_effect=mock_responses) as mock_acompletion:
        result = await mock_litellm_extractor_without_cache.extract(
            ExtractionInput(
                path=str(test_file),
                mime_type="application/pdf",
            )
        )

    # Verify that the completion was called for each page
    assert mock_acompletion.call_count == 2

    # Verify the output contains content from both pages
    assert "Content from page 1" in result.content
    assert "Content from page 2" in result.content


async def test_extract_pdf_mixed_cache_hits_and_misses(
    mock_file_factory, mock_litellm_extractor_with_cache
):
    """Test PDF extraction with some pages cached and others not."""
    test_file = mock_file_factory(MockFileFactoryMimeType.PDF)
    pdf_path = Path(test_file)

    # Pre-populate cache with only page 0 content
    cache_key = mock_litellm_extractor_with_cache.pdf_page_cache_key(pdf_path, 0)
    await mock_litellm_extractor_with_cache.filesystem_cache.set(
        cache_key, "Cached content from page 1".encode("utf-8")
    )

    # Mock responses for page 1 only (page 0 should hit cache)
    mock_response = AsyncMock(spec=ModelResponse)
    mock_choice = AsyncMock(spec=Choices)
    mock_message = AsyncMock()
    mock_message.content = "Fresh content from page 2"
    mock_choice.message = mock_message
    mock_response.choices = [mock_choice]

    with patch("litellm.acompletion", return_value=mock_response) as mock_acompletion:
        result = await mock_litellm_extractor_with_cache.extract(
            ExtractionInput(
                path=str(test_file),
                mime_type="application/pdf",
            )
        )

    # Verify that litellm.acompletion was called only once (for page 1)
    assert mock_acompletion.call_count == 1

    # Verify the output contains both cached and fresh content
    assert "Cached content from page 1" in result.content
    assert "Fresh content from page 2" in result.content


async def test_extract_pdf_cache_write_failure_does_not_throw(
    mock_file_factory, mock_litellm_extractor_with_cache
):
    """Test that PDF extraction continues successfully even when cache write fails."""
    test_file = mock_file_factory(MockFileFactoryMimeType.PDF)

    # Mock responses for each page (PDF has 2 pages)
    mock_responses = []
    for i in range(2):
        mock_response = AsyncMock(spec=ModelResponse)
        mock_choice = AsyncMock(spec=Choices)
        mock_message = AsyncMock()
        mock_message.content = f"Content from page {i + 1}"
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_responses.append(mock_response)

    # Mock the cache set method to raise an exception
    with patch.object(
        mock_litellm_extractor_with_cache.filesystem_cache,
        "set",
        side_effect=Exception("Cache write failed"),
    ) as mock_cache_set:
        with patch(
            "litellm.acompletion", side_effect=mock_responses
        ) as mock_acompletion:
            # This should not raise an exception despite cache write failures
            result = await mock_litellm_extractor_with_cache.extract(
                ExtractionInput(
                    path=str(test_file),
                    mime_type="application/pdf",
                )
            )

    # Verify that the completion was called for each page
    assert mock_acompletion.call_count == 2

    # Verify that cache.set was called for each page (and failed)
    assert mock_cache_set.call_count == 2

    # Verify the output contains content from both pages despite cache failures
    assert "Content from page 1" in result.content
    assert "Content from page 2" in result.content

    # Verify the extraction completed successfully
    assert not result.is_passthrough
    assert result.content_format == OutputFormat.MARKDOWN


async def test_extract_pdf_cache_decode_failure_does_not_throw(
    mock_file_factory, mock_litellm_extractor_with_cache
):
    """Test that PDF extraction continues successfully even when cache decode fails."""
    test_file = mock_file_factory(MockFileFactoryMimeType.PDF)
    pdf_path = Path(test_file)

    # Pre-populate cache with invalid UTF-8 bytes that will cause decode failure
    for i in range(2):
        cache_key = mock_litellm_extractor_with_cache.pdf_page_cache_key(pdf_path, i)
        # Use bytes that are not valid UTF-8 (e.g., some binary data)
        invalid_utf8_bytes = b"\xff\xfe\x00\x00"  # Invalid UTF-8 sequence
        await mock_litellm_extractor_with_cache.filesystem_cache.set(
            cache_key, invalid_utf8_bytes
        )

    # Mock responses for each page (PDF has 2 pages) - should be called due to decode failures
    mock_responses = []
    for i in range(2):
        mock_response = AsyncMock(spec=ModelResponse)
        mock_choice = AsyncMock(spec=Choices)
        mock_message = AsyncMock()
        mock_message.content = f"Content from page {i + 1}"
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_responses.append(mock_response)

    with patch("litellm.acompletion", side_effect=mock_responses) as mock_acompletion:
        # This should not raise an exception despite cache decode failures
        result = await mock_litellm_extractor_with_cache.extract(
            ExtractionInput(
                path=str(test_file),
                mime_type="application/pdf",
            )
        )

    # Verify that the completion was called for each page (due to decode failures)
    assert mock_acompletion.call_count == 2

    # Verify the output contains content from both pages despite cache decode failures
    assert "Content from page 1" in result.content
    assert "Content from page 2" in result.content

    # Verify the extraction completed successfully
    assert not result.is_passthrough
    assert result.content_format == OutputFormat.MARKDOWN


async def test_extract_pdf_parallel_processing_error_handling(
    mock_file_factory, mock_litellm_extractor_with_cache
):
    """Test that parallel processing handles errors correctly."""
    test_file = mock_file_factory(MockFileFactoryMimeType.PDF)

    # Mock first page to succeed, second to fail
    mock_response1 = AsyncMock(spec=ModelResponse)
    mock_choice1 = AsyncMock(spec=Choices)
    mock_message1 = AsyncMock()
    mock_message1.content = "Success from page 1"
    mock_choice1.message = mock_message1
    mock_response1.choices = [mock_choice1]

    with patch(
        "litellm.acompletion",
        side_effect=[mock_response1, Exception("API Error on page 2")],
    ) as mock_acompletion:
        with pytest.raises(ValueError, match=r".*API Error on page 2"):
            await mock_litellm_extractor_with_cache.extract(
                ExtractionInput(
                    path=str(test_file),
                    mime_type="application/pdf",
                )
            )

    # Verify that both pages were attempted
    assert mock_acompletion.call_count == 2


async def test_extract_pdf_parallel_processing_all_cached(
    mock_file_factory, mock_litellm_extractor_with_cache
):
    """Test parallel processing when all pages are cached."""
    test_file = mock_file_factory(MockFileFactoryMimeType.PDF)
    pdf_path = Path(test_file)

    # Pre-populate cache with both pages
    for i in range(2):
        cache_key = mock_litellm_extractor_with_cache.pdf_page_cache_key(pdf_path, i)
        await mock_litellm_extractor_with_cache.filesystem_cache.set(
            cache_key, f"Cached content from page {i + 1}".encode("utf-8")
        )

    # Mock responses (should not be called due to cache hits)
    mock_responses = []
    for i in range(2):
        mock_response = AsyncMock(spec=ModelResponse)
        mock_choice = AsyncMock(spec=Choices)
        mock_message = AsyncMock()
        mock_message.content = f"Fresh content from page {i + 1}"
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_responses.append(mock_response)

    with patch("litellm.acompletion", side_effect=mock_responses) as mock_acompletion:
        result = await mock_litellm_extractor_with_cache.extract(
            ExtractionInput(
                path=str(test_file),
                mime_type="application/pdf",
            )
        )

    # Verify that no API calls were made (all pages cached)
    assert mock_acompletion.call_count == 0

    # Verify the output contains cached content
    assert "Cached content from page 1" in result.content
    assert "Cached content from page 2" in result.content
    assert "Fresh content from page 1" not in result.content
    assert "Fresh content from page 2" not in result.content
