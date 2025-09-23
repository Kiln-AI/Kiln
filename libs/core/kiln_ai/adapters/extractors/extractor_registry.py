from kiln_ai.adapters.extractors.base_extractor import BaseExtractor
from kiln_ai.adapters.extractors.litellm_extractor import LitellmExtractor
from kiln_ai.adapters.extractors.mistralocr_extractor import MistralOcrExtractor
from kiln_ai.adapters.ml_model_list import ModelProviderName
from kiln_ai.adapters.provider_tools import (
    core_provider,
    lite_llm_core_config_for_provider,
)
from kiln_ai.datamodel.extraction import ExtractorConfig, ExtractorType
from kiln_ai.utils.config import Config
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error
from kiln_ai.utils.filesystem_cache import FilesystemCache


def extractor_adapter_from_type(
    extractor_type: ExtractorType,
    extractor_config: ExtractorConfig,
    filesystem_cache: FilesystemCache | None = None,
) -> BaseExtractor:
    match extractor_type:
        case ExtractorType.LITELLM:
            try:
                provider_enum = ModelProviderName(extractor_config.model_provider_name)
            except ValueError:
                raise ValueError(
                    f"Unsupported model provider name: {extractor_config.model_provider_name}. "
                )

            core_provider_name = core_provider(
                extractor_config.model_name, provider_enum
            )

            provider_config = lite_llm_core_config_for_provider(core_provider_name)
            if provider_config is None:
                raise ValueError(
                    f"No configuration found for core provider: {core_provider_name.value}. "
                )

            return LitellmExtractor(
                extractor_config,
                provider_config,
                filesystem_cache,
            )
        case ExtractorType.MISTRAL_OCR:
            return MistralOcrExtractor(
                Config.shared().mistral_api_key,
                extractor_config,
            )
        case _:
            # type checking will catch missing cases
            raise_exhaustive_enum_error(extractor_type)
