"""Pydantic models for the Eval Builder review pipeline (studio side).

These are the STABLE, UI-driven contract (mirrors builder/claim_evidence.ts).
They are deliberately decoupled from the kiln_server SDK models: the server
side (claim builder, judge) is WIP and will churn, so the studio orchestrator
maps between these UI-facing models and the SDK internally. No SDK types leak
to the UI.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TraceInput(BaseModel):
    """One generated trace to review (single- or multi-turn)."""

    raw_input: str
    raw_output: str
    trace: list[dict[str, Any]] | None = Field(
        default=None,
        description="Structured message list ({role, content}, chronological) "
        "for multi-turn traces, so the judge scores the full conversation "
        "instead of the flattened raw_output. Single-turn traces omit it. "
        "Kept as loose dicts: the claim builder still receives the flattened "
        "text, and message shapes (tool calls etc.) will churn.",
    )


class JudgeConfig(BaseModel):
    """The candidate judge to run over each trace.

    PROVISIONAL: the judge is WIP (today a prompt+model; with Eval V2 it becomes
    a typed EvalConfig, then more eval types). Kept intentionally thin — the
    orchestrator maps this to whatever the judge execution currently needs, so
    the UI contract doesn't churn with the server.
    """

    prompt: str
    model_name: str
    model_provider: str


class ReviewTracesRequest(BaseModel):
    """Batch request: judge + build claims for every trace, streamed back."""

    traces: list[TraceInput]
    eval_rubric: str = Field(
        description="The spec intent / rubric passed to the claim builder "
        "(distinct from the judge prompt)."
    )
    judge: JudgeConfig


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
    """One atomic claim + its one-sentence evidence with [n] citation markers."""

    claim: str
    claim_type: Literal["inclusion", "exclusion", "assertion", "final_judgement"]
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
    judge_score: str


class BuildClaimsApiOutput(BaseModel):
    """All claims for one trace, ordered most- to least-important."""

    claims: list[ClaimApi]


# ── SSE event payloads (serialized to JSON in the review_traces stream) ──────


class TraceReviewedEvent(BaseModel):
    """Emitted once per trace as its judge+claims complete."""

    type: Literal["trace_reviewed"] = "trace_reviewed"
    trace_index: int
    judge_score: str
    judge_reasoning: str
    claims: list[ClaimApi]


class TraceErrorEvent(BaseModel):
    """Emitted for a trace whose judge or claim step failed; batch continues."""

    type: Literal["trace_error"] = "trace_error"
    trace_index: int
    error: str
