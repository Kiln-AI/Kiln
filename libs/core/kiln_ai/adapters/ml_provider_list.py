"""Facts about each model provider, and the source of the friendly provider names.

The list is published in the remote config as `provider_list` for agents outside
Kiln. Kiln clients do not load it from the remote config; they use the copy here,
which ships with each release.
"""

from pydantic import BaseModel, Field

from kiln_ai.datamodel.datamodel_enums import ModelProviderName


class KilnProviderInfo(BaseModel):
    """
    Facts about one model provider.

    Attributes:
        id: Kiln's provider id.
        friendly_name: The provider name people see.
        notes: For an agent that chooses a provider: data retention, rate limits, routing and gotchas. None means no note. The rules are in kiln_ai.adapters.model_agent_info.
        tags: Labels code can filter on, from PROVIDER_LIST_TAGS in kiln_ai.adapters.model_agent_info.
        models_dev_id: The provider's key in models.dev (https://models.dev/api.json). None means models.dev has no entry for the provider, or the mapping is not checked.
    """

    id: ModelProviderName
    friendly_name: str
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)
    models_dev_id: str | None = None


built_in_providers: tuple[KilnProviderInfo, ...] = (
    KilnProviderInfo(
        id=ModelProviderName.openai,
        friendly_name="OpenAI",
        models_dev_id="openai",
    ),
    KilnProviderInfo(
        id=ModelProviderName.groq,
        friendly_name="Groq",
        models_dev_id="groq",
    ),
    KilnProviderInfo(
        id=ModelProviderName.amazon_bedrock,
        friendly_name="Amazon Bedrock",
        models_dev_id="amazon-bedrock",
    ),
    KilnProviderInfo(
        id=ModelProviderName.ollama,
        friendly_name="Ollama",
    ),
    KilnProviderInfo(
        id=ModelProviderName.openrouter,
        friendly_name="OpenRouter",
        models_dev_id="openrouter",
    ),
    KilnProviderInfo(
        id=ModelProviderName.fireworks_ai,
        friendly_name="Fireworks AI",
        models_dev_id="fireworks-ai",
    ),
    KilnProviderInfo(
        id=ModelProviderName.kiln_fine_tune,
        friendly_name="Fine Tuned Models",
    ),
    KilnProviderInfo(
        id=ModelProviderName.kiln_custom_registry,
        friendly_name="Custom Models",
    ),
    KilnProviderInfo(
        id=ModelProviderName.openai_compatible,
        friendly_name="OpenAI Compatible",
    ),
    KilnProviderInfo(
        id=ModelProviderName.anthropic,
        friendly_name="Anthropic",
        models_dev_id="anthropic",
    ),
    KilnProviderInfo(
        id=ModelProviderName.gemini_api,
        friendly_name="Gemini API",
        models_dev_id="google",
    ),
    KilnProviderInfo(
        id=ModelProviderName.azure_openai,
        friendly_name="Azure OpenAI",
        models_dev_id="azure",
    ),
    # models.dev has a `huggingface` key; set it here only once it is confirmed to be
    # the same service Kiln calls (Hugging Face Inference Providers).
    KilnProviderInfo(
        id=ModelProviderName.huggingface,
        friendly_name="Hugging Face",
    ),
    KilnProviderInfo(
        id=ModelProviderName.vertex,
        friendly_name="Gemini Enterprise Agent Platform",
        models_dev_id="google-vertex",
    ),
    KilnProviderInfo(
        id=ModelProviderName.together_ai,
        friendly_name="Together AI",
        models_dev_id="togetherai",
    ),
    KilnProviderInfo(
        id=ModelProviderName.siliconflow_cn,
        friendly_name="SiliconFlow",
        models_dev_id="siliconflow-cn",
    ),
    KilnProviderInfo(
        id=ModelProviderName.cerebras,
        friendly_name="Cerebras",
        models_dev_id="cerebras",
    ),
    KilnProviderInfo(
        id=ModelProviderName.docker_model_runner,
        friendly_name="Docker Model Runner",
    ),
    KilnProviderInfo(
        id=ModelProviderName.featherless_ai,
        friendly_name="Featherless AI",
    ),
    KilnProviderInfo(
        id=ModelProviderName.cloudflare,
        friendly_name="Cloudflare",
        models_dev_id="cloudflare-workers-ai",
    ),
    KilnProviderInfo(
        id=ModelProviderName.typesafe,
        friendly_name="TypeSafe AI",
    ),
)


def get_provider_info(provider: ModelProviderName) -> KilnProviderInfo:
    """
    The built-in info for a provider.

    Raises:
        ValueError: If built_in_providers has no item for the provider.
    """
    for info in built_in_providers:
        if info.id == provider:
            return info
    raise ValueError(f"No provider info for {provider.value}")
