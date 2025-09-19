import hashlib
import logging
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
from kiln_ai.adapters.provider_tools import LiteLlmCoreConfig
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.datamodel.extraction import ExtractorConfig, ExtractorType, Kind
from kiln_ai.utils.filesystem_cache import FilesystemCache
from kiln_ai.utils.litellm import get_litellm_provider_info
from kiln_ai.utils.pdf_utils import split_pdf_into_pages

logger = logging.getLogger(__name__)

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


def encode_file_litellm_format(path: Path, mime_type: str) -> dict[str, Any]:
    # There are different formats that LiteLLM supports, the docs are scattered
    # and incomplete:
    # - https://docs.litellm.ai/docs/completion/document_understanding#base64
    # - https://docs.litellm.ai/docs/completion/vision#explicitly-specify-image-type

    # this is the most generic format that seems to work for all / most mime types
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

    # image has its own format (but also appears to work with the file format)
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
    def __init__(
        self,
        extractor_config: ExtractorConfig,
        litellm_core_config: LiteLlmCoreConfig,
        filesystem_cache: FilesystemCache | None = None,
    ):
        if extractor_config.extractor_type != ExtractorType.LITELLM:
            raise ValueError(
                f"LitellmExtractor must be initialized with a litellm extractor_type config. Got {extractor_config.extractor_type}"
            )

        prompt_document = extractor_config.prompt_document()
        if prompt_document is None or prompt_document == "":
            raise ValueError(
                "properties.prompt_document is required for LitellmExtractor"
            )
        prompt_video = extractor_config.prompt_video()
        if prompt_video is None or prompt_video == "":
            raise ValueError("properties.prompt_video is required for LitellmExtractor")
        prompt_audio = extractor_config.prompt_audio()
        if prompt_audio is None or prompt_audio == "":
            raise ValueError("properties.prompt_audio is required for LitellmExtractor")
        prompt_image = extractor_config.prompt_image()
        if prompt_image is None or prompt_image == "":
            raise ValueError("properties.prompt_image is required for LitellmExtractor")

        self.filesystem_cache = filesystem_cache

        super().__init__(extractor_config)
        self.prompt_for_kind = {
            Kind.DOCUMENT: prompt_document,
            Kind.VIDEO: prompt_video,
            Kind.AUDIO: prompt_audio,
            Kind.IMAGE: prompt_image,
        }

        self.litellm_core_config = litellm_core_config

    def pdf_page_cache_key(self, pdf_path: Path, page_number: int) -> str:
        if self.extractor_config.id is None:
            raise ValueError("Extractor config ID is required for PDF page cache key")

        return (
            self.extractor_config.id
            + "_"
            + hashlib.md5(f"{pdf_path.name}_{page_number}".encode("utf-8")).hexdigest()
        )

    def get_page_content_from_cache(
        self, pdf_path: Path, page_number: int
    ) -> str | None:
        if self.filesystem_cache is None:
            return None

        page_bytes = self.filesystem_cache.get(
            self.pdf_page_cache_key(pdf_path, page_number)
        )

        if page_bytes is not None:
            logger.debug(f"Cache hit for page {page_number} of {pdf_path}")
            content = page_bytes.decode("utf-8")
            return content

        logger.debug(f"Cache miss for page {page_number} of {pdf_path}")
        return None

    async def _extract_from_pdf_pages(self, pdf_path: Path, prompt: str) -> str:
        combined_content = []

        async with split_pdf_into_pages(pdf_path) as page_paths:
            # we extract from each page individually and then combine the results
            # this ensures the model stays focused on the current page and does not
            # start summarizing the later pages
            for i, page_path in enumerate(page_paths):
                try:
                    page_content = self.get_page_content_from_cache(pdf_path, i)
                    if page_content is not None:
                        combined_content.append(page_content)
                        continue

                    page_input = ExtractionInput(
                        path=str(page_path), mime_type="application/pdf"
                    )
                    completion_kwargs = self._build_completion_kwargs(
                        prompt, page_input
                    )
                    response = await litellm.acompletion(**completion_kwargs)
                except Exception as e:
                    raise RuntimeError(
                        f"Error extracting page {i + 1} in file {pdf_path}: {e}"
                    ) from e

                if (
                    not isinstance(response, ModelResponse)
                    or not response.choices
                    or len(response.choices) == 0
                    or not isinstance(response.choices[0], Choices)
                ):
                    raise RuntimeError(
                        f"Expected ModelResponse with Choices for page {i + 1}, got {type(response)}."
                    )

                if response.choices[0].message.content is None:
                    raise ValueError(
                        f"No text returned from LiteLLM when extracting page {i + 1}"
                    )

                content = response.choices[0].message.content
                if not content:
                    raise ValueError(
                        f"No text returned from extraction model when extracting page {i + 1} for {pdf_path}"
                    )

                if self.filesystem_cache is not None:
                    logger.debug(f"Caching page {i + 1} of {pdf_path} in cache")
                    self.filesystem_cache.set(
                        self.pdf_page_cache_key(pdf_path, i), content.encode("utf-8")
                    )

                combined_content.append(content)

        return "\n\n".join(combined_content)

    def _get_kind_from_mime_type(self, mime_type: str) -> Kind | None:
        for kind, mime_types in MIME_TYPES_SUPPORTED.items():
            if mime_type in mime_types:
                return kind
        return None

    def _build_completion_kwargs(
        self, prompt: str, extraction_input: ExtractionInput
    ) -> dict[str, Any]:
        completion_kwargs = {
            "model": self.litellm_model_slug(),
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        encode_file_litellm_format(
                            Path(extraction_input.path), extraction_input.mime_type
                        ),
                    ],
                }
            ],
            "temperature": 0.8,
        }

        if self.litellm_core_config.base_url:
            completion_kwargs["base_url"] = self.litellm_core_config.base_url

        if self.litellm_core_config.default_headers:
            completion_kwargs["default_headers"] = (
                self.litellm_core_config.default_headers
            )

        if self.litellm_core_config.additional_body_options:
            completion_kwargs.update(self.litellm_core_config.additional_body_options)

        return completion_kwargs

    async def _extract(self, extraction_input: ExtractionInput) -> ExtractionOutput:
        kind = self._get_kind_from_mime_type(extraction_input.mime_type)
        if kind is None:
            raise ValueError(
                f"Unsupported MIME type: {extraction_input.mime_type} for {extraction_input.path}"
            )

        prompt = self.prompt_for_kind.get(kind)
        if prompt is None:
            raise ValueError(f"No prompt found for kind: {kind}")

        # special handling for PDFs - process each page individually
        if extraction_input.mime_type == "application/pdf":
            content = await self._extract_from_pdf_pages(
                Path(extraction_input.path), prompt
            )
            return ExtractionOutput(
                is_passthrough=False,
                content=content,
                content_format=self.extractor_config.output_format,
            )

        completion_kwargs = self._build_completion_kwargs(prompt, extraction_input)

        response = await litellm.acompletion(**completion_kwargs)

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
            raise ValueError("No text returned from LiteLLM when extracting document")

        return ExtractionOutput(
            is_passthrough=False,
            content=response.choices[0].message.content,
            content_format=self.extractor_config.output_format,
        )

    def litellm_model_slug(self) -> str:
        kiln_model_provider = built_in_models_from_provider(
            ModelProviderName(self.extractor_config.model_provider_name),
            self.extractor_config.model_name,
        )

        if kiln_model_provider is None:
            raise ValueError(
                f"Model provider {self.extractor_config.model_provider_name} not found in the list of built-in models"
            )

        # need to translate into LiteLLM model slug
        litellm_provider_name = get_litellm_provider_info(
            kiln_model_provider,
        )

        return litellm_provider_name.litellm_model_id
