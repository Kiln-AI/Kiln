from dataclasses import dataclass, field


@dataclass
class LiteLlmConfig:
    model_name: str
    provider_name: str
    # If set, over rides the provider-name based URL from litellm
    base_url: str | None = None
    # Headers to send with every request
    default_headers: dict[str, str] | None = None
    # Extra body to send with every request
    additional_body_options: dict[str, str] = field(default_factory=dict)
