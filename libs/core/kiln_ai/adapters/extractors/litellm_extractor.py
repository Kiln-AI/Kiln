from pathlib import Path
from typing import Any

import litellm
from litellm.types.utils import Choices, ModelResponse

from kiln_ai.adapters.extractors.base_extractor import (
    BaseExtractor,
    ExtractionInput,
    ExtractionOutput,
)
from kiln_ai.adapters.extractors.encoding import to_base64_url
from kiln_ai.adapters.ml_model_list import built_in_models_from_provider
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.datamodel.extraction import ExtractorConfig, ExtractorType, Kind
from kiln_ai.utils.config import Config
from kiln_ai.utils.litellm import get_litellm_provider_info

MIME_TYPES_SUPPORTED = {
    Kind.DOCUMENT: [
        "application/pdf",
        "text/plain",
        "text/markdown",  # not officially listed, but works
        "text/html",
        "text/md",
        "text/csv",
    ],
    Kind.IMAGE: [
        "image/png",
        "image/jpeg",
        "image/jpg",
    ],
    Kind.VIDEO: [
        "video/mp4",
        "video/mov",  # the correct type is video/quicktime, but Google lists it as video/mov
        "video/quicktime",
    ],
    Kind.AUDIO: [
        "audio/wav",
        "audio/mpeg",  # this is the official MP3 mimetype, audio/mp3 is often used but not correct
        "audio/ogg",
    ],
}


def encode_file(path: Path, mime_type: str) -> dict[str, Any]:
    if mime_type in [
        "application/pdf",
        "text/csv",
        "text/html",
        "text/markdown",
        "text/plain",
    ] or any(mime_type.startswith(m) for m in ["video/", "audio/"]):
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
    raise ValueError(f"Unsupported MIME type: {mime_type} for {path}")


class LitellmExtractor(BaseExtractor):
    def __init__(self, extractor_config: ExtractorConfig):
        if extractor_config.extractor_type != ExtractorType.LITELLM:
            raise ValueError(
                f"LitellmExtractor must be initialized with a litellm extractor_type config. Got {extractor_config.extractor_type}"
            )

        model_provider_name = extractor_config.model_provider_name()
        if model_provider_name is None:
            raise ValueError(
                "properties.model_provider_name is required for LitellmExtractor"
            )

        model_name = extractor_config.model_name()
        if model_name is None:
            raise ValueError("properties.model_name is required for GeminiExtractor")

        # TODO: some models supports only a few kinds - maybe drop Kind altogether
        # and deal with mimetype directly instead
        # can do the arbitrary kind-grouping at the UI and API level
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

    async def _extract(self, extraction_input: ExtractionInput) -> ExtractionOutput:
        kind = self._get_kind_from_mime_type(extraction_input.mime_type)
        if kind is None:
            raise ValueError(
                f"Unsupported MIME type: {extraction_input.mime_type} for {extraction_input.path}"
            )

        prompt = self.prompt_for_kind.get(kind)
        if prompt is None:
            raise ValueError(f"No prompt found for kind: {kind}")

        # FIXME: check modality support - maybe later
        # litellm.supports_vision(model=self.model_name)
        # litellm.supports_pdf_input(model=self.model_name)
        # litellm.supports_audio_input(model=self.model_name) # https://github.com/BerriAI/litellm/issues/6303

        response = await litellm.acompletion(
            model=self.litellm_model_slug(),
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        encode_file(
                            Path(extraction_input.path), extraction_input.mime_type
                        ),
                    ],
                }
            ],
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

    def litellm_model_slug(self) -> str:
        kiln_model_provider_name = self.extractor_config.model_provider_name()
        if kiln_model_provider_name is None:
            raise ValueError(
                "properties.model_provider_name is required for LitellmExtractor"
            )

        kiln_model_name = self.extractor_config.model_name()
        if kiln_model_provider_name is None or kiln_model_name is None:
            raise ValueError(
                "properties.model_provider_name and properties.model_name are required for LitellmExtractor"
            )

        kiln_model_provider = built_in_models_from_provider(
            ModelProviderName(kiln_model_provider_name), kiln_model_name
        )

        if kiln_model_provider is None:
            raise ValueError(
                f"Model provider {kiln_model_provider_name} not found in the list of built-in models"
            )

        # need to translate into LiteLLM model slug
        litellm_provider_name = get_litellm_provider_info(
            kiln_model_provider,
        )

        return litellm_provider_name.litellm_model_id
