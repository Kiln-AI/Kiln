"""Pydantic models for the Eval Builder review pipeline (studio side).

These are the STABLE, UI-driven contract (mirrors builder/claim_evidence.ts).
They are deliberately decoupled from the kiln_server SDK models: the server
side (claim builder, judge) is WIP and will churn, so the studio orchestrator
maps between these UI-facing models and the SDK internally. No SDK types leak
to the UI.
"""

from typing import Literal

from kiln_ai.datamodel.basemodel import FilenameStringShort
from kiln_ai.datamodel.json_schema import string_to_json_key
from pydantic import BaseModel, ConfigDict, Field, field_validator

# The binary verdict vocabulary, shared by every judge_score/expected_result
# field on this API surface (mirrors the server contract's enum).
JudgeScoreLiteral = Literal["pass", "fail"]


def spec_name_must_have_a_json_key(value: str) -> str:
    """Shared spec_name rule for every review request: the judge's score key
    is derived from the name, so a name with no [a-z0-9_] characters would
    produce an empty key and fail every trace deep inside the judge — reject
    it up front instead.
    """
    if not string_to_json_key(value):
        raise ValueError(
            "spec_name must contain at least one letter or digit usable in a score key."
        )
    return value


class TraceInput(BaseModel):
    """One single-turn example to review: the task's raw I/O pair.

    Multi-turn conversations never ride this request — they are driven,
    judged, and distilled server-side by the review pipeline, which reads
    the runner's real trace directly. Structured traces therefore have no
    wire shape here at all.
    """

    raw_input: str = Field(description="The task's raw input.")
    raw_output: str = Field(description="The task's raw output.")

    # forbid: a client still sending the retired multi-turn `trace` key must
    # fail loudly here, not have its trace silently dropped.
    model_config = ConfigDict(extra="forbid")


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

    traces: list[TraceInput] = Field(min_length=1, max_length=50)
    spec_name: FilenameStringShort = Field(
        description="The spec's name. The review judge scores under the same "
        "output-score identity the saved eval will use, so the prompt the "
        "user calibrates here is byte-identical to the one that ships."
    )
    judge: JudgeConfig

    _spec_name_has_json_key = field_validator("spec_name")(
        spec_name_must_have_a_json_key
    )


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


# ── SSE event payloads ────────────────────────────────────────────────────
#
# ONE frame contract across every eval_builder stream: each frame is a JSON
# object under a `data:` line, discriminated by `type`; error-class frames
# carry {code, message}; the stream terminator is the bare `data: complete`.


class TraceReviewedEvent(BaseModel):
    """Emitted once per trace as its judge+claims complete (single-turn).

    raw_input/raw_output echo the exact text the claim builder saw — the UI
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
    code: str
    message: str


# ── Review-pipeline SSE events (the merged multi-turn stream) ─────────────
#
# One stream runs [drive → judge → claims] per case; each case flows through
# independently, so events from different cases interleave. Ordering WITHIN
# a case: turn_completed* → case_driven → (case_reviewed | case_failed), or
# case_failed at any earlier point. A failed case never discards other
# cases' results.


class PipelineBatchStartedEvent(BaseModel):
    """First frame: the resolved batch tag and how many cases will run."""

    type: Literal["batch_started"] = "batch_started"
    batch_tag: str
    total_cases: int


class PipelineTurnCompletedEvent(BaseModel):
    """One assistant turn finished for a case (drives per-row progress)."""

    type: Literal["turn_completed"] = "turn_completed"
    case_index: int
    turns_completed: int
    total_turns: int


class PipelineCaseDrivenEvent(BaseModel):
    """A case's conversation finished driving; its judge+claims stage begins."""

    type: Literal["case_driven"] = "case_driven"
    case_index: int
    leaf_run_id: str


class PipelineCaseReviewedEvent(BaseModel):
    """A case completed the full [drive → judge → claims] pipeline.

    raw_input/raw_output are the canonical transcript rendering of the
    runner's REAL trace (tool calls and system turns included) — the same
    text the judge and claim builder saw, so citations resolve against it.
    """

    type: Literal["case_reviewed"] = "case_reviewed"
    case_index: int
    leaf_run_id: str
    raw_input: str
    raw_output: str
    judge_score: JudgeScoreLiteral
    judge_reasoning: str
    claims: list[ClaimApi]
    final_judgement: FinalJudgementApi
    total_cost: float


class PipelineCaseFailedEvent(BaseModel):
    """A case died at some stage; the batch continues without it."""

    type: Literal["case_failed"] = "case_failed"
    case_index: int
    stage: Literal["drive", "judge", "claims"]
    code: str
    message: str


class PipelineBatchCompletedEvent(BaseModel):
    """Last frame before the terminator: per-batch outcome counts."""

    type: Literal["batch_completed"] = "batch_completed"
    reviewed: int
    failed: int
    batch_tag: str
    total_cost: float
