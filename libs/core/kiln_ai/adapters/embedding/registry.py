from kiln_ai.adapters.embedding.base_embedding_adapter import BaseEmbeddingAdapter
from kiln_ai.adapters.embedding.litellm_embedding_adapter import LitellmEmbeddingAdapter
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.datamodel.embedding import EmbeddingConfig
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error


def embedding_adapter_from_type(
    embedding_type: ModelProviderName,
    embedding_config: EmbeddingConfig,
) -> BaseEmbeddingAdapter:
    # FIXME: fix this before review; and integrate changes from this PR:
    # - https://github.com/Kiln-AI/Kiln/pull/390
    match embedding_type:
        case ModelProviderName.openrouter:
            return LitellmEmbeddingAdapter(embedding_config)
        case ModelProviderName.openai:
            return LitellmEmbeddingAdapter(embedding_config)
        case ModelProviderName.openai_compatible:
            return LitellmEmbeddingAdapter(embedding_config)
        case ModelProviderName.anthropic:
            return LitellmEmbeddingAdapter(embedding_config)
        case ModelProviderName.gemini_api:
            return LitellmEmbeddingAdapter(embedding_config)
        case ModelProviderName.huggingface:
            return LitellmEmbeddingAdapter(embedding_config)
        case ModelProviderName.vertex:
            return LitellmEmbeddingAdapter(embedding_config)
        case ModelProviderName.kiln_fine_tune:
            return LitellmEmbeddingAdapter(embedding_config)
        case ModelProviderName.kiln_custom_registry:
            return LitellmEmbeddingAdapter(embedding_config)
        case ModelProviderName.amazon_bedrock:
            return LitellmEmbeddingAdapter(embedding_config)
        case ModelProviderName.ollama:
            return LitellmEmbeddingAdapter(embedding_config)
        case ModelProviderName.fireworks_ai:
            return LitellmEmbeddingAdapter(embedding_config)
        case ModelProviderName.azure_openai:
            return LitellmEmbeddingAdapter(embedding_config)
        case ModelProviderName.together_ai:
            return LitellmEmbeddingAdapter(embedding_config)
        case ModelProviderName.groq:
            return LitellmEmbeddingAdapter(embedding_config)
        case _:
            # type checking will catch missing cases
            raise_exhaustive_enum_error(embedding_type)
