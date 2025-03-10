from dataclasses import dataclass


@dataclass
class OpenAICompatibleConfig:
    api_key: str
    model_name: str
    # TODO what is this?
    provider_name: str
    litellm_provider_name: str
    # TODO P0 remove this? Naaa
    base_url: str | None = None
    default_headers: dict[str, str] | None = None
