from enum import Enum

from google import genai
from google.genai import types
from pydantic import Field

from kiln_ai.adapters.extractors.base_extractor import (
    BaseExtractor,
    BaseExtractorConfig,
    ExtractionFormat,
    ExtractionOutput,
    FileInfoInternal,
)


class Kind(Enum):
    DOCUMENT = "document"

    # NOTE: maybe remove the these ones for now as we don't use them and the mimetypes list for them
    # might evolve by the time we do add support for them
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"


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


class GeminiExtractorConfig(BaseExtractorConfig):
    default_prompt: str = Field(
        description="The default prompt to use for the extractor."
    )
    prompt_for_kind: dict[Kind, str] = Field(
        default_factory=dict,
        description="A dictionary of prompts for each kind of file.",
    )
    model: str = Field(description="The model to use for the extractor.")
    output_format: ExtractionFormat = Field(
        default=ExtractionFormat.MARKDOWN,
        description="The format to use for the output.",
    )


class GeminiExtractor(BaseExtractor):
    def __init__(self, gemini_client: genai.Client, config: GeminiExtractorConfig):
        super().__init__(config)
        self.config = config
        self.gemini_client = gemini_client

    def _get_kind_from_mime_type(self, mime_type: str) -> Kind:
        for kind, mime_types in MIME_TYPES_SUPPORTED.items():
            if mime_type in mime_types:
                return kind
        raise ValueError(f"Unsupported MIME type: {mime_type}")

    def _get_prompt_for_kind(self, kind: Kind) -> str:
        return self.config.prompt_for_kind.get(kind, self.config.default_prompt)

    def _extract(
        self, file_info: FileInfoInternal, custom_prompt: str | None
    ) -> ExtractionOutput:
        kind = self._get_kind_from_mime_type(file_info.mime_type)
        custom_prompt = custom_prompt or self._get_prompt_for_kind(kind)

        # TODO:
        # - seems to be a way to upload the file and reuse later - need to check if this is suitable or useful
        #   - https://ai.google.dev/api/files
        # - also nice if we could pass in a stream instead of loading the file into memory, maybe do if trivial
        response = self.gemini_client.models.generate_content(
            model=self.config.model,
            contents=[
                types.Part.from_bytes(
                    data=self._load_file_bytes(file_info.path),
                    mime_type=file_info.mime_type,
                ),
                custom_prompt,
            ],
        )

        if response.text is None:
            raise ValueError("No text returned from Gemini")

        return ExtractionOutput(
            is_passthrough=False,
            content=response.text,
            content_format=self.config.output_format,
        )
