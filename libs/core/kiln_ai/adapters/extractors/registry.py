from kiln_ai.adapters.extractors.base_extractor import BaseExtractor
from kiln_ai.adapters.extractors.gemini_extractor import GeminiExtractor
from kiln_ai.datamodel.extraction import ExtractorType
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error


def extractor_adapter_from_type(
    extractor_config_type: ExtractorType,
) -> type[BaseExtractor]:
    match extractor_config_type:
        case ExtractorType.gemini:
            return GeminiExtractor
        case _:
            # type checking will catch missing cases
            raise_exhaustive_enum_error(extractor_config_type)
