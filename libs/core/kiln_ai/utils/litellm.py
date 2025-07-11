from dataclasses import dataclass

from kiln_ai.adapters.ml_embedding_model_list import KilnEmbeddingModelProvider
from kiln_ai.adapters.ml_model_list import KilnModelProvider
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error


@dataclass
class LitellmProviderInfo:
    # The name of the provider, as it appears in litellm
    provider_name: str
    # Whether the provider is custom - e.g. custom models, ollama, fine tunes, and custom registry models
    is_custom: bool
    # The model ID slug to use in litellm
    litellm_model_id: str


def get_litellm_provider_info(
    model_provider: KilnEmbeddingModelProvider | KilnModelProvider,
) -> LitellmProviderInfo:
    """
    Maps a Kiln model provider to a litellm provider.

    Args:
        model_provider: The model provider to get litellm provider info for

    Returns:
        LitellmProviderInfo containing the provider name and whether it's custom
    """
    if not model_provider.model_id:
        raise ValueError("Model ID is required for OpenAI compatible models")

    litellm_provider_name: str | None = None
    is_custom = False
    match model_provider.name:
        case ModelProviderName.openrouter:
            litellm_provider_name = "openrouter"
        case ModelProviderName.openai:
            litellm_provider_name = "openai"
        case ModelProviderName.groq:
            litellm_provider_name = "groq"
        case ModelProviderName.anthropic:
            litellm_provider_name = "anthropic"
        case ModelProviderName.ollama:
            # We don't let litellm use the Ollama API and muck with our requests. We use Ollama's OpenAI compatible API.
            # This is because we're setting detailed features like response_format=json_schema and want lower level control.
            is_custom = True
        case ModelProviderName.gemini_api:
            litellm_provider_name = "gemini"
        case ModelProviderName.fireworks_ai:
            litellm_provider_name = "fireworks_ai"
        case ModelProviderName.amazon_bedrock:
            litellm_provider_name = "bedrock"
        case ModelProviderName.azure_openai:
            litellm_provider_name = "azure"
        case ModelProviderName.huggingface:
            litellm_provider_name = "huggingface"
        case ModelProviderName.vertex:
            litellm_provider_name = "vertex_ai"
        case ModelProviderName.together_ai:
            litellm_provider_name = "together_ai"
        case ModelProviderName.openai_compatible:
            is_custom = True
        case ModelProviderName.kiln_custom_registry:
            is_custom = True
        case ModelProviderName.kiln_fine_tune:
            is_custom = True
        case _:
            raise_exhaustive_enum_error(model_provider.name)

    if is_custom:
        # Use openai as it's only used for format, not url
        litellm_provider_name = "openai"

    # Shouldn't be possible but keep type checker happy
    if litellm_provider_name is None:
        raise ValueError(
            f"Provider name could not lookup valid litellm provider ID {model_provider.model_id}"
        )

    return LitellmProviderInfo(
        provider_name=litellm_provider_name,
        is_custom=is_custom,
        litellm_model_id=f"{litellm_provider_name}/{model_provider.model_id}",
    )
