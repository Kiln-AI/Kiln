import base64
from pathlib import Path
from typing import Any

import litellm
from google import genai
from litellm.types.utils import Choices, ModelResponse

from kiln_ai.adapters.extractors.base_extractor import BaseExtractor, ExtractionOutput
from kiln_ai.datamodel.extraction import ExtractorConfig, ExtractorType, Kind
from kiln_ai.utils.config import Config

# docs list out supported formats:
# - https://ai.google.dev/gemini-api/docs/document-processing#supported-formats
# - https://ai.google.dev/gemini-api/docs/image-understanding#supported-formats
# - https://ai.google.dev/gemini-api/docs/video-understanding#supported-formats
# - https://ai.google.dev/gemini-api/docs/audio#supported-formats
MIME_TYPES_SUPPORTED = {
    Kind.DOCUMENT: [
        "application/pdf",
        "application/x-javascript",
        "text/javascript",
        "application/x-python",
        "text/x-python",
        "text/plain",
        "text/markdown",  # not officially listed, but works
        "text/html",
        "text/css",
        "text/md",
        "text/csv",
        "text/xml",
        "text/rtf",
    ],
    Kind.IMAGE: [
        "image/png",
        "image/jpeg",
        "image/webp",
        "image/heic",
        "image/heif",
    ],
    Kind.VIDEO: [
        "video/mp4",
        "video/mpeg",
        "video/mov",  # the correct type is video/quicktime, but Google lists it as video/mov
        "video/quicktime",
        "video/avi",
        "video/x-flv",
        "video/mpg",
        "video/webm",
        "video/wmv",
        "video/3gpp",
    ],
    Kind.AUDIO: [
        "audio/wav",
        "audio/mp3",
        "audio/mpeg",  # not explicitly supported, but mimetypes stdlib returns audio/mpeg for MP3
        "audio/aiff",
        "audio/aac",
        "audio/ogg",
        "audio/flac",
    ],
}


class GeminiExtractor(BaseExtractor):
    def __init__(self, gemini_client: genai.Client, extractor_config: ExtractorConfig):
        if extractor_config.extractor_type != ExtractorType.GEMINI:
            raise ValueError(
                f"GeminiExtractor must be initialized with a gemini extractor_type config. Got {extractor_config.extractor_type}"
            )

        model_name = extractor_config.model_name()
        if model_name is None:
            raise ValueError("properties.model_name is required for GeminiExtractor")

        prompt_document = extractor_config.prompt_document()
        if prompt_document is None or prompt_document == "":
            raise ValueError(
                "properties.prompt_document is required for GeminiExtractor"
            )
        prompt_video = extractor_config.prompt_video()
        if prompt_video is None or prompt_video == "":
            raise ValueError("properties.prompt_video is required for GeminiExtractor")
        prompt_audio = extractor_config.prompt_audio()
        if prompt_audio is None or prompt_audio == "":
            raise ValueError("properties.prompt_audio is required for GeminiExtractor")
        prompt_image = extractor_config.prompt_image()
        if prompt_image is None or prompt_image == "":
            raise ValueError("properties.prompt_image is required for GeminiExtractor")

        super().__init__(extractor_config)
        self.gemini_client = gemini_client
        self.model_name = model_name
        self.prompt_for_kind = {
            Kind.DOCUMENT: prompt_document,
            Kind.VIDEO: prompt_video,
            Kind.AUDIO: prompt_audio,
            Kind.IMAGE: prompt_image,
        }

    def _get_kind_from_mime_type(self, mime_type: str) -> Kind | None:
        for kind, mime_types in MIME_TYPES_SUPPORTED.items():
            if mime_type in mime_types:
                return kind
        return None

    async def _extract(self, path: Path, mime_type: str) -> ExtractionOutput:
        kind = self._get_kind_from_mime_type(mime_type)
        if kind is None:
            raise ValueError(
                f"Unsupported MIME type: {mime_type} for {path} with {self.model_name}"
            )

        prompt = self.prompt_for_kind.get(kind)
        if prompt is None:
            raise ValueError(f"No prompt found for kind: {kind}")

        # FIXME: the supports_pdf_input check does not seem to work for gemini models
        # if not supports_pdf_input(self.model_name):
        #     raise ValueError(f"Model {self.model_name} does not support PDF input")

        # FIXME: check vision support
        # supports_vision(model=self.model_name)

        def encode_file(path: Path, mime_type: str) -> dict[str, Any]:
            def to_base64_url(mime_type: str, bytes: bytes) -> str:
                base64_url = (
                    f"data:{mime_type};base64,{base64.b64encode(bytes).decode('utf-8')}"
                )
                return base64_url

            if mime_type == "application/pdf" or mime_type.startswith("image/"):
                pdf_bytes = path.read_bytes()
                return {
                    "type": "file",
                    "file": {
                        "file_data": to_base64_url(mime_type, pdf_bytes),
                    },
                }
            if mime_type.startswith("image/"):
                image_bytes = path.read_bytes()
                return {
                    "type": "image_url",
                    "image_url": {
                        "url": to_base64_url(mime_type, image_bytes),
                    },
                }
            if mime_type.startswith("video/"):
                video_bytes = path.read_bytes()
                return {
                    "type": "file",
                    "file": {
                        "file_data": to_base64_url(mime_type, video_bytes),
                    },
                }
            if mime_type.startswith("audio/"):
                audio_bytes = path.read_bytes()
                return {
                    "type": "file",
                    "file": {
                        "file_data": to_base64_url(mime_type, audio_bytes),
                    },
                }
            raise ValueError(f"Unsupported MIME type: {mime_type} for {path}")

        file_content = [
            {"type": "text", "text": prompt},
            encode_file(path, mime_type),
        ]

        response = await litellm.acompletion(
            model=self.model_name,
            messages=[{"role": "user", "content": file_content}],
            api_key=Config.shared().gemini_api_key,
        )

        if (
            not isinstance(response, ModelResponse)
            or not response.choices
            or len(response.choices) == 0
            or not isinstance(response.choices[0], Choices)
        ):
            raise RuntimeError(
                f"Expected ModelResponse with Choices, got {type(response)}."
            )

        if response.choices[0].message.content is None:
            raise ValueError("No text returned from Gemini when extracting document")

        return ExtractionOutput(
            is_passthrough=False,
            content=response.choices[0].message.content,
            content_format=self.extractor_config.output_format,
        )


def get_genai_client() -> genai.Client:
    return genai.Client(api_key=Config.shared().gemini_api_key)


def build_gemini_extractor(extractor_config: ExtractorConfig) -> GeminiExtractor:
    return GeminiExtractor(get_genai_client(), extractor_config)
