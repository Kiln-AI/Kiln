import base64
from functools import cached_property
from pathlib import Path
from typing import Literal, TypedDict

from mistralai import DocumentTypedDict, Mistral

from kiln_ai.adapters.extractor_list import built_in_extractors_from_provider
from kiln_ai.adapters.extractors.base_extractor import (
    BaseExtractor,
    ExtractionInput,
    ExtractionOutput,
)
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.datamodel.extraction import ExtractorConfig, ExtractorType, OutputFormat


class MistralOcrPdfEncoded(TypedDict):
    type: Literal["document_url"]
    document_url: str


class MistralOcrImageEncoded(TypedDict):
    type: Literal["image_url"]
    image_url: str


def encode_pdf_for_mistral_ocr(pdf_path: Path) -> DocumentTypedDict:
    """Encode the pdf to base64."""
    with open(pdf_path, "rb") as pdf_file:
        base64_pdf = base64.b64encode(pdf_file.read()).decode("utf-8")
        return {
            "type": "document_url",
            "document_url": f"data:application/pdf;base64,{base64_pdf}",
        }


def encode_image_for_mistral_ocr(image_path: Path) -> DocumentTypedDict:
    """Encode the image to base64."""
    with open(image_path, "rb") as image_file:
        base64_image = base64.b64encode(image_file.read()).decode("utf-8")
        return {
            "type": "image_url",
            "image_url": f"data:image/jpeg;base64,{base64_image}",
        }


def encode_file_for_mistral_ocr(
    extraction_input: ExtractionInput,
) -> DocumentTypedDict:
    if extraction_input.mime_type == "application/pdf":
        return encode_pdf_for_mistral_ocr(Path(extraction_input.path))
    elif extraction_input.mime_type == "image/jpeg":
        return encode_image_for_mistral_ocr(Path(extraction_input.path))
    else:
        raise ValueError(f"Unsupported MIME type: {extraction_input.mime_type}")


# https://docs.litellm.ai/docs/pass_through/mistral
class MistralOcrExtractor(BaseExtractor):
    def __init__(self, mistral_api_key: str, extractor_config: ExtractorConfig):
        if extractor_config.extractor_type != ExtractorType.MISTRAL_OCR:
            raise ValueError(
                f"MistralOcrExtractor must be initialized with a mistral-ocr extractor_type config. Got {extractor_config.extractor_type}"
            )

        self.mistral_api_key = mistral_api_key
        self.client = Mistral(api_key=self.mistral_api_key)
        super().__init__(extractor_config)

    async def _extract(self, extraction_input: ExtractionInput) -> ExtractionOutput:
        # TODO: extract images and transcribe them individually with the OCR again?
        ocr_response = await self.client.ocr.process_async(
            model=self.model_name,
            document=encode_file_for_mistral_ocr(extraction_input),
            include_image_base64=False,
        )

        if ocr_response.pages is None:
            raise ValueError("No pages returned from Mistral OCR")

        pages_text = "\n\n".join([page.markdown for page in ocr_response.pages])

        return ExtractionOutput(
            is_passthrough=False,
            content=pages_text,
            content_format=OutputFormat.MARKDOWN,
        )

    @cached_property
    def model_name(self) -> str:
        extractor = built_in_extractors_from_provider(
            provider_name=ModelProviderName.mistral,
            extractor_name=self.extractor_config.model_name,
        )
        if extractor is None:
            raise ValueError(f"Extractor {self.extractor_config.model_name} not found")

        return extractor.extractor_id
