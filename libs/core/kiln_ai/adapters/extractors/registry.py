from kiln_ai.adapters.extractors.base_extractor import BaseExtractor
from kiln_ai.adapters.extractors.litellm_extractor import LitellmExtractor
from kiln_ai.adapters.ml_model_list import ModelProviderName
from kiln_ai.adapters.provider_tools import core_provider, get_provider_auth_details
from kiln_ai.datamodel.extraction import ExtractorConfig, ExtractorType
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error


def extractor_adapter_from_type(
    extractor_type: ExtractorType,
    extractor_config: ExtractorConfig,
) -> BaseExtractor:
    match extractor_type:
        case ExtractorType.LITELLM:
            provider_enum = ModelProviderName(extractor_config.model_provider_name)
            core_provider_name = core_provider(
                extractor_config.model_name, provider_enum
            )

            return LitellmExtractor(
                extractor_config, get_provider_auth_details(core_provider_name)
            )
        case _:
            # type checking will catch missing cases
            raise_exhaustive_enum_error(extractor_type)
