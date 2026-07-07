"""Eval Builder review-pipeline API (studio side).

Two streams, one frame contract (see api_models/eval_builder_models.py):

  review_pipeline (multi-turn) — runs [drive → judge → claims] as one unit
  of work per case. The await order inside each case's coroutine IS the
  stage dependency; per-stage semaphores bound the fan-out (DRIVE_CONCURRENCY
  drive loops, REVIEW_CONCURRENCY judge+claims units). A case failing at any
  stage emits case_failed and the other cases keep flowing — completed
  results are never discarded. The judge and claim builder receive the
  runner's REAL trace (tool calls and system turns included), rendered once
  into the canonical transcript.

  review_traces (single-turn) — judge + claims over already-generated I/O
  pairs, fanned out per trace.

The remote kiln_server is only reached for the claim builder (secret sauce);
the judge runs locally via the Eval V2 llm_judge adapter (the user's keys).
Orchestration and concurrency live here so the UI stays a thin SSE consumer.
"""

import asyncio
import json
import logging
import re
from typing import Annotated, Any, AsyncIterator, Literal, cast

from app.desktop.studio_server.api_models.eval_builder_models import (
    BuildClaimsApiInput,
    BuildClaimsApiOutput,
    JudgeConfig,
    PipelineBatchCompletedEvent,
    PipelineBatchStartedEvent,
    PipelineCaseDrivenEvent,
    PipelineCaseFailedEvent,
    PipelineCaseReviewedEvent,
    PipelineTurnCompletedEvent,
    ReviewTracesRequest,
    TraceErrorEvent,
    TraceInput,
    TraceReviewedEvent,
    spec_name_must_have_a_json_key,
)
from app.desktop.studio_server.multiturn_sdg_api import (
    RunCasesBatchApiInput,
    guard_multiturn,
    to_su_driver_config,
    to_target_run_config,
)
from app.desktop.studio_server.utils.copilot_utils import (
    delete_multi_turn_batch_chains,
    get_copilot_api_key,
)
from app.desktop.studio_server.utils.eval_builder_utils import (
    build_claims_for_trace,
    run_judge_for_trace,
    transcript_io_for_trace,
)
from fastapi import FastAPI, HTTPException, Path, Request
from kiln_ai.datamodel.basemodel import FilenameStringShort
from kiln_ai.datamodel.task import Task
from kiln_ai.synthetic_user.case import SyntheticUserCase as RunnerCase
from kiln_ai.synthetic_user.runner import (
    BatchStartedEvent,
    CaseCompletedEvent,
    CaseFailedEvent,
    TurnCompletedEvent,
    run_cases_batch,
)
from kiln_server.cancellable_streaming_response import CancellableStreamingResponse
from kiln_ai.utils.git_sync_protocols import SaveContext, default_save_context
from kiln_server.git_sync_decorators import build_save_context, no_write_lock
from kiln_server.task_api import task_from_id
from kiln_server.utils.agent_checks.policy import agent_policy_require_approval
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing_extensions import Self

logger = logging.getLogger(__name__)

# The builder's two concurrency knobs, one per pipeline stage:
#   DRIVE_CONCURRENCY  — concurrent SU drive loops (target model + SU driver
#                        both burn tokens per turn; the most expensive stage).
#   REVIEW_CONCURRENCY — concurrent [judge → claims] units (a local judge
#                        call then a remote claim-builder call), shared by
#                        the merged pipeline and the single-turn review.
DRIVE_CONCURRENCY = 4
REVIEW_CONCURRENCY = 5


def _sse(payload: dict | BaseModel) -> str:
    """Format one SSE `data:` frame (the shared eval_builder frame contract)."""
    if isinstance(payload, BaseModel):
        payload = payload.model_dump(by_alias=True)  # by_alias → citations use `from`
    return "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"


SSE_TERMINATOR = "data: complete\n\n"


class ReviewPipelineRequest(RunCasesBatchApiInput):
    """The merged multi-turn pipeline's request: everything a drive takes
    (inherited — the two drive contracts can't drift) plus the judge that
    scores the results and the batch lifecycle field.

    `judge.prompt` doubles as the claim builder's eval_rubric — the builder
    pressure-tests the rubric the verdict was really produced under.
    """

    replace_batch_tags: list[str] = Field(
        default_factory=list,
        max_length=20,
        description=(
            "Batch tags of previous drives this one supersedes (aborted "
            "re-drives can leave several behind). Their chains are deleted "
            "once this drive has produced replacement chains "
            "(delete-on-redrive), so abandoned batches don't accumulate on "
            "disk — and a wholesale drive failure never destroys the only "
            "batch the user has."
        ),
    )

    # forbid: a retired or misspelled field on this request must 422, not be
    # silently dropped (a dropped replace_batch_tags quietly disables the
    # batch cleanup with no signal anywhere).
    model_config = ConfigDict(extra="forbid")

    @field_validator("replace_batch_tags")
    @classmethod
    def replace_batch_tags_must_be_valid(cls, value: list[str]) -> list[str]:
        for tag in value:
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", tag):
                raise ValueError(f"invalid batch tag: {tag!r}")
        return value

    @model_validator(mode="after")
    def batch_tag_cannot_be_replaced(self) -> Self:
        # Deleting the batch this drive is about to create would destroy the
        # results the moment they were produced.
        if self.batch_tag is not None and self.batch_tag in self.replace_batch_tags:
            raise ValueError(
                "replace_batch_tags must not contain this drive's own batch_tag."
            )
        return self

    spec_name: FilenameStringShort = Field(
        description="The spec's name. The review judge scores under the same "
        "output-score identity the saved eval will use, so the prompt the "
        "user calibrates here is byte-identical to the one that ships."
    )
    judge: JudgeConfig

    _spec_name_has_json_key = field_validator("spec_name")(
        spec_name_must_have_a_json_key
    )


async def review_one_trace(
    project_id: str,
    task_id: str,
    index: int,
    trace: TraceInput,
    judge: JudgeConfig,
    spec_name: str,
) -> TraceReviewedEvent:
    """One single-turn unit of work: judge the I/O pair (local), then build
    claims (remote). The claim builder's eval_rubric is the judge's actual
    prompt: it pressure-tests the rubric the verdict was produced under.
    """
    verdict = await run_judge_for_trace(
        project_id,
        task_id,
        trace.raw_input,
        trace.raw_output,
        judge,
        spec_name=spec_name,
    )
    claims_output = await build_claims_for_trace(
        raw_input=trace.raw_input,
        raw_output=trace.raw_output,
        eval_rubric=judge.prompt,
        judge_score=verdict.judge_score,
        judge_reasoning=verdict.judge_reasoning,
    )
    return TraceReviewedEvent(
        trace_index=index,
        raw_input=trace.raw_input,
        raw_output=trace.raw_output,
        judge_score=verdict.judge_score,
        judge_reasoning=verdict.judge_reasoning,
        claims=claims_output.claims,
        final_judgement=claims_output.final_judgement,
    )


class ReviewPipelineRun:
    """One merged-pipeline execution: [drive → judge → claims] per case.

    Frames from the concurrently-running stages funnel through one queue and
    come out of `events()`, the SSE stream body. Each stage is a method and
    shared state lives in instance attributes, so the pipeline reads top to
    bottom: `events()` drains, `_run_drive()` produces, `_review_case()`
    judges and distills, `_fail_case()` isolates.
    """

    def __init__(
        self,
        *,
        project_id: str,
        task_id: str,
        task: Task,
        cases: list[RunnerCase],
        input: ReviewPipelineRequest,
        save_context: SaveContext | None,
    ) -> None:
        self._project_id = project_id
        self._task_id = task_id
        self._task = task
        self._cases = cases
        self._input = input
        # build_save_context returns None outside a git-synced request; fall
        # back the same way the runner does.
        self._save_context = save_context or default_save_context
        # `None` is the end-of-stream sentinel.
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._review_sem = asyncio.Semaphore(REVIEW_CONCURRENCY)
        self._review_tasks: list[asyncio.Task] = []
        # Latest cumulative trace per case, captured from the runner's
        # in-process turn events — the REAL trace (tool calls, system turns),
        # not a wire projection. Popped when the case's review starts.
        self._latest_trace: dict[int, list[dict[str, Any]]] = {}
        self._turns_completed: dict[int, int] = {}
        self._reviewed_count = 0
        self._failed_count = 0
        self._total_cost = 0.0
        self._batch_tag = input.batch_tag or ""

    async def events(self) -> AsyncIterator[str]:
        """The SSE stream: drain frames until every stage finished, then
        emit batch_completed (or batch_failed) and the terminator."""
        drive_task = asyncio.create_task(self._run_drive(), name="pipeline_drive")

        async def close_when_done() -> None:
            # _review_tasks only grows while drive_task runs, so once the
            # drive is done the list is final and the gather is complete.
            try:
                await drive_task
            finally:
                if self._review_tasks:
                    await asyncio.gather(*self._review_tasks, return_exceptions=True)
                await self._queue.put(None)

        closer = asyncio.create_task(close_when_done(), name="pipeline_closer")

        try:
            while True:
                frame = await self._queue.get()
                if frame is None:
                    break
                yield frame
            # The closer swallows a drive-level crash (its finally still
            # closes the queue) — re-raise it here so the client sees
            # batch_failed, not a clean-looking batch_completed. Our own
            # teardown never reaches this line, so a cancelled drive here
            # means a stray CancelledError killed it: also a failure.
            if drive_task.cancelled():
                raise RuntimeError("The drive was cancelled unexpectedly.")
            drive_error = drive_task.exception() if drive_task.done() else None
            if drive_error is not None:
                raise drive_error
            yield _sse(
                PipelineBatchCompletedEvent(
                    reviewed=self._reviewed_count,
                    failed=self._failed_count,
                    batch_tag=self._batch_tag,
                    total_cost=self._total_cost,
                )
            )
        except Exception as e:  # noqa: BLE001 — last-resort surface for developer bugs
            # Per-case failures never reach here (they become case_failed
            # frames); this catches orchestration bugs only.
            logger.exception("review_pipeline failed mid-stream")
            yield _sse(
                {
                    "type": "batch_failed",
                    "code": "internal_error",
                    "message": f"{type(e).__name__}: {e}",
                }
            )
        finally:
            # Consumer disconnect (or any exit): stop the drive and any
            # in-flight reviews so abandoned LLM calls stop spending.
            drive_task.cancel()
            for t in self._review_tasks:
                t.cancel()
            closer.cancel()
            await asyncio.gather(
                drive_task, closer, *self._review_tasks, return_exceptions=True
            )
        yield SSE_TERMINATOR

    async def _run_drive(self) -> None:
        """Consume the SU runner's events; each completed case pipelines
        straight into its own judge+claims task — no stage barrier."""
        any_case_driven = False
        async for event in run_cases_batch(
            cases=self._cases,
            target_task=self._task,
            target_run_config=to_target_run_config(self._input.target_run_config),
            su_driver_config=to_su_driver_config(self._input.su_driver),
            turns=self._input.turns,
            concurrency=DRIVE_CONCURRENCY,
            batch_tag=self._input.batch_tag,
            save_context=self._save_context,
        ):
            if isinstance(event, BatchStartedEvent):
                self._batch_tag = event.batch_tag
                await self._emit(
                    PipelineBatchStartedEvent(
                        batch_tag=event.batch_tag,
                        total_cases=event.num_cases,
                    )
                )
            elif isinstance(event, TurnCompletedEvent):
                # The runner emits a fresh snapshot list per event; its typed
                # message params are plain dicts at runtime, which the
                # judge/claims layer treats loosely.
                self._latest_trace[event.case_index] = cast(
                    list[dict[str, Any]], event.trace
                )
                self._turns_completed[event.case_index] = (
                    self._turns_completed.get(event.case_index, 0) + 1
                )
                await self._emit(
                    PipelineTurnCompletedEvent(
                        case_index=event.case_index,
                        turns_completed=self._turns_completed[event.case_index],
                        total_turns=self._input.turns,
                    )
                )
            elif isinstance(event, CaseCompletedEvent):
                # Drive spend is real once the conversation ran, whatever the
                # review stage does with it later.
                self._total_cost += event.total_cost
                trace = self._latest_trace.pop(event.case_index, [])
                if not trace:
                    # turns >= 1 guarantees a turn event before the case
                    # completes; an empty trace means that invariant broke —
                    # fail the case, keep the batch.
                    await self._fail_case(
                        event.case_index,
                        "drive",
                        "missing_trace",
                        "The drive produced no trace for this case.",
                    )
                    continue
                any_case_driven = True
                await self._emit(
                    PipelineCaseDrivenEvent(
                        case_index=event.case_index,
                        leaf_run_id=event.leaf_run_id,
                    )
                )
                self._review_tasks.append(
                    asyncio.create_task(
                        self._review_case(
                            event.case_index,
                            event.leaf_run_id,
                            trace,
                            event.total_cost,
                        ),
                        name=f"review_case_{event.case_index}",
                    )
                )
            elif isinstance(event, CaseFailedEvent):
                await self._fail_case(
                    event.case_index, "drive", event.error_code, event.message
                )
            # The runner's BatchCompletedEvent is not forwarded: the
            # pipeline's own batch_completed fires after reviews drain.
        if any_case_driven:
            # Replacement chains exist on disk — now the superseded batches
            # can go. A drive that produced nothing keeps them untouched.
            await self._delete_superseded_batches()

    async def _review_case(
        self,
        case_index: int,
        leaf_run_id: str,
        trace: list[dict[str, Any]],
        drive_cost: float,
    ) -> None:
        """Judge one driven case (local), then build claims (remote)."""
        async with self._review_sem:
            try:
                raw_input, raw_output = transcript_io_for_trace(trace)
                verdict = await run_judge_for_trace(
                    self._project_id,
                    self._task_id,
                    raw_input,
                    raw_output,
                    self._input.judge,
                    spec_name=self._input.spec_name,
                    trace=trace,
                )
            except Exception as e:  # noqa: BLE001 — isolate to this case
                await self._fail_case(
                    case_index, "judge", "judge_failed", f"{type(e).__name__}: {e}"
                )
                return
            try:
                claims_output = await build_claims_for_trace(
                    raw_input=raw_input,
                    raw_output=raw_output,
                    eval_rubric=self._input.judge.prompt,
                    judge_score=verdict.judge_score,
                    judge_reasoning=verdict.judge_reasoning,
                )
                # Frame construction/serialization is inside the try: a
                # failure here must surface as case_failed too, or the batch
                # totals would claim a review the client never received.
                frame = _sse(
                    PipelineCaseReviewedEvent(
                        case_index=case_index,
                        leaf_run_id=leaf_run_id,
                        raw_input=raw_input,
                        raw_output=raw_output,
                        judge_score=verdict.judge_score,
                        judge_reasoning=verdict.judge_reasoning,
                        claims=claims_output.claims,
                        final_judgement=claims_output.final_judgement,
                        total_cost=drive_cost,
                    )
                )
            except Exception as e:  # noqa: BLE001 — isolate to this case
                await self._fail_case(
                    case_index, "claims", "claims_failed", f"{type(e).__name__}: {e}"
                )
                return
            self._reviewed_count += 1
            await self._queue.put(frame)

    async def _fail_case(
        self,
        case_index: int,
        stage: Literal["drive", "judge", "claims"],
        code: str,
        message: str,
    ) -> None:
        """One case died at `stage`; the batch continues without it."""
        logger.exception("review_pipeline: %s failed for case %d", stage, case_index)
        self._failed_count += 1
        await self._emit(
            PipelineCaseFailedEvent(
                case_index=case_index,
                stage=stage,
                code=code,
                message=message,
            )
        )

    async def _delete_superseded_batches(self) -> None:
        """Delete-on-redrive, AFTER the drive produced replacement chains —
        deleting up front could leave the user with neither batch when a
        re-drive fails wholesale. Best-effort cleanup: a failure here must
        never cost the batch's results.
        """
        for tag in self._input.replace_batch_tags:
            try:
                # The delete is sync file I/O over the task's run corpus —
                # run it off the event loop so other requests and streams
                # keep moving.
                async with self._save_context():
                    deleted = await asyncio.to_thread(
                        delete_multi_turn_batch_chains, self._task, tag
                    )
                logger.info(
                    "review_pipeline: deleted %d chain runs of superseded batch %s",
                    deleted,
                    tag,
                )
            except Exception:  # noqa: BLE001 — cleanup must not fail the batch
                logger.exception(
                    "review_pipeline: failed to delete superseded batch %s", tag
                )

    async def _emit(self, payload: dict | BaseModel) -> None:
        await self._queue.put(_sse(payload))


def connect_eval_builder_api(app: FastAPI):
    @app.post(
        "/api/projects/{project_id}/tasks/{task_id}/eval_builder/review_pipeline",
        tags=["Eval Builder"],
        summary="Run Multi-Turn Review Pipeline",
        openapi_extra=agent_policy_require_approval(
            "Drive multi-turn synthetic-user conversations and run judge + "
            "claims on each? Invokes the target model, SU driver, and judge "
            "(cost)."
        ),
    )
    @no_write_lock  # streaming route: lock would buffer the SSE and break cancel-on-disconnect
    async def review_pipeline(
        request: Request,
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[str, Path(description="The unique identifier of the task.")],
        input: ReviewPipelineRequest,
    ) -> CancellableStreamingResponse:
        """The merged multi-turn stream: [drive → judge → claims] per case.

        Emits (all frames `type`-discriminated; errors carry {code, message}):
          - batch_started   { batch_tag, total_cases }
          - turn_completed  { case_index, turns_completed, total_turns }
          - case_driven     { case_index, leaf_run_id }
          - case_reviewed   { case_index, leaf_run_id, raw_input, raw_output,
                              judge_score, judge_reasoning, claims,
                              final_judgement, total_cost }
          - case_failed     { case_index, stage, code, message }  (batch continues)
          - batch_completed { reviewed, failed, batch_tag, total_cost }
        Terminated by `data: complete`.
        """
        # Guard + decode before the stream opens so the client sees a clean
        # 4xx rather than a half-open text/event-stream. The copilot key
        # check comes first: the claims stage is the only remote call, but
        # discovering a missing key there would be AFTER the user burned
        # their own model spend driving and judging every case.
        get_copilot_api_key()
        task = task_from_id(project_id, task_id)
        guard_multiturn(task)
        try:
            runner_cases = [RunnerCase.model_validate(c) for c in input.cases]
        except Exception as exc:  # noqa: BLE001 — Pydantic ValidationError + any future shape drift
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "invalid_case_shape",
                    "message": f"Could not parse cases against the runner shape: {exc}",
                },
            ) from exc

        run = ReviewPipelineRun(
            project_id=project_id,
            task_id=task_id,
            task=task,
            cases=runner_cases,
            input=input,
            save_context=build_save_context(request),
        )
        return CancellableStreamingResponse(
            content=run.events(),
            media_type="text/event-stream",
        )

    @app.post(
        "/api/projects/{project_id}/tasks/{task_id}/eval_builder/review_traces",
        tags=["Eval Builder"],
        openapi_extra=agent_policy_require_approval(
            "Run judge and build claims for alignment traces?"
        ),
    )
    @no_write_lock  # streaming route: lock would buffer the SSE and break cancel-on-disconnect
    async def review_traces(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[str, Path(description="The unique identifier of the task.")],
        request: ReviewTracesRequest,
    ) -> CancellableStreamingResponse:
        """Per-trace `judge → claim builder` over single-turn I/O pairs,
        fanned out (local) and streamed.

        Emits one SSE event per trace as it completes:
          - `trace_reviewed` { trace_index, raw_input, raw_output,
                               judge_score, judge_reasoning, claims,
                               final_judgement }
          - `trace_error`    { trace_index, code, message }   (batch continues)
        Bracketed by `{ "type": "batch_started", "total" }` and `data: complete`.
        """

        async def event_generator():
            sem = asyncio.Semaphore(REVIEW_CONCURRENCY)

            async def one(index: int, trace: TraceInput) -> str:
                async with sem:
                    try:
                        event = await review_one_trace(
                            project_id,
                            task_id,
                            index,
                            trace,
                            request.judge,
                            request.spec_name,
                        )
                        return _sse(event)
                    except Exception as e:  # noqa: BLE001 — surface per-trace, keep batch alive
                        logger.exception(
                            "review_trace failed for trace_index=%s", index
                        )
                        return _sse(
                            TraceErrorEvent(
                                trace_index=index,
                                code="review_failed",
                                message=f"{type(e).__name__}: {e}",
                            )
                        )

            yield _sse({"type": "batch_started", "total": len(request.traces)})
            tasks = [
                asyncio.create_task(one(i, t)) for i, t in enumerate(request.traces)
            ]
            for finished in asyncio.as_completed(tasks):
                yield await finished
            yield SSE_TERMINATOR

        return CancellableStreamingResponse(
            content=event_generator(),
            media_type="text/event-stream",
        )

    @app.post(
        "/api/projects/{project_id}/tasks/{task_id}/eval_builder/build_claims",
        tags=["Eval Builder"],
        openapi_extra=agent_policy_require_approval(
            "Build claim/evidence for a trace?"
        ),
    )
    async def build_claims(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[str, Path(description="The unique identifier of the task.")],
        input: BuildClaimsApiInput,
    ) -> BuildClaimsApiOutput:
        """Claims-only primitive: build claims for one trace given a known verdict.

        Used by the refine loop (regenerate claims without re-running the judge).
        """
        return await build_claims_for_trace(
            raw_input=input.raw_input,
            raw_output=input.raw_output,
            eval_rubric=input.eval_rubric,
            judge_score=input.judge_score,
            judge_reasoning=input.judge_reasoning,
        )
