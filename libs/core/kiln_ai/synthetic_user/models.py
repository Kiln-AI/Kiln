"""Internal models for the synthetic-user player.

`SyntheticUserInfo` is the parsed form of the tagged blob the server sends
on `/generate`; the parser produces it and `prompt.render_system_prompt`
consumes it. `SyntheticUserDriverConfig` carries the per-eval runtime
config — model, provider, role visibility.
"""

from typing import Literal

from pydantic import BaseModel, Field

from kiln_ai.datamodel.datamodel_enums import ModelProviderName

VisibleMessageRole = Literal["user", "assistant"]


class SyntheticUserInfo(BaseModel):
    """Parsed form of the tagged synthetic_user_info blob.

    Built by `parser.parse_synthetic_user_info` from the wire string.
    Used by `prompt.render_system_prompt` to assemble the per-request
    system prompt.

    Extend with new fields as the server-side generator emits new tags —
    the parser ignores unknown tags so this is forward-compat by default.
    """

    persona: str
    goal: str
    behavior_guidance: str | None = None


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
