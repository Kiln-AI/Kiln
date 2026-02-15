from dataclasses import dataclass, field

from kiln_ai.datamodel.run_config import (
    KilnAgentRunConfigProperties,
)


@dataclass
class LiteLlmConfig:
    run_config_properties: KilnAgentRunConfigProperties
    # If set, over rides the provider-name based URL from litellm
    base_url: str | None = None
    # Headers to send with every request
    default_headers: dict[str, str] | None = None
    # Extra body to send with every request
    additional_body_options: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        # Validate that run_config_properties is a KilnAgent config
        if isinstance(self.run_config_properties, dict):
            if self.run_config_properties.get("type", "kiln_agent") != "kiln_agent":
                raise ValueError(
                    "LiteLlmConfig only supports kiln_agent run configurations."
                )
        elif hasattr(self.run_config_properties, "type"):
            if self.run_config_properties.type != "kiln_agent":
                raise ValueError(
                    "LiteLlmConfig only supports kiln_agent run configurations."
                )
