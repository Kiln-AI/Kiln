from __future__ import annotations

import json
from enum import Enum
from typing import Any, Literal, get_args

from pydantic import BaseModel, Field, JsonValue, model_validator
from typing_extensions import Self

from kiln_ai.datamodel.json_schema import validate_schema_with_value_error
from kiln_ai.datamodel.openenv import OpenEnvReset
from kiln_ai.synthetic_user.parser import parse_synthetic_user_info
from kiln_ai.utils.usage import Usage

GroundingMode = Literal["multi_turn", "single_turn"]
"""What the grounding agent hands back for a case. `multi_turn`: it fills in the simulated
user kiln_server drafted, which then holds a whole conversation with the agent under test.
`single_turn`: it writes the one input the agent under test answers."""


class GroundingCase(BaseModel):
    """One planned case. A multi-turn case carries the simulated user kiln_server drafted
    for it; a single-turn case carries only its scenario, since the agent writes its
    input."""

    scenario: str = Field(description="The approved plan item's prompt.")
    seed_prompt: str | None = None
    synthetic_user_info: str | None = Field(
        default=None,
        description="kiln_server's tagged blob: <persona>, <goal>, optional <behavior_guidance>.",
    )

    @model_validator(mode="after")
    def _simulated_user_is_whole(self) -> Self:
        if (self.seed_prompt is None) != (self.synthetic_user_info is None):
            raise ValueError(
                "A case carries both seed_prompt and synthetic_user_info, or neither."
            )
        return self

    @property
    def mode(self) -> GroundingMode:
        """The mode this case's shape is for: a drafted simulated user is multi-turn."""
        return "multi_turn" if self.seed_prompt is not None else "single_turn"


class EvalContext(BaseModel):
    """What the eval is for. The same for every case in a run."""

    specification: str = Field(
        description="The eval's specification: what the eval tests."
    )
    target_task_prompt: str = Field(
        description="The target task's prompt: what the agent under test is told."
    )
    data_guide: str | None = Field(
        default=None,
        description="The task's Data Guide: who uses the agent under test, what they ask "
        "and what its inputs look like. None when the task has none.",
    )
    mode: GroundingMode = Field(
        default="multi_turn",
        description="What the agent hands back for each case (see GroundingMode).",
    )
    input_schema: str | None = Field(
        default=None,
        description="The JSON schema the input must match, when the task's input is "
        "structured. Single-turn only.",
    )
    example_input: str | None = Field(
        default=None,
        description="A real input from the task's dataset, for the input's format and "
        "voice. Single-turn only.",
    )

    @model_validator(mode="after")
    def _single_turn_fields(self) -> Self:
        if self.mode == "multi_turn" and (
            self.input_schema is not None or self.example_input is not None
        ):
            raise ValueError(
                "input_schema and example_input are for single-turn grounding only."
            )
        return self


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
    """A grounded case's facts of the environment. Saved as the markdown `render_judge_guidance` makes of
    it, under the reference key `judge_guidance`."""

    starting_point: str = Field(
        description="What the environment holds before the conversation, including any "
        "setup the grounding agent added."
    )
    facts: list[Fact]
    expected_outcome: str = Field(
        description="One short paragraph of facts: the correct answer the agent should be "
        "able to give and any change the environment should show at the end. Says nothing "
        "about how to apply the specification; the judge has that."
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
    input: str | None = Field(
        default=None, description="A single-turn case's input, in place of a user."
    )
    reference: GroundedReference | None = None

    @model_validator(mode="after")
    def _check_status_fields(self) -> Self:
        _check_status_fields(
            self.status,
            drop_reason=self.drop_reason,
            drop_detail=self.drop_detail,
            grounded_fields={"reference": self.reference},
            seed_prompt=self.seed_prompt,
            synthetic_user_info=self.synthetic_user_info,
            input=self.input,
        )
        if self.status == "grounded" and self.synthetic_user_info is not None:
            parse_synthetic_user_info(self.synthetic_user_info)
        return self

    def problem_for(self, eval_context: EvalContext) -> str | None:
        """Why this valid result doesn't fit the run's mode, or None when it does. A
        single-turn input must match the task's input schema when there is one."""
        if self.status == "dropped":
            return None
        if eval_context.mode == "multi_turn":
            if self.input is not None:
                return "A multi-turn case fills seed_prompt and synthetic_user_info, not input."
            return None
        if self.input is None:
            return "A single-turn case fills input, not seed_prompt and synthetic_user_info."
        if eval_context.input_schema is None:
            return None
        try:
            parsed = json.loads(self.input)
        except json.JSONDecodeError:
            return f"{INPUT_SCHEMA_MISMATCH} The input isn't valid JSON."
        try:
            validate_schema_with_value_error(parsed, eval_context.input_schema)
        except ValueError as e:
            return f"{INPUT_SCHEMA_MISMATCH} {e}"
        return None

    @classmethod
    def from_model_output(
        cls, data: dict[Any, Any], *, args_as_json_string: bool
    ) -> GroundingResult:
        """The result from the object the model returned in the shape of
        `result_json_schema(args_as_json_string=...)`. Raises ValueError (including
        pydantic's ValidationError) when it isn't a valid result."""
        if not args_as_json_string:
            return cls.model_validate(data)
        reference = data.get("reference")
        facts = reference.get("facts") if isinstance(reference, dict) else None
        if not isinstance(facts, list):
            return cls.model_validate(data)
        decoded_facts = [_decode_fact_args(fact) for fact in facts]
        return cls.model_validate(
            {**data, "reference": {**reference, "facts": decoded_facts}}
        )


INPUT_SCHEMA_MISMATCH = "The input didn't match the task's input schema."
"""How a single-turn input that breaks the task's input schema is reported."""


def result_json_schema(
    *, args_as_json_string: bool, mode: GroundingMode = "multi_turn"
) -> dict[str, Any]:
    """The JSON schema of `GroundingResult` that the model answers in, for `mode`.
    Written out with every property required and no `$ref`, so it holds under strict
    structured output.

    Strict output closes every object to the properties it lists, which would force the
    free-form `Evidence.args` to `{}`. With `args_as_json_string` it is a string holding
    the JSON object instead, and `GroundingResult.from_model_output` decodes it."""
    args_schema: dict[str, Any] = (
        {
            "type": "string",
            "description": "The arguments you called the tool with: a JSON object, "
            'written as a string, e.g. "{\\"id\\": 7}".',
        }
        if args_as_json_string
        else {
            "type": "object",
            "description": "The arguments you called the tool with.",
        }
    )
    evidence = _object_schema(
        {
            "tool": {"type": "string", "description": "The tool you called."},
            "args": args_schema,
            "result_excerpt": {
                "type": "string",
                "description": "The part of its result that shows the fact.",
            },
        }
    )
    reference = _object_schema(
        {
            "starting_point": {
                "type": "string",
                "description": "What the environment holds before the conversation, "
                "including any setup you added.",
            },
            "facts": {
                "type": "array",
                "items": _object_schema(
                    {"text": {"type": "string"}, "evidence": evidence}
                ),
            },
            "expected_outcome": {
                "type": "string",
                "description": "One short paragraph of facts: the correct answer the "
                "agent should be able to give and any change the environment should "
                "show at the end.",
            },
        }
    )
    return _object_schema(
        {
            "status": {"type": "string", "enum": ["grounded", "dropped"]},
            "drop_reason": {
                "type": ["string", "null"],
                "enum": [*get_args(ModelDropReason), None],
            },
            "drop_detail": {
                "type": ["string", "null"],
                "description": "One sentence on why the case was dropped.",
            },
            **(
                {
                    "input": {
                        "type": ["string", "null"],
                        "description": "The input the agent under test gets.",
                    }
                }
                if mode == "single_turn"
                else {
                    "seed_prompt": {
                        "type": ["string", "null"],
                        "description": "The filled-in opening message.",
                    },
                    "synthetic_user_info": {
                        "type": ["string", "null"],
                        "description": "<persona>...</persona><goal>...</goal>, then "
                        "<behavior_guidance>...</behavior_guidance> when the draft had one.",
                    },
                }
            ),
            "reference": {"anyOf": [reference, {"type": "null"}]},
        }
    )


def _object_schema(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _decode_fact_args(fact: Any) -> Any:
    """`fact` with its evidence `args` string decoded; any other shape is left for
    validation to report."""
    if not isinstance(fact, dict):
        return fact
    evidence = fact.get("evidence")
    if not isinstance(evidence, dict) or not isinstance(evidence.get("args"), str):
        return fact
    try:
        args = json.loads(evidence["args"])
    except json.JSONDecodeError as e:
        raise ValueError(f"A fact's evidence args is not valid JSON: {e}") from e
    if not isinstance(args, dict):
        raise ValueError("A fact's evidence args must be a JSON object.")
    return {**fact, "evidence": {**evidence, "args": args}}


class GroundingOutcome(BaseModel):
    """One case's grounding, ready to save or to show as a drop."""

    status: Literal["grounded", "dropped"]
    drop_reason: DropReason | None = None
    drop_detail: str | None = None
    openenv_reset: OpenEnvReset | None = None
    seed_prompt: str | None = None
    synthetic_user_info: str | None = None
    input: str | None = None
    reference: GroundedReference | None = None
    call_log: list[LoggedCall] = Field(default_factory=list)
    usage: Usage | None = Field(
        default=None, description="Tokens and cost, summed over the run."
    )
    usage_complete: bool = Field(
        default=True,
        description="False when some model calls' tokens and cost are missing from "
        "`usage`: a run cut short by a stop or the time limit, or one whose answer the "
        "adapter rejected, reports none.",
    )

    @model_validator(mode="after")
    def _check_status_fields(self) -> Self:
        _check_status_fields(
            self.status,
            drop_reason=self.drop_reason,
            drop_detail=self.drop_detail,
            grounded_fields={
                "openenv_reset": self.openenv_reset,
                "reference": self.reference,
            },
            seed_prompt=self.seed_prompt,
            synthetic_user_info=self.synthetic_user_info,
            input=self.input,
        )
        return self

    @classmethod
    def dropped(
        cls,
        reason: DropReason,
        detail: str,
        *,
        call_log: list[LoggedCall],
        usage: Usage | None,
        usage_complete: bool = True,
    ) -> GroundingOutcome:
        """A dropped case, with the calls made before it was dropped."""
        return cls(
            status="dropped",
            drop_reason=reason,
            drop_detail=detail,
            call_log=call_log,
            usage=usage,
            usage_complete=usage_complete,
        )

    @classmethod
    def from_result(
        cls,
        result: GroundingResult,
        *,
        openenv_reset: OpenEnvReset | None,
        call_log: list[LoggedCall],
        usage: Usage | None,
        usage_complete: bool = True,
    ) -> GroundingOutcome:
        """The outcome for the model's result. `openenv_reset` is the session's last reset,
        the environment the reference was observed in; a grounded result without one never
        looked at the environment, so it is dropped as `invalid_output`."""
        if result.status == "dropped":
            assert result.drop_reason is not None and result.drop_detail is not None
            return cls.dropped(
                DropReason(result.drop_reason),
                result.drop_detail,
                call_log=call_log,
                usage=usage,
                usage_complete=usage_complete,
            )
        if openenv_reset is None:
            return cls.dropped(
                DropReason.invalid_output,
                "The agent returned a grounded case without starting an environment.",
                call_log=call_log,
                usage=usage,
                usage_complete=usage_complete,
            )
        return cls(
            status="grounded",
            openenv_reset=openenv_reset,
            seed_prompt=result.seed_prompt,
            synthetic_user_info=result.synthetic_user_info,
            input=result.input,
            reference=result.reference,
            call_log=call_log,
            usage=usage,
            usage_complete=usage_complete,
        )


def _check_status_fields(
    status: Literal["grounded", "dropped"],
    *,
    drop_reason: object,
    drop_detail: str | None,
    grounded_fields: dict[str, object],
    seed_prompt: str | None,
    synthetic_user_info: str | None,
    input: str | None,
) -> None:
    """A grounded case has `grounded_fields` and one of the two shapes: a simulated user
    (seed_prompt and synthetic_user_info) or an input. A dropped case has a reason and
    detail."""
    if status == "grounded":
        missing = [name for name, value in grounded_fields.items() if value is None]
        if input is None:
            missing += [
                name
                for name, value in (
                    ("seed_prompt", seed_prompt),
                    ("synthetic_user_info", synthetic_user_info),
                )
                if value is None
            ]
        if missing:
            raise ValueError(f"A grounded case needs {', '.join(missing)}.")
        if input is not None and (
            seed_prompt is not None or synthetic_user_info is not None
        ):
            raise ValueError(
                "A grounded case has an input or a simulated user, not both."
            )
        if drop_reason is not None or drop_detail is not None:
            raise ValueError("A grounded case has no drop reason or detail.")
        return
    if drop_reason is None or not drop_detail:
        raise ValueError("A dropped case needs drop_reason and drop_detail.")
