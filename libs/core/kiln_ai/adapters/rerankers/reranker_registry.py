from kiln_ai.adapters.provider_tools import lite_llm_core_config_for_provider
from kiln_ai.adapters.rerankers.base_reranker import BaseReranker
from kiln_ai.adapters.rerankers.litellm_reranker_adapter import LitellmRerankerAdapter
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.datamodel.reranker import RerankerConfig, RerankerType
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error


def reranker_adapter_from_config(
    reranker_config: RerankerConfig,
) -> BaseReranker:
    match reranker_config.properties["type"]:
        case RerankerType.COHERE_COMPATIBLE:
            litellm_provider_config = lite_llm_core_config_for_provider(
                ModelProviderName(reranker_config.model_provider_name)
            )
            if litellm_provider_config is None:
                raise ValueError(
                    f"No configuration found for core provider: {reranker_config.model_provider_name}. "
                )
            return LitellmRerankerAdapter(
                reranker_config,
                litellm_provider_config,
            )
        case _:
            raise_exhaustive_enum_error(reranker_config.properties["type"])
