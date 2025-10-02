from enum import Enum
from typing import List

from pydantic import BaseModel

from kiln_ai.datamodel.datamodel_enums import KilnMimeType, ModelProviderName
from kiln_ai.datamodel.extraction import ExtractorType


class ExtractorProviderName(str, Enum):
    mistral = "mistral"


class ExtractorFamily(str, Enum):
    mistral = "mistral"
    gemini = "gemini"
    gpt = "gpt"


class ExtractorName(str, Enum):
    gemini_2_5_pro = "gemini_2_5_pro"
    gemini_2_5_flash = "gemini_2_5_flash"
    gemini_2_0_flash = "gemini_2_0_flash"
    gemini_2_0_flash_lite = "gemini_2_0_flash_lite"
    gpt_5 = "gpt_5"
    gpt_5_mini = "gpt_5_mini"
    gpt_5_nano = "gpt_5_nano"
    gpt_4_1 = "gpt_4_1"
    mistral_ocr = "mistral_ocr"


class KilnExtractorProvider(BaseModel):
    name: str
    extractor_type: ExtractorType
    extractor_id: str
    supported_mime_types: List[str] | None = None


class KilnExtractor(BaseModel):
    name: ExtractorName
    family: ExtractorFamily
    friendly_name: str
    providers: List[KilnExtractorProvider]


# Static copy of all model-backed extractors (supports_doc_extraction=True in model list)
built_in_extractors: List[KilnExtractor] = [
    KilnExtractor(
        name=ExtractorName.gpt_5,
        family=ExtractorFamily.gpt,
        friendly_name="GPT-5",
        providers=[
            KilnExtractorProvider(
                name=ModelProviderName.openai,
                extractor_type=ExtractorType.LITELLM,
                extractor_id="gpt-5",
                supported_mime_types=[
                    # documents
                    KilnMimeType.PDF,
                    # images
                    KilnMimeType.JPG,
                    KilnMimeType.PNG,
                ],
            ),
            KilnExtractorProvider(
                name=ModelProviderName.openrouter,
                extractor_type=ExtractorType.LITELLM,
                extractor_id="openai/gpt-5",
                supported_mime_types=[
                    # documents
                    KilnMimeType.PDF,
                    # images
                    KilnMimeType.JPG,
                    KilnMimeType.PNG,
                ],
            ),
        ],
    ),
    KilnExtractor(
        name=ExtractorName.gpt_5_mini,
        family=ExtractorFamily.gpt,
        friendly_name="GPT-5 Mini",
        providers=[
            KilnExtractorProvider(
                name=ModelProviderName.openai,
                extractor_type=ExtractorType.LITELLM,
                extractor_id="gpt-5-mini",
                supported_mime_types=[
                    # documents
                    KilnMimeType.PDF,
                    # images
                    KilnMimeType.JPG,
                    KilnMimeType.PNG,
                ],
            ),
            KilnExtractorProvider(
                name=ModelProviderName.openrouter,
                extractor_type=ExtractorType.LITELLM,
                extractor_id="openai/gpt-5-mini",
                supported_mime_types=[
                    # documents
                    KilnMimeType.PDF,
                    # images
                    KilnMimeType.JPG,
                    KilnMimeType.PNG,
                ],
            ),
        ],
    ),
    KilnExtractor(
        name=ExtractorName.gpt_5_nano,
        family=ExtractorFamily.gpt,
        friendly_name="GPT-5 Nano",
        providers=[
            KilnExtractorProvider(
                name=ModelProviderName.openai,
                extractor_type=ExtractorType.LITELLM,
                extractor_id="gpt-5-nano",
                supported_mime_types=[
                    # documents
                    KilnMimeType.PDF,
                    # images
                    KilnMimeType.JPG,
                    KilnMimeType.PNG,
                ],
            ),
            KilnExtractorProvider(
                name=ModelProviderName.openrouter,
                extractor_type=ExtractorType.LITELLM,
                extractor_id="openai/gpt-5-nano",
                supported_mime_types=[
                    # documents
                    KilnMimeType.PDF,
                    # images
                    KilnMimeType.JPG,
                    KilnMimeType.PNG,
                ],
            ),
        ],
    ),
    KilnExtractor(
        name=ExtractorName.gpt_4_1,
        family=ExtractorFamily.gpt,
        friendly_name="GPT 4.1",
        providers=[
            KilnExtractorProvider(
                name=ModelProviderName.openai,
                extractor_type=ExtractorType.LITELLM,
                extractor_id="gpt-4.1",
                supported_mime_types=[
                    # documents
                    KilnMimeType.PDF,
                    # images
                    KilnMimeType.JPG,
                    KilnMimeType.PNG,
                ],
            ),
            KilnExtractorProvider(
                name=ModelProviderName.openrouter,
                extractor_type=ExtractorType.LITELLM,
                extractor_id="openai/gpt-4.1",
                supported_mime_types=[
                    # documents
                    KilnMimeType.PDF,
                    # images
                    KilnMimeType.JPG,
                    KilnMimeType.PNG,
                ],
            ),
        ],
    ),
    KilnExtractor(
        name=ExtractorName.gemini_2_5_pro,
        family=ExtractorFamily.gemini,
        friendly_name="Gemini 2.5 Pro",
        providers=[
            KilnExtractorProvider(
                name=ModelProviderName.openrouter,
                extractor_type=ExtractorType.LITELLM,
                extractor_id="google/gemini-2.5-pro",
                supported_mime_types=[
                    # documents
                    KilnMimeType.PDF,
                    KilnMimeType.CSV,
                    KilnMimeType.TXT,
                    KilnMimeType.HTML,
                    KilnMimeType.MD,
                    # images
                    KilnMimeType.JPG,
                    KilnMimeType.PNG,
                ],
            ),
            KilnExtractorProvider(
                name=ModelProviderName.gemini_api,
                extractor_type=ExtractorType.LITELLM,
                extractor_id="gemini-2.5-pro",
                supported_mime_types=[
                    # documents
                    KilnMimeType.PDF,
                    KilnMimeType.CSV,
                    KilnMimeType.TXT,
                    KilnMimeType.HTML,
                    KilnMimeType.MD,
                    # images
                    KilnMimeType.JPG,
                    KilnMimeType.PNG,
                    # audio
                    KilnMimeType.MP3,
                    KilnMimeType.WAV,
                    KilnMimeType.OGG,
                    # video
                    KilnMimeType.MP4,
                    KilnMimeType.MOV,
                ],
            ),
        ],
    ),
    KilnExtractor(
        name=ExtractorName.gemini_2_5_flash,
        family=ExtractorFamily.gemini,
        friendly_name="Gemini 2.5 Flash",
        providers=[
            KilnExtractorProvider(
                name=ModelProviderName.openrouter,
                extractor_type=ExtractorType.LITELLM,
                extractor_id="google/gemini-2.5-flash",
                supported_mime_types=[
                    # documents
                    KilnMimeType.PDF,
                    KilnMimeType.CSV,
                    KilnMimeType.TXT,
                    KilnMimeType.HTML,
                    KilnMimeType.MD,
                    # images
                    KilnMimeType.JPG,
                    KilnMimeType.PNG,
                ],
            ),
            KilnExtractorProvider(
                name=ModelProviderName.gemini_api,
                extractor_type=ExtractorType.LITELLM,
                extractor_id="gemini-2.5-flash",
                supported_mime_types=[
                    # documents
                    KilnMimeType.PDF,
                    KilnMimeType.CSV,
                    KilnMimeType.TXT,
                    KilnMimeType.HTML,
                    KilnMimeType.MD,
                    # images
                    KilnMimeType.JPG,
                    KilnMimeType.PNG,
                    # audio
                    KilnMimeType.MP3,
                    KilnMimeType.WAV,
                    KilnMimeType.OGG,
                    # video
                    KilnMimeType.MP4,
                    KilnMimeType.MOV,
                ],
            ),
        ],
    ),
    KilnExtractor(
        name=ExtractorName.gemini_2_0_flash,
        family=ExtractorFamily.gemini,
        friendly_name="Gemini 2.0 Flash",
        providers=[
            KilnExtractorProvider(
                name=ModelProviderName.openrouter,
                extractor_type=ExtractorType.LITELLM,
                extractor_id="google/gemini-2.0-flash-001",
                supported_mime_types=[
                    # documents
                    KilnMimeType.PDF,
                    KilnMimeType.CSV,
                    KilnMimeType.TXT,
                    KilnMimeType.HTML,
                    KilnMimeType.MD,
                    # images
                    KilnMimeType.JPG,
                    KilnMimeType.PNG,
                ],
            ),
            KilnExtractorProvider(
                name="ModelProviderName.gemini_api",
                extractor_type=ExtractorType.LITELLM,
                extractor_id="gemini-2.0-flash",
                supported_mime_types=[
                    # documents
                    KilnMimeType.PDF,
                    KilnMimeType.CSV,
                    KilnMimeType.TXT,
                    KilnMimeType.HTML,
                    KilnMimeType.MD,
                    # images
                    KilnMimeType.JPG,
                    KilnMimeType.PNG,
                    # audio
                    KilnMimeType.MP3,
                    KilnMimeType.WAV,
                    KilnMimeType.OGG,
                    # video
                    KilnMimeType.MP4,
                    KilnMimeType.MOV,
                ],
            ),
        ],
    ),
    KilnExtractor(
        name=ExtractorName.gemini_2_0_flash_lite,
        family=ExtractorFamily.gemini,
        friendly_name="Gemini 2.0 Flash Lite",
        providers=[
            KilnExtractorProvider(
                name=ModelProviderName.openrouter,
                extractor_type=ExtractorType.LITELLM,
                extractor_id="google/gemini-2.0-flash-lite-001",
                supported_mime_types=[
                    # documents
                    KilnMimeType.PDF,
                    KilnMimeType.CSV,
                    KilnMimeType.TXT,
                    KilnMimeType.HTML,
                    KilnMimeType.MD,
                    # images
                    KilnMimeType.JPG,
                    KilnMimeType.PNG,
                ],
            ),
            KilnExtractorProvider(
                name="ModelProviderName.gemini_api",
                extractor_type=ExtractorType.LITELLM,
                extractor_id="gemini-2.0-flash-lite",
                supported_mime_types=[
                    # documents
                    KilnMimeType.PDF,
                    KilnMimeType.CSV,
                    KilnMimeType.TXT,
                    KilnMimeType.HTML,
                    KilnMimeType.MD,
                    # images
                    KilnMimeType.JPG,
                    KilnMimeType.PNG,
                    # audio
                    KilnMimeType.MP3,
                    KilnMimeType.WAV,
                    KilnMimeType.OGG,
                    # video
                    KilnMimeType.MP4,
                    KilnMimeType.MOV,
                ],
            ),
        ],
    ),
    KilnExtractor(
        name=ExtractorName.mistral_ocr,
        family=ExtractorFamily.mistral,
        friendly_name="Mistral OCR",
        providers=[
            KilnExtractorProvider(
                name=ModelProviderName.mistral,
                extractor_type=ExtractorType.MISTRAL_OCR,
                extractor_id="mistral-ocr-latest",
                supported_mime_types=[
                    # documents
                    KilnMimeType.PDF,
                    # images
                    KilnMimeType.JPG,
                    KilnMimeType.PNG,
                ],
            ),
        ],
    ),
]


def built_in_extractors_from_provider(
    provider_name: ModelProviderName,
    extractor_name: str,
) -> KilnExtractorProvider | None:
    for extractor in built_in_extractors:
        if extractor.name == extractor_name:
            for provider in extractor.providers:
                if provider.name == provider_name:
                    return provider
    return None
