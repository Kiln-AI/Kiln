"""Pydantic models for the Eval Builder review pipeline (studio side).

These are the STABLE, UI-driven contract (mirrors builder/claim_evidence.ts).
They are deliberately decoupled from the kiln_server SDK models: the server
side (claim builder, judge) is WIP and will churn, so the studio orchestrator
maps between these UI-facing models and the SDK internally. No SDK types leak
to the UI.
"""

from typing import Any, Literal

from kiln_ai.datamodel.basemodel import FilenameStringShort
from kiln_ai.datamodel.json_schema import string_to_json_key
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing_extensions import Self

# The binary verdict vocabulary, shared by every judge_score/expected_result
# field on this API surface (mirrors the server contract's enum).
JudgeScoreLiteral = Literal["pass", "fail"]


class TraceInput(BaseModel):
    """One generated trace to review (single- or multi-turn).

    Exactly one source shape per trace: single-turn sends the raw I/O pair;
    multi-turn sends the structured message list and the studio derives the
    canonical transcript from it server-side — the UI never fabricates a
    flattened rendering, so the text the claim builder cites is authoritative
    (it's echoed back on the trace_reviewed event).
    """

    raw_input: str | None = Field(
        default=None,
        description="Single-turn: the task's raw input. Omitted for "
        "multi-turn traces (derived from the trace's first user message).",
    )
    raw_output: str | None = Field(
        default=None,
        description="Single-turn: the task's raw output. Omitted for "
        "multi-turn traces (the canonical transcript is rendered from trace).",
    )
    trace: list[dict[str, Any]] | None = Field(
        default=None,
        min_length=1,
        description="Structured message list ({role, content}, chronological) "
        "for multi-turn traces: the judge scores it directly and the claim "
        "builder receives its canonical rendering. Kept as loose dicts — "
        "message shapes (tool calls etc.) will churn.",
    )

    @model_validator(mode="after")
    def validate_one_source_shape(self) -> Self:
        has_io = self.raw_input is not None and self.raw_output is not None
        if self.trace is None and not has_io:
            raise ValueError(
                "Provide raw_input + raw_output (single-turn) or trace (multi-turn)."
            )
        if self.trace is not None and (
            self.raw_input is not None or self.raw_output is not None
        ):
            raise ValueError(
                "Multi-turn traces send only `trace` — raw_input/raw_output are "
                "derived server-side so the rendering is canonical."
            )
        return self


class JudgeConfig(BaseModel):
    """The judge: a plain-text prompt plus the model that runs it.

    The ONE judge shape across the builder — the review step runs it
    transiently and the save path persists it as a V2 EvalConfig, both through
    the same prompt-template wrap, so the judge the user calibrates is the
    judge that ships.
    """

    prompt: str
    model_name: str
    model_provider: str


class ReviewTracesRequest(BaseModel):
    """Batch request: judge + build claims for every trace, streamed back.

    The claim builder's eval_rubric is the judge's ACTUAL prompt (from
    `judge`), not a separate spec text — the builder pressure-tests the rubric
    the verdict was really produced under.
    """

    traces: list[TraceInput]
    spec_name: FilenameStringShort = Field(
        description="The spec's name. The review judge scores under the same "
        "output-score identity the saved eval will use, so the prompt the "
        "user calibrates here is byte-identical to the one that ships."
    )
    judge: JudgeConfig

    @field_validator("spec_name")
    @classmethod
    def spec_name_must_have_a_json_key(cls, value: str) -> str:
        # The score's JSON-schema key is derived from the name; a name with no
        # [a-z0-9_] characters would produce an empty key and fail every trace
        # deep inside the judge — reject it up front instead.
        if not string_to_json_key(value):
            raise ValueError(
                "spec_name must contain at least one letter or digit usable "
                "in a score key."
            )
        return value


class CitationApi(BaseModel):
    """A start+end anchor into the trace; the UI highlights from `from` to `to`.

    `from` is a Python keyword, so the field is `from_` with an alias — the
    serialized key MUST stay `from` (the UI greps that literal JSON key).
    """

    marker: int
    source: Literal["input", "output"]
    from_: str = Field(alias="from")
    to: str

    model_config = ConfigDict(populate_by_name=True)


class ClaimApi(BaseModel):
    """One atomic claim + its one-sentence evidence with [n] citation markers.

    `expected_result` is the verdict a reviewer's AGREE on this claim supports —
    a direction bit, not a re-judging: claims pointing opposite the judge's
    verdict are counter-evidence the reviewer can use to catch a bad judge.
    """

    claim: str
    expected_result: JudgeScoreLiteral
    evidence: str
    citations: list[CitationApi]


class FinalJudgementApi(BaseModel):
    """The one overall verdict entry (top-level, not a claim in the list).

    Its expected_result always equals the judge's verdict — the server pins it
    deterministically, so the answer key can anchor to it.
    """

    claim: str
    expected_result: JudgeScoreLiteral
    evidence: str
    citations: list[CitationApi]


class BuildClaimsApiInput(BaseModel):
    """One trace + its judge decision, to distill into claim/evidence pairs.

    The claims-only primitive: use when a verdict is already known (e.g. the
    refine loop re-generating claims without re-running the judge).
    """

    raw_input: str
    raw_output: str
    eval_rubric: str
    judge_reasoning: str
    judge_score: JudgeScoreLiteral


class BuildClaimsApiOutput(BaseModel):
    """Claims for one trace (importance-ordered, may be empty) + the one
    final judgement. Trivial single-property evals can carry everything in
    the final judgement alone."""

    claims: list[ClaimApi]
    final_judgement: FinalJudgementApi


# ── SSE event payloads (serialized to JSON in the review_traces stream) ──────


class TraceReviewedEvent(BaseModel):
    """Emitted once per trace as its judge+claims complete.

    raw_input/raw_output echo the exact text the claim builder saw (for
    multi-turn, the canonical transcript rendered server-side) — the UI
    displays and resolves citations against these, never its own rendering.
    """

    type: Literal["trace_reviewed"] = "trace_reviewed"
    trace_index: int
    raw_input: str
    raw_output: str
    judge_score: JudgeScoreLiteral
    judge_reasoning: str
    claims: list[ClaimApi]
    final_judgement: FinalJudgementApi


class TraceErrorEvent(BaseModel):
    """Emitted for a trace whose judge or claim step failed; batch continues."""

    type: Literal["trace_error"] = "trace_error"
    trace_index: int
    error: str
