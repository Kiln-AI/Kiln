"""Internal models for the synthetic-user player.

`SyntheticUserInfo` is declared in the datamodel (it persists on multi-turn
eval inputs) and re-exported here for the runtime side: the parser produces
it from the tagged wire blob and `prompt.render_system_prompt` consumes it.
`SyntheticUserDriverConfig` carries the per-eval runtime config — model,
provider, role visibility.
"""

from typing import Literal

from pydantic import BaseModel, Field

from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.datamodel.eval import SyntheticUserInfo as SyntheticUserInfo

VisibleMessageRole = Literal["user", "assistant"]

# The exact message the SU sends to end a conversation before the turn ceiling
# is reached. It lives in this leaf module so the drive loop that acts on it
# and the prompt that will teach it can share one string without importing
# each other. Nothing teaches it yet, so today every case still runs the full
# `turns`.
EARLY_STOP_SENTINEL = "<DONE>"


class SyntheticUserDriverConfig(BaseModel):
    """Per-eval runtime config for the SU's LLM driver.

    No `temperature` field — runs at the chosen model's default. The driver
    intentionally does not own temperature: the persona-playing prompt and
    `behavior_guidance` carry style; temperature is a model-level concern
    surfaced elsewhere when it matters.
    """

    model_name: str
    model_provider_name: ModelProviderName
    visible_message_roles: list[VisibleMessageRole] = Field(
        default_factory=lambda: ["user", "assistant"]
    )
