from kiln_ai.adapters.embedding.base_embedding_adapter import BaseEmbeddingAdapter
from kiln_ai.adapters.embedding.litellm_embedding_adapter import LitellmEmbeddingAdapter
from kiln_ai.adapters.provider_tools import (
    core_provider,
    lite_llm_core_config_for_provider,
)
from kiln_ai.datamodel.datamodel_enums import parse_model_provider_name
from kiln_ai.datamodel.embedding import EmbeddingConfig


def embedding_adapter_from_type(
    embedding_config: EmbeddingConfig,
) -> BaseEmbeddingAdapter:
    provider_enum = parse_model_provider_name(embedding_config.model_provider_name)
    core_provider_name = core_provider(embedding_config.model_name, provider_enum)

    provider_config = lite_llm_core_config_for_provider(core_provider_name)
    if provider_config is None:
        raise ValueError(
            f"No configuration found for core provider: {core_provider_name.value}. "
        )

    return LitellmEmbeddingAdapter(
        embedding_config,
        provider_config,
    )
