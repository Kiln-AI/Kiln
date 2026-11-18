from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, JsonValue, model_validator
from typing_extensions import Self

from kiln_ai.datamodel.openenv import OpenEnvReset
from kiln_ai.synthetic_user.parser import parse_synthetic_user_info
from kiln_ai.utils.usage import Usage


class GroundingCase(BaseModel):
    """One planned case, as kiln_server drafted it."""

    scenario: str = Field(description="The approved plan item's prompt.")
    seed_prompt: str
    synthetic_user_info: str = Field(
        description="kiln_server's tagged blob: <persona>, <goal>, optional <behavior_guidance>."
    )


class Evidence(BaseModel):
    """The call the grounding agent made to learn a fact, so a person can re-run it. Not
    the path the agent under test must take."""

    tool: str
    args: dict[str, JsonValue]
    result_excerpt: str


class Fact(BaseModel):
    """One thing true in the environment, with the call that showed it."""

    text: str
    evidence: Evidence


class GroundedReference(BaseModel):
    """A grounded case's answer key, stored as `EvalInput.reference` via `model_dump()`."""

    starting_point: str = Field(description="What is true before the conversation.")
    facts: list[Fact]
    expected_outcome: list[str] = Field(
        description="What must be true at the end, or what the agent must tell the user."
    )
    allowed: list[str] = Field(
        description="Acceptable alternatives, e.g. asking a clarifying question first."
    )
    must_not_happen: list[str] = Field(
        description="Changes or claims that fail the case."
    )


class DropReason(str, Enum):
    """Why a case was dropped instead of grounded."""

    no_fit = "no_fit"
    """Nothing fits the scenario after a reasonable search."""
    unrepresentable = "unrepresentable"
    """The scenario needs something the server can't represent."""
    rehearsal_failed = "rehearsal_failed"
    """The rehearsal failed for a reason the agent under test couldn't avoid."""
    limit = "limit"
    """The tool calls, resets or time ran out."""
    invalid_output = "invalid_output"
    """The agent's result could not be used."""


ModelDropReason = Literal["no_fit", "unrepresentable", "rehearsal_failed"]
"""The drop reasons the model may give. `limit` and `invalid_output` are Kiln's to set."""


class LoggedCall(BaseModel):
    """One tool call the grounding agent made, as it went to the server and came back."""

    tool: str
    args: dict[str, JsonValue]
    output: str
    is_error: bool
    episode_id: str | None = Field(
        description="The environment the call ran in. None when it ran in none."
    )


class GroundingResult(BaseModel):
    """What the grounding model returns. `openenv_reset` is deliberately absent: it is
    the session's last reset, the environment the reference was observed in."""

    status: Literal["grounded", "dropped"]
    drop_reason: ModelDropReason | None = None
    drop_detail: str | None = Field(
        default=None, description="One sentence, shown to the user."
    )
    seed_prompt: str | None = None
    synthetic_user_info: str | None = None
    reference: GroundedReference | None = None

    @model_validator(mode="after")
    def _check_status_fields(self) -> Self:
        _check_status_fields(
            self.status,
            drop_reason=self.drop_reason,
            drop_detail=self.drop_detail,
            grounded_fields={
                "seed_prompt": self.seed_prompt,
                "synthetic_user_info": self.synthetic_user_info,
                "reference": self.reference,
            },
        )
        if self.status == "grounded" and self.synthetic_user_info is not None:
            parse_synthetic_user_info(self.synthetic_user_info)
        return self


class GroundingOutcome(BaseModel):
    """One case's grounding, ready to save or to show as a drop."""

    status: Literal["grounded", "dropped"]
    drop_reason: DropReason | None = None
    drop_detail: str | None = None
    openenv_reset: OpenEnvReset | None = None
    seed_prompt: str | None = None
    synthetic_user_info: str | None = None
    reference: GroundedReference | None = None
    call_log: list[LoggedCall] = Field(default_factory=list)
    usage: Usage | None = Field(
        default=None, description="Tokens and cost, summed over the run."
    )

    @model_validator(mode="after")
    def _check_status_fields(self) -> Self:
        _check_status_fields(
            self.status,
            drop_reason=self.drop_reason,
            drop_detail=self.drop_detail,
            grounded_fields={
                "openenv_reset": self.openenv_reset,
                "seed_prompt": self.seed_prompt,
                "synthetic_user_info": self.synthetic_user_info,
                "reference": self.reference,
            },
        )
        return self


def _check_status_fields(
    status: Literal["grounded", "dropped"],
    *,
    drop_reason: object,
    drop_detail: str | None,
    grounded_fields: dict[str, object],
) -> None:
    if status == "grounded":
        missing = [name for name, value in grounded_fields.items() if value is None]
        if missing:
            raise ValueError(f"A grounded case needs {', '.join(missing)}.")
        if drop_reason is not None or drop_detail is not None:
            raise ValueError("A grounded case has no drop reason or detail.")
        return
    if drop_reason is None or not drop_detail:
        raise ValueError("A dropped case needs drop_reason and drop_detail.")
