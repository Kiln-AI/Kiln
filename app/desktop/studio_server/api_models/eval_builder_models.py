"""Pydantic models for the Eval Builder pipelines (studio side).

These are the STABLE, UI-driven contract (mirrors builder/claim_evidence.ts).
They are deliberately decoupled from the kiln_server SDK models so
server-side changes don't ripple into the UI contract: the studio
orchestrator maps between these UI-facing models and the SDK internally.
No SDK types leak to the UI.
"""

from typing import Any, Literal

from kiln_ai.adapters.eval.base_eval import validate_judge_thinking_level
from kiln_ai.datamodel.claim_review import GradedClaim
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.datamodel.json_schema import string_to_json_key
from kiln_ai.datamodel.openenv import OpenEnvReset
from kiln_ai.eval_grounding.models import DropReason
from kiln_ai.utils.usage import Usage
from pydantic import BaseModel, ConfigDict, Field, model_validator

# The binary verdict vocabulary, shared by every judge_score and human_verdict
# field on this API surface (mirrors the server contract's enum).
JudgeScoreLiteral = Literal["pass", "fail"]


def spec_name_must_have_a_json_key(value: str) -> str:
    """Name rule for the spec-save request: the saved eval's score key is
    derived from the name, so a name with no [a-z0-9_] characters would
    produce an empty key and fail every eval job deep inside the judge —
    reject it up front instead. (The review streams carry no name; their
    transient judge scores under a constant draft key.)
    """
    if not string_to_json_key(value):
        raise ValueError(
            "spec_name must contain at least one letter or digit usable in a score key."
        )
    return value


class JudgeConfig(BaseModel):
    """The judge: a plain-text prompt plus the model that runs it.

    The ONE judge shape across the builder — the review step runs it
    transiently and the save path persists it as a V2 EvalConfig, both through
    the same prompt-template wrap, so the judge the user calibrates is the
    judge that ships.
    """

    prompt: str
    model_name: str
    # Validate the provider against the registry enum, like every other
    # model-lane field on this surface — a bad provider must 422 here, not
    # persist a judge config that fails deep inside every eval run.
    model_provider: ModelProviderName
    thinking_level: str | None = Field(
        default=None,
        description="The judge model's thinking level, one of the levels its provider offers. Unset uses the model's default.",
    )

    @model_validator(mode="after")
    def thinking_level_is_offered(self) -> "JudgeConfig":
        if self.thinking_level is not None:
            validate_judge_thinking_level(
                self.model_name, self.model_provider, self.thinking_level
            )
        return self


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


class OverviewApi(BaseModel):
    """The neutral summary of the trace the reviewer reads before the claims.

    Same shape as a claim: prose with inline [n] markers resolved through
    `citations`. Markers restart at [1] here and in every claim.
    """

    text: str
    citations: list[CitationApi]


class ClaimApi(BaseModel):
    """One decision the judge made, written so the reviewer can vote on it.

    `text` carries the claim, its evidence and its [n] markers in one string;
    every marker resolves through `citations`. Grades have one direction:
    agree means the judge got this decision right, disagree means it got it
    wrong.

    `is_verdict` marks the claim that states the overall pass/fail. The claim
    builder may omit it, and only the LAST claim can be one, so the UI needs a
    flag rather than a guess: it decides whether to derive the reviewer's
    overall call from that claim's grade or to ask for it outright. The studio
    sets the flag from the builder's own convention (the verdict claim opens
    "It passes" or "It fails", and no other claim may) so the UI never
    pattern-matches prose.
    """

    text: str
    citations: list[CitationApi]
    is_verdict: bool


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
    judge_guidance: str | None = Field(
        default=None,
        description="The case's judge guidance, for a case grounded in an OpenEnv "
        "server. The judge read it beside the rubric, so the claim builder does too.",
    )


class BuildClaimsApiOutput(BaseModel):
    """The review card for one trace: the overview, then one to eight claims
    in the order the reviewer reads them. The verdict claim, when the builder
    wrote one, is the last claim and carries `is_verdict`."""

    overview: OverviewApi
    claims: list[ClaimApi]


# ── Run-config preflight ──────────────────────────────────────────────────


class PreflightModelApiInput(BaseModel):
    """One model lane to verify before a drive commits real spend.

    The client pings each lane the pipeline will use (target run config,
    synthetic-user driver, judge) with one of these before generate_cases,
    so a dead key/model stops the drive before the plan/SU-gen minutes and
    the batch's model spend, not after.
    """

    model_name: str = Field(description="The model to verify.")
    model_provider: ModelProviderName = Field(
        description="The provider to verify the model against."
    )


class PreflightModelApiOutput(BaseModel):
    """The lane answered a one-word completion — key, billing, and model
    resolution all work. Failures surface as a 400 with the unwrapped root
    provider error instead."""

    ok: Literal[True] = True


# ── Refine judge loop ─────────────────────────────────────────────────────


class GradedTraceApi(BaseModel):
    """One human-reviewed trace's grades, shaped to feed judge refinement.

    Mirrors the persisted ClaimReview (judge verdict, the overview, every
    claim with its agree/disagree and optional why, and the reviewer's
    overall call) plus a `trace_label` the refine model cites in its change
    rationales.
    """

    trace_label: str = Field(
        description="A label for the trace the refine model cites in its "
        "rationales; derived UI-side from the run id (often opaque)."
    )
    judge_score: JudgeScoreLiteral
    judge_reasoning: str
    overview: str
    # Never a subset: every claim on the card, graded. A card always carries
    # at least one, and the refiner rejects an empty list.
    claims: list[GradedClaim] = Field(min_length=1)
    human_verdict: JudgeScoreLiteral


class RefineJudgeApiInput(BaseModel):
    """The current judge prompt plus the human's grades on reviewed traces.

    `judge_prompt` is the plain-text rubric being refined (the same text the
    review judge ran with). The refined result is a PROPOSAL — the studio
    never auto-applies it.
    """

    judge_prompt: str = Field(min_length=1)
    graded_traces: list[GradedTraceApi] = Field(min_length=1, max_length=50)


class RefineJudgeChangeApi(BaseModel):
    """One edit the refine model made to the judge prompt, with its rationale."""

    change: str
    rationale: str


class RefineJudgeApiOutput(BaseModel):
    """The proposed judge-prompt revision + a per-edit rationale.

    A PROPOSAL: the UI shows the changes for approval and validates the
    prompt before any write; it is never auto-applied.
    """

    refined_judge_prompt: str
    changes: list[RefineJudgeChangeApi]
    not_incorporated_feedback: str | None


class AuthorJudgeApiInput(BaseModel):
    """The spec + target-task prompt the judge author tailors its rubric to.

    One authoring path for both arms: same two inputs, prompt-only output —
    the judge model stays the caller's choice. Both arms judge a transcript,
    so the rubric is always authored against one; the framing is fixed
    server-side rather than client-sent.
    """

    target_specification: str = Field(min_length=1)
    target_task_prompt: str
    run_config_id: str | None = Field(
        default=None,
        description="The task run config the eval is written against. Its "
        "tools and skills are what the rubric grades tool and skill use "
        "over. Omit to use the task's default run config.",
    )


class AuthorJudgeApiOutput(BaseModel):
    """The authored judge prompt — plain text, rendered into the judge
    harness verbatim."""

    judge_prompt: str


# ── SSE event payloads ────────────────────────────────────────────────────
#
# ONE frame contract across every eval_builder stream: each frame is a JSON
# object under a `data:` line, discriminated by `type`; error-class frames
# carry {code, message}; the stream terminator is the bare `data: complete`.


# ── Review-pipeline SSE events (the merged pipeline streams) ──────────────
#
# One stream runs [drive → judge] (multi-turn multi_turn_pipeline) or
# [run → judge] (single_turn_pipeline) per case; each case flows through
# independently, so events from different cases interleave. Ordering WITHIN
# a case: turn_completed* (multi-turn only) → case_driven →
# (case_judged | case_failed), or case_failed at any earlier point. A
# failed case never discards other cases' results. Claims are NOT built on
# these streams: the client builds them lazily via the build_claims
# primitive for the traces a reviewer actually opens — under subset review
# most traces are never opened.
#
# judge_traces (the re-judge stream) emits the SAME batch/case frames with
# no drive or turn events, so one client consumer serves every stream.
# Drive-only fields carry honest neutral values there (batch_tag "",
# total_cost 0).


class PipelineBatchStartedEvent(BaseModel):
    """First frame: the resolved batch tag and how many cases will run."""

    type: Literal["batch_started"] = "batch_started"
    batch_tag: str
    total_cases: int


class PipelineTurnCompletedEvent(BaseModel):
    """One assistant turn finished for a case (drives batch progress)."""

    type: Literal["turn_completed"] = "turn_completed"
    case_index: int
    turns_completed: int
    total_turns: int


class PipelineCaseDrivenEvent(BaseModel):
    """A case's conversation (or single-turn run) finished; its judge stage
    begins. leaf_run_id is the chain's leaf on the multi-turn stream and the
    run itself on the single-turn one."""

    type: Literal["case_driven"] = "case_driven"
    case_index: int
    leaf_run_id: str


class PipelineCaseJudgedEvent(BaseModel):
    """A case completed the [drive → judge] pipeline.

    raw_output is the canonical transcript rendering of the runner's REAL
    trace (tool calls and system turns included) — the same text the judge saw
    and the claim builder will see, so citations built later resolve against
    it. raw_input is the conversation's opening user message on the multi-turn
    stream; the single-turn stream keeps the run's own input string instead,
    because that is what its saved eval reads back.
    """

    type: Literal["case_judged"] = "case_judged"
    case_index: int
    leaf_run_id: str
    raw_input: str
    raw_output: str
    judge_score: JudgeScoreLiteral
    judge_reasoning: str
    total_cost: float
    # The structured conversation behind raw_output, as raw chat-completion
    # message dicts: the runner's real trace on the multi-turn stream, the
    # run's own trace (tool calls included) on the single-turn one. The
    # client renders it in the house chat UI. Both streams judge this
    # conversation, exactly what the saved eval judges — a run whose adapter
    # recorded no trace is judged on a two-message echo of its pair rather
    # than on nothing. Nullable only for legacy streams that predate it.
    trace: list[dict[str, Any]] | None = None


class PipelineCaseFailedEvent(BaseModel):
    """A case died at some stage; the batch continues without it.

    Stage vocabulary: "drive" = the multi-turn conversation stage, "run" =
    the single-turn one-shot task run, "judge" = the shared scoring stage.
    """

    type: Literal["case_failed"] = "case_failed"
    case_index: int
    stage: Literal["drive", "run", "judge"]
    code: str
    message: str
    # Exception class name behind a provider or unexpected failure, so clients
    # can aggregate by type instead of parsing `message`. Always None on
    # deterministic failures (invalid_input, missing_output,
    # bad_synthetic_user_info): `code` already names those, and it does so even
    # where an exception triggered them.
    error_type: str | None = None


class PipelineBatchCompletedEvent(BaseModel):
    """Last frame before the terminator: per-batch outcome counts."""

    type: Literal["batch_completed"] = "batch_completed"
    judged: int
    failed: int
    batch_tag: str
    # Actual drive spend for the batch, including failed cases and retried
    # attempts whose chains were discarded — not just surviving conversations.
    total_cost: float


class PipelineBatchAbortedEvent(BaseModel):
    """The whole batch was aborted on a config-scoped (batch-fatal) failure —
    an error guaranteed to kill every case identically (bad credentials,
    deprecated model, hard budget wall; see retry_classification.
    is_batch_fatal_error). Emitted ONCE in place of batch_completed, then
    the stream tears down like a consumer disconnect, cancelling queued and
    in-flight cases so a doomed batch stops spending. Judge-lane only today:
    a drive-lane config error fails every case fast and free, so the
    client's stop banner covers it without an abort."""

    type: Literal["batch_aborted"] = "batch_aborted"
    error: str
    stage: Literal["drive", "run", "judge"]


# ── Grounding stream (ground_cases) ───────────────────────────────────────
#
# One frame per finished case, in finishing order, between grounding_started
# and grounding_finished (or grounding_failed, which ends the stream in its
# place). case_index is the case's position in the request.


class GroundingModelApi(BaseModel):
    """The model the grounding agent runs on: the build's judge model, at the judge's
    thinking level."""

    model_name: str = Field(min_length=1)
    model_provider: ModelProviderName
    thinking_level: str | None = Field(
        default=None,
        description="The thinking level, one of the levels the model's provider offers. Unset uses the model's default.",
    )

    @model_validator(mode="after")
    def thinking_level_is_offered(self) -> "GroundingModelApi":
        if self.thinking_level is not None:
            validate_judge_thinking_level(
                self.model_name, self.model_provider, self.thinking_level
            )
        return self


class GroundCaseApi(BaseModel):
    """One planned case to ground: its plan item and kiln_server's simulated user."""

    scenario_index: int = Field(
        ge=0, description="The plan item's position in the approved plan."
    )
    scenario: str = Field(min_length=1, description="The plan item's text.")
    seed_prompt: str = Field(min_length=1)
    synthetic_user_info: str = Field(
        min_length=1,
        description="kiln_server's tagged blob: <persona>, <goal>, optional "
        "<behavior_guidance>.",
    )


class GroundingStartedEvent(BaseModel):
    """First frame: how many cases will be grounded."""

    type: Literal["grounding_started"] = "grounding_started"
    total: int


class CaseGroundedEvent(BaseModel):
    """A case fits the environment. Its simulated user carries real specifics, and
    `openenv_reset` and `judge_guidance` go with it to the drive, judge and save."""

    type: Literal["case_grounded"] = "case_grounded"
    case_index: int
    scenario_index: int
    status: Literal["grounded"] = "grounded"
    openenv_reset: OpenEnvReset
    seed_prompt: str
    synthetic_user_info: str
    judge_guidance: str = Field(
        description="The case's facts of the environment, as markdown: starting "
        "point, facts with the tool call that showed each, expected outcome."
    )


class CaseDroppedEvent(BaseModel):
    """A case couldn't be made to fit the environment."""

    type: Literal["case_dropped"] = "case_dropped"
    case_index: int
    scenario_index: int
    drop_reason: DropReason
    drop_detail: str = Field(description="One sentence, shown to the user.")


class GroundingFinishedEvent(BaseModel):
    """Last frame before the terminator: every case finished."""

    type: Literal["grounding_finished"] = "grounding_finished"
    grounded: int
    dropped: int
    usage: Usage | None = Field(
        description="Tokens and cost summed over the cases that reported any."
    )
    usage_complete: bool = Field(
        description="False when some model calls' tokens and cost are missing from usage."
    )


class GroundingFailedEvent(BaseModel):
    """Grounding stopped on an error that is not a case's fault, such as the server
    going unreachable or the model provider failing. Sent in place of
    grounding_finished; the cases still running were cancelled."""

    type: Literal["grounding_failed"] = "grounding_failed"
    code: Literal["openenv_unreachable", "grounding_error", "internal_error"]
    message: str
