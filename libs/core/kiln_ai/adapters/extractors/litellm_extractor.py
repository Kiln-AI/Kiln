import asyncio
import hashlib
import logging
from functools import cached_property
from pathlib import Path
from typing import Any, List

import litellm
from litellm.types.utils import Choices, ModelResponse

from kiln_ai.adapters.extractors.base_extractor import (
    BaseExtractor,
    ExtractionInput,
    ExtractionOutput,
)
from kiln_ai.adapters.extractors.encoding import to_base64_url
from kiln_ai.adapters.ml_model_list import (
    KilnModelProvider,
    built_in_models_from_provider,
)
from kiln_ai.adapters.provider_tools import LiteLlmCoreConfig
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.datamodel.extraction import ExtractorConfig, ExtractorType, Kind
from kiln_ai.utils.filesystem_cache import FilesystemCache
from kiln_ai.utils.litellm import get_litellm_provider_info
from kiln_ai.utils.pdf_utils import convert_pdf_to_images, split_pdf_into_pages

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
        file_bytes = path.read_bytes()
        return {
            "type": "file",
            "file": {
                "file_data": to_base64_url(mime_type, file_bytes),
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
        default_max_parallel_requests: int = 5,
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
        self.default_max_parallel_requests = default_max_parallel_requests

    def pdf_page_cache_key(self, pdf_path: Path, page_number: int) -> str:
        """
        Generate a cache key for a page of a PDF. The PDF path must be the full path to the PDF file,
        not the path to the page - since page path is temporary and changes on each run.
        """
        if self.extractor_config.id is None:
            raise ValueError("Extractor config ID is required for PDF page cache key")

        raw_key = f"{pdf_path.resolve()}::{page_number}"
        digest = hashlib.md5(raw_key.encode("utf-8")).hexdigest()
        return f"{self.extractor_config.id}_{digest}"

    async def get_page_content_from_cache(
        self, pdf_path: Path, page_number: int
    ) -> str | None:
        if self.filesystem_cache is None:
            return None

        page_bytes = await self.filesystem_cache.get(
            self.pdf_page_cache_key(pdf_path, page_number)
        )

        if page_bytes is not None:
            logger.debug(f"Cache hit for page {page_number} of {pdf_path}")
            try:
                return page_bytes.decode("utf-8")
            except UnicodeDecodeError:
                logger.warning(
                    "Cached bytes for page %s of %s are not valid UTF-8; treating as miss.",
                    page_number,
                    pdf_path,
                    exc_info=True,
                )

        logger.debug(f"Cache miss for page {page_number} of {pdf_path}")
        return None

    async def convert_pdf_page_to_image_input(
        self, page_path: Path, page_number: int
    ) -> ExtractionInput:
        image_paths = await convert_pdf_to_images(page_path, page_path.parent)
        if len(image_paths) != 1:
            raise ValueError(
                f"Expected 1 image, got {len(image_paths)} for page {page_number} in {page_path}"
            )
        image_path = image_paths[0]
        page_input = ExtractionInput(path=str(image_path), mime_type="image/png")
        return page_input

    async def _extract_single_pdf_page(
        self,
        pdf_path: Path,
        page_path: Path,
        prompt: str,
        page_number: int,
    ) -> str:
        try:
            if self.model_provider.multimodal_requires_pdf_as_image:
                page_input = await self.convert_pdf_page_to_image_input(
                    page_path, page_number
                )
            else:
                page_input = ExtractionInput(
                    path=str(page_path), mime_type="application/pdf"
                )

            completion_kwargs = self._build_completion_kwargs(prompt, page_input)
            response = await litellm.acompletion(**completion_kwargs)
        except Exception as e:
            raise RuntimeError(
                f"Error extracting page {page_number} in file {page_path}: {e}"
            ) from e

        if (
            not isinstance(response, ModelResponse)
            or not response.choices
            or len(response.choices) == 0
            or not isinstance(response.choices[0], Choices)
        ):
            raise RuntimeError(
                f"Expected ModelResponse with Choices for page {page_number}, got {type(response)}."
            )

        if response.choices[0].message.content is None:
            raise ValueError(
                f"No text returned from LiteLLM when extracting page {page_number}"
            )

        content = response.choices[0].message.content
        if self.filesystem_cache is not None:
            # we don't want to fail the whole extraction just because cache write fails
            # as that would block the whole flow
            try:
                logger.debug(f"Caching page {page_number} of {page_path} in cache")
                await self.filesystem_cache.set(
                    self.pdf_page_cache_key(pdf_path, page_number),
                    content.encode("utf-8"),
                )
            except Exception:
                logger.warning(
                    "Failed to cache page %s of %s; continuing without cache.",
                    page_number,
                    page_path,
                    exc_info=True,
                )

        return content

    async def _extract_pdf_page_by_page(self, pdf_path: Path, prompt: str) -> str:
        async with split_pdf_into_pages(pdf_path) as page_paths:
            page_outcomes: List[str | Exception | None] = [None] * len(page_paths)

            extract_page_jobs: list = []
            page_indices_for_jobs: list = []  # Track which page index each job corresponds to

            # we extract from each page individually and then combine the results
            # this ensures the model stays focused on the current page and does not
            # start summarizing the later pages
            for i, page_path in enumerate(page_paths):
                page_content = await self.get_page_content_from_cache(pdf_path, i)
                if page_content is not None:
                    page_outcomes[i] = page_content
                    continue

                extract_page_jobs.append(
                    self._extract_single_pdf_page(
                        pdf_path, page_path, prompt, page_number=i
                    )
                )
                page_indices_for_jobs.append(i)

                if (
                    len(extract_page_jobs) >= self.max_parallel_requests_for_model
                    or i == len(page_paths) - 1
                ):
                    extraction_results = await asyncio.gather(
                        *extract_page_jobs, return_exceptions=True
                    )

                    for batch_i, extraction_result in enumerate(extraction_results):
                        page_index = page_indices_for_jobs[batch_i]
                        # we let it continue even if there is an error - the success results will be cached
                        # and can be reused on the next run
                        if isinstance(extraction_result, Exception):
                            page_outcomes[page_index] = extraction_result
                        elif isinstance(extraction_result, str):
                            page_outcomes[page_index] = extraction_result
                        else:
                            raise ValueError(
                                f"Unexpected type {type(extraction_result)} for page {page_index}"
                            )
                    extract_page_jobs.clear()
                    page_indices_for_jobs.clear()

        exceptions: list[tuple[int, Exception]] = [
            (page_index, result)
            for page_index, result in enumerate(page_outcomes)
            if isinstance(result, Exception)
        ]
        if len(exceptions) > 0:
            msg = f"Error extracting PDF {pdf_path}: "
            for page_index, exception in exceptions:
                msg += f"Page {page_index}: {exception}\n"
            raise RuntimeError(msg)

        return "\n\n".join(
            [outcome for outcome in page_outcomes if isinstance(outcome, str)]
        )

    def _get_kind_from_mime_type(self, mime_type: str) -> Kind | None:
        for kind, mime_types in MIME_TYPES_SUPPORTED.items():
            if mime_type in mime_types:
                return kind
        return None

    def _build_completion_kwargs(
        self, prompt: str, extraction_input: ExtractionInput
    ) -> dict[str, Any]:
        completion_kwargs = {
            "model": self.litellm_model_slug,
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
            content = await self._extract_pdf_page_by_page(
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

    @cached_property
    def model_provider(self) -> KilnModelProvider:
        kiln_model_provider = built_in_models_from_provider(
            ModelProviderName(self.extractor_config.model_provider_name),
            self.extractor_config.model_name,
        )
        if kiln_model_provider is None:
            raise ValueError(
                f"Model provider {self.extractor_config.model_provider_name} not found in the list of built-in models"
            )
        return kiln_model_provider

    @cached_property
    def max_parallel_requests_for_model(self) -> int:
        value = self.model_provider.max_parallel_requests
        return value if value is not None else self.default_max_parallel_requests

    @cached_property
    def litellm_model_slug(self) -> str:
        litellm_provider_name = get_litellm_provider_info(
            self.model_provider,
        )
        return litellm_provider_name.litellm_model_id
