from dataclasses import dataclass, field

from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties


@dataclass
class LiteLlmConfig:
    run_config_properties: KilnAgentRunConfigProperties
    # If set, over rides the provider-name based URL from litellm
    base_url: str | None = None
    # Headers to send with every request
    default_headers: dict[str, str] | None = None
    # Extra body to send with every request
    additional_body_options: dict[str, str] = field(default_factory=dict)
