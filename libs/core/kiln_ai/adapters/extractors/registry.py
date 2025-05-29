from typing import Callable

from google import genai

from kiln_ai.adapters.extractors.base_extractor import BaseExtractor
from kiln_ai.adapters.extractors.gemini_extractor import GeminiExtractor
from kiln_ai.datamodel.extraction import ExtractorConfig, ExtractorType
from kiln_ai.utils.config import Config
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error


def extractor_adapter_from_type(
    extractor_type: ExtractorType,
) -> Callable[[ExtractorConfig], BaseExtractor] | type[BaseExtractor]:
    match extractor_type:
        case ExtractorType.gemini:
            # TODO: maybe make client global / singleton in GeminiExtractor instead of here
            client = genai.Client(api_key=Config.shared().gemini_api_key)
            return lambda extractor_config: GeminiExtractor(client, extractor_config)
        case _:
            # type checking will catch missing cases
            raise_exhaustive_enum_error(extractor_type)
