from dataclasses import dataclass


@dataclass
class OpenAICompatibleConfig:
    api_key: str
    model_name: str
    provider_name: str
    base_url: str | None = None  # Defaults to OpenAI
    default_headers: dict[str, str] | None = None
    openrouter_style_reasoning: bool = False
