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
        notes=(
            "Data retention: API usage is not used for training by default.\n"
            "Rate limits: Tiered by usage; higher tiers unlock more requests per minute."
        ),
        models_dev_id="openai",
    ),
    KilnProviderInfo(
        id=ModelProviderName.groq,
        friendly_name="Groq",
        notes=(
            "Data retention: Does not use prompts or completions for training.\n"
            "Rate limits: Free tier has low RPM limits that can stall agents; paid plans raise them."
        ),
        models_dev_id="groq",
    ),
    KilnProviderInfo(
        id=ModelProviderName.amazon_bedrock,
        friendly_name="Amazon Bedrock",
        notes=(
            "Data retention: Does not use prompts or completions for training by default.\n"
            "Gotchas: Requires AWS account setup, IAM permissions, and model access requests per region."
        ),
        models_dev_id="amazon-bedrock",
    ),
    KilnProviderInfo(
        id=ModelProviderName.ollama,
        friendly_name="Ollama",
        notes=(
            "Data retention: Runs locally; no data leaves the machine.\n"
            "Gotchas: Requires local GPU or CPU resources; performance depends on hardware."
        ),
    ),
    KilnProviderInfo(
        id=ModelProviderName.openrouter,
        friendly_name="OpenRouter",
        notes=(
            "Data retention: Depends on the upstream host. Account settings can block hosts that log or train on prompts.\n"
            "Routing: Routes each request to one of several upstream hosts; quality and quantization can differ between them.\n"
            "Gotchas: Some models are free variants with low rate limits; do not use them for production agents."
        ),
        models_dev_id="openrouter",
    ),
    KilnProviderInfo(
        id=ModelProviderName.fireworks_ai,
        friendly_name="Fireworks AI",
        notes=(
            "Data retention: Does not use prompts or completions for training; SOC 2 compliant.\n"
            "Rate limits: Per-account rate limits; contact sales for higher tiers."
        ),
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
        notes="Gotchas: Behavior depends on the endpoint operator; test tool calls and structured output before relying on them.",
    ),
    KilnProviderInfo(
        id=ModelProviderName.anthropic,
        friendly_name="Anthropic",
        notes=(
            "Data retention: Does not use prompts or completions for training by default.\n"
            "Rate limits: Tiered by usage; rate limits apply per model and per organization."
        ),
        models_dev_id="anthropic",
    ),
    KilnProviderInfo(
        id=ModelProviderName.gemini_api,
        friendly_name="Gemini API",
        notes=(
            "Data retention: Paid API usage is not used for training. Free-tier prompts may be reviewed.\n"
            "Rate limits: Free tier has low RPM limits; paid plans raise them per model."
        ),
        models_dev_id="google",
    ),
    KilnProviderInfo(
        id=ModelProviderName.azure_openai,
        friendly_name="Azure OpenAI",
        notes=(
            "Data retention: Does not use prompts or completions for training. Data stays within the Azure region.\n"
            "Gotchas: Requires Azure subscription, resource deployment, and model access approval per region."
        ),
        models_dev_id="azure",
    ),
    KilnProviderInfo(
        id=ModelProviderName.huggingface,
        friendly_name="Hugging Face",
        notes=(
            "Rate limits: Free tier has low rate limits; PRO subscriptions raise them.\n"
            "Routing: Routes through Hugging Face Inference Providers to upstream hosts."
        ),
        # Confirmed: models.dev's `huggingface` entry (doc: huggingface.co/docs/inference-providers,
        # api: router.huggingface.co/v1) is the same Hugging Face Inference Providers service Kiln uses.
        models_dev_id="huggingface",
    ),
    KilnProviderInfo(
        id=ModelProviderName.vertex,
        friendly_name="Gemini Enterprise Agent Platform",
        notes=(
            "Data retention: Does not use customer data for training. Data stays within the GCP project.\n"
            "Gotchas: Requires GCP project setup, billing, and API enablement."
        ),
        models_dev_id="google-vertex",
    ),
    KilnProviderInfo(
        id=ModelProviderName.together_ai,
        friendly_name="Together AI",
        notes="Data retention: Does not use prompts or completions for training.",
        models_dev_id="togetherai",
    ),
    KilnProviderInfo(
        id=ModelProviderName.siliconflow_cn,
        friendly_name="SiliconFlow",
        notes="Gotchas: China-based service; latency may be high from other regions.",
        models_dev_id="siliconflow-cn",
    ),
    KilnProviderInfo(
        id=ModelProviderName.cerebras,
        friendly_name="Cerebras",
        notes="Rate limits: Free tier is available but has strict RPM limits.",
        models_dev_id="cerebras",
    ),
    KilnProviderInfo(
        id=ModelProviderName.docker_model_runner,
        friendly_name="Docker Model Runner",
        notes=(
            "Data retention: Runs locally within Docker; no data leaves the machine.\n"
            "Gotchas: Requires Docker Desktop with the Model Runner feature enabled."
        ),
    ),
    KilnProviderInfo(
        id=ModelProviderName.featherless_ai,
        friendly_name="Featherless AI",
        notes="Data retention: Does not use prompts or completions for training.",
    ),
    KilnProviderInfo(
        id=ModelProviderName.cloudflare,
        friendly_name="Cloudflare",
        notes="Gotchas: Workers AI has per-request size limits and region-dependent latency.",
        models_dev_id="cloudflare-workers-ai",
    ),
    KilnProviderInfo(
        id=ModelProviderName.typesafe,
        friendly_name="TypeSafe AI",
        notes="Gotchas: Uses a custom adapter (Jev); not OpenAI-compatible.",
    ),
    KilnProviderInfo(
        id=ModelProviderName.opencode,
        friendly_name="OpenCode",
        notes=(
            "Data retention: OpenCode's hosts don't retain data by default, but the OpenAI, Anthropic and xAI APIs keep requests 30 days and Google up to 55 days.\n"
            "Routing: An AI gateway; each model runs on its lab's own API (OpenAI, Anthropic, Google, xAI) or a vetted host, and Kiln calls all of them through OpenCode's Chat Completions translation.\n"
            "Gotchas: Pay-as-you-go credits only; OpenCode Go subscriptions and OpenCode's free models aren't supported."
        ),
        tags=[],
        models_dev_id="opencode",
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
