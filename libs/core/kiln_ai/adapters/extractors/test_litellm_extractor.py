from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from litellm import Message
from litellm.types.utils import Choices, ModelResponse

from conftest import MockFileFactoryMimeType
from kiln_ai.adapters.extractors.base_extractor import (
    ExtractionInput,
    ExtractionOutput,
    OutputFormat,
)
from kiln_ai.adapters.extractors.encoding import to_base64_url
from kiln_ai.adapters.extractors.litellm_extractor import (
    ExtractorConfig,
    Kind,
    LitellmExtractor,
    encode_file,
)
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
            properties={
                "prompt_document": PROMPTS_FOR_KIND["document"],
                "prompt_image": PROMPTS_FOR_KIND["image"],
                "prompt_video": PROMPTS_FOR_KIND["video"],
                "prompt_audio": PROMPTS_FOR_KIND["audio"],
                "model_name": "model-name",
                "model_provider_name": "provider-name",
            },
        ),
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


async def test_extract_success(mock_file_factory, mock_litellm_extractor):
    test_pdf_file = mock_file_factory(MockFileFactoryMimeType.PDF)
    test_pdf_file_bytes = Path(test_pdf_file).read_bytes()

    # we expect the base64 URL to be passed on to litellm
    base64_url = to_base64_url("application/pdf", test_pdf_file_bytes)

    # Mock the litellm response structure
    mock_message = AsyncMock(spec=Message)
    mock_message.content = "extracted content"
    mock_choice = AsyncMock(spec=Choices)
    mock_choice.message = mock_message
    mock_response = AsyncMock(spec=ModelResponse)
    mock_response.choices = [mock_choice]

    with (
        patch("pathlib.Path.read_bytes", return_value=test_pdf_file_bytes),
        patch("litellm.acompletion", return_value=mock_response) as mock_acompletion,
    ):
        # test the extract method
        result = await mock_litellm_extractor.extract(
            extraction_input=ExtractionInput(
                path=str(test_pdf_file),
                mime_type="application/pdf",
                model_slug="provider-name/model-name",
            )
        )

        assert result == ExtractionOutput(
            is_passthrough=False,
            content="extracted content",
            content_format=OutputFormat.MARKDOWN,
        )

        # check that litellm.acompletion was called with the correct arguments
        mock_acompletion.assert_awaited_once()

        # Verify the call arguments
        call_args = mock_acompletion.call_args
        assert call_args[1]["model"] == "provider-name/model-name"
        assert call_args[1]["messages"][0]["role"] == "user"
        assert call_args[1]["messages"][0]["content"][0]["type"] == "text"
        assert (
            call_args[1]["messages"][0]["content"][0]["text"]
            == PROMPTS_FOR_KIND["document"]
        )

        # check that the file was read correctly
        assert call_args[1]["messages"][0]["content"][1]["type"] == "file"
        assert (
            call_args[1]["messages"][0]["content"][1]["file"]["file_data"] == base64_url
        )


async def test_extract_failure_from_litellm(mock_file_factory, mock_litellm_extractor):
    test_pdf_file = mock_file_factory(MockFileFactoryMimeType.PDF)

    with (
        patch("pathlib.Path.read_bytes", return_value=b"test content"),
        patch("litellm.acompletion", side_effect=Exception("error from litellm")),
    ):
        # Mock litellm to raise an exception
        with pytest.raises(Exception, match="error from litellm"):
            await mock_litellm_extractor.extract(
                extraction_input=ExtractionInput(
                    path=str(test_pdf_file),
                    mime_type="application/pdf",
                    model_slug="provider-name/model-name",
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
    ):
        # test the extract method
        with pytest.raises(ValueError, match="error from read_bytes"):
            await mock_litellm_extractor.extract(
                extraction_input=ExtractionInput(
                    path="test.pdf",
                    mime_type="application/pdf",
                    model_slug="provider-name/model-name",
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
                    model_slug="provider-name/model-name",
                )
            )


# TODO: dynamic model list - get rid of this
# need to keep track of mimetypes for each model, because most models
# such as OpenAI's don't support videos and a lot of other files via
# the normal completion API (some they do via assistant API, but no
# multimodal support for video at all - only frames fed as an array of images
# which would require our own processing and is much worse than Gemini's
# native video understanding).
SUPPORTED_MODELS = [
    "gemini/gemini-2.5-pro",
    "gemini/gemini-2.5-flash",
    "gemini/gemini-2.0-flash",
    "gemini/gemini-2.0-flash-lite",
]


def paid_litellm_extractor(model_name: str):
    return LitellmExtractor(
        extractor_config=ExtractorConfig(
            name="paid-litellm",
            extractor_type=ExtractorType.LITELLM,
            properties={
                "model_name": model_name,
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
def test_encode_file(mock_file_factory, mime_type, expected_encoding):
    test_file = mock_file_factory(mime_type)
    encoded = encode_file(Path(test_file), mime_type)

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


@pytest.mark.paid
@pytest.mark.parametrize("model_name", SUPPORTED_MODELS)
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
    model_name, mime_type, expected_substring_in_output, mock_file_factory
):
    test_file = mock_file_factory(mime_type)
    extractor = paid_litellm_extractor(model_name=model_name)
    output = await extractor.extract(
        extraction_input=ExtractionInput(
            path=str(test_file),
            mime_type=mime_type,
            model_slug=model_name,
        )
    )
    assert not output.is_passthrough
    assert output.content_format == OutputFormat.MARKDOWN
    assert expected_substring_in_output.lower() in output.content.lower()


@pytest.mark.paid
@pytest.mark.parametrize("model_name", SUPPORTED_MODELS)
async def test_provider_bad_request(tmp_path, model_name):
    # write corrupted PDF file to temp files
    temp_file = tmp_path / "corrupted_file.pdf"
    temp_file.write_bytes(b"invalid file")

    extractor = paid_litellm_extractor(model_name=model_name)

    with pytest.raises(ValueError, match="Error extracting .*corrupted_file.pdf: "):
        await extractor.extract(
            extraction_input=ExtractionInput(
                path=temp_file.as_posix(),
                mime_type="application/pdf",
                model_slug=model_name,
            )
        )
