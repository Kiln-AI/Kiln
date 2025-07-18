from kiln_ai.adapters.extractors.base_extractor import BaseExtractor
from kiln_ai.adapters.extractors.litellm_extractor import LitellmExtractor
from kiln_ai.datamodel.extraction import ExtractorConfig, ExtractorType
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error


def extractor_adapter_from_type(
    extractor_type: ExtractorType,
    extractor_config: ExtractorConfig,
) -> BaseExtractor:
    match extractor_type:
        case ExtractorType.LITELLM:
            return LitellmExtractor(extractor_config)
        case _:
            # type checking will catch missing cases
            raise_exhaustive_enum_error(extractor_type)
