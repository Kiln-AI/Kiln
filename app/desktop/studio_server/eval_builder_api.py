"""Eval Builder review-pipeline API (studio side).

Orchestrates the alignment-phase review as one unit of work per trace —
`judge → claim builder` — and fans out across N traces server-side (local),
streaming each result to the UI. See specs/projects/eval_builder/review_pipeline.md.

The remote kiln_server is only reached for the claim builder (secret sauce); the
judge runs locally (stubbed until Eval V2 / PR #1454). Fan-out + concurrency live
here so the UI stays a thin SSE consumer.
"""

import asyncio
import json
import logging
from typing import Annotated

from app.desktop.studio_server.api_models.eval_builder_models import (
    BuildClaimsApiInput,
    BuildClaimsApiOutput,
    JudgeConfig,
    ReviewTracesRequest,
    TraceErrorEvent,
    TraceInput,
    TraceReviewedEvent,
)
from app.desktop.studio_server.utils.eval_builder_utils import (
    build_claims_for_trace,
    run_judge_for_trace,
)
from fastapi import FastAPI, Path
from kiln_server.cancellable_streaming_response import CancellableStreamingResponse
from kiln_server.utils.agent_checks.policy import agent_policy_require_approval

logger = logging.getLogger(__name__)

# Cap concurrent (local judge + remote claim) work per batch. Protects the local
# judge (LLM calls) and the remote claim calls; tune or swap to EvalRunner
# batching when the real judge lands (#1454).
REVIEW_CONCURRENCY = 5


def _sse(payload: dict | TraceReviewedEvent | TraceErrorEvent) -> str:
    """Format one SSE `data:` frame (matches the eval_api / multiturn_sdg convention)."""
    if isinstance(payload, (TraceReviewedEvent, TraceErrorEvent)):
        payload = payload.model_dump(by_alias=True)  # by_alias → citations use `from`
    return "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"


async def review_one_trace(
    project_id: str,
    task_id: str,
    index: int,
    trace: TraceInput,
    eval_rubric: str,
    judge: JudgeConfig,
) -> TraceReviewedEvent:
    """One unit of work: judge the trace (local), then build claims (remote)."""
    verdict = await run_judge_for_trace(
        project_id, task_id, trace.raw_input, trace.raw_output, judge
    )
    claims = await build_claims_for_trace(
        raw_input=trace.raw_input,
        raw_output=trace.raw_output,
        eval_rubric=eval_rubric,
        judge_score=verdict.judge_score,
        judge_reasoning=verdict.judge_reasoning,
    )
    return TraceReviewedEvent(
        trace_index=index,
        judge_score=verdict.judge_score,
        judge_reasoning=verdict.judge_reasoning,
        claims=claims,
    )


def connect_eval_builder_api(app: FastAPI):
    @app.post(
        "/api/projects/{project_id}/tasks/{task_id}/eval_builder/review_traces",
        tags=["Eval Builder"],
        openapi_extra=agent_policy_require_approval(
            "Run judge and build claims for alignment traces?"
        ),
    )
    async def review_traces(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[str, Path(description="The unique identifier of the task.")],
        request: ReviewTracesRequest,
    ) -> CancellableStreamingResponse:
        """Per-trace `judge → claim builder`, fanned out (local) and streamed.

        Emits one SSE event per trace as it completes:
          - `trace_reviewed` { trace_index, judge_score, judge_reasoning, claims }
          - `trace_error`    { trace_index, error }   (batch continues)
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
                            request.eval_rubric,
                            request.judge,
                        )
                        return _sse(event)
                    except Exception as e:  # noqa: BLE001 — surface per-trace, keep batch alive
                        logger.exception(
                            "review_trace failed for trace_index=%s", index
                        )
                        return _sse(
                            TraceErrorEvent(
                                trace_index=index, error=f"{type(e).__name__}: {e}"
                            )
                        )

            yield _sse({"type": "batch_started", "total": len(request.traces)})
            tasks = [
                asyncio.create_task(one(i, t)) for i, t in enumerate(request.traces)
            ]
            for finished in asyncio.as_completed(tasks):
                yield await finished
            yield "data: complete\n\n"

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
        return BuildClaimsApiOutput(
            claims=await build_claims_for_trace(
                raw_input=input.raw_input,
                raw_output=input.raw_output,
                eval_rubric=input.eval_rubric,
                judge_score=input.judge_score,
                judge_reasoning=input.judge_reasoning,
            )
        )
