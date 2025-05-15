import pathlib

from google import genai
from google.genai import types

from kiln_ai.adapters.extraction.base_extractor import (
    BaseExtractor,
    ExtractionOutput,
    FileInfoInternal,
)
from kiln_ai.datamodel.extraction import ExtractorConfig, ExtractorType, Kind

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
        "video/mov",
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
        if extractor_config.extractor_type != ExtractorType.gemini:
            raise ValueError(
                f"GeminiExtractor must be initialized with a gemini extractor_type config. Got {extractor_config.extractor_type}"
            )

        super().__init__(extractor_config)
        self.gemini_client = gemini_client
        self.gemini_config = extractor_config.gemini_properties()

    def _get_kind_from_mime_type(self, mime_type: str) -> Kind | None:
        for kind, mime_types in MIME_TYPES_SUPPORTED.items():
            if mime_type in mime_types:
                return kind
        return None

    def _extract(self, file_info: FileInfoInternal) -> ExtractionOutput:
        kind = self._get_kind_from_mime_type(file_info.mime_type)
        if kind is None:
            raise ValueError(f"Unsupported MIME type: {file_info.mime_type}")

        prompt = self.gemini_config.prompt_for_kind.get(kind)
        if prompt is None:
            raise ValueError(f"No prompt found for kind: {kind}")

        response = self.gemini_client.models.generate_content(
            model=self.gemini_config.model_name,
            contents=[
                types.Part.from_bytes(
                    data=pathlib.Path(file_info.path).read_bytes(),
                    mime_type=file_info.mime_type,
                ),
                prompt,
            ],
        )

        if response.text is None:
            raise ValueError("No text returned from Gemini when extracting document")

        return ExtractionOutput(
            is_passthrough=False,
            content=response.text,
            content_format=self.extractor_config.output_format,
        )
