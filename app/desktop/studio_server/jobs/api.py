from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Annotated, Any, AsyncGenerator

from fastapi import FastAPI, HTTPException, Path, Query, Response
from kiln_server.cancellable_streaming_response import CancellableStreamingResponse
from kiln_server.utils.agent_checks.policy import (
    ALLOW_AGENT,
    agent_policy_require_approval,
)
from pydantic import BaseModel, Field

from ..eval_api import eval_from_id, split_filter_id_from_eval
from . import error_log
from .events import JobEvent
from .models import BackgroundJobStatus, JobRecord
from .registry import JobNotFoundError, JobOperationError, job_registry
from .workers.eval import EvalJobParams, EvalJobWorker
from .workers.judge_feedback_batch import (
    JudgeFeedbackBatchJobParams,
    JudgeFeedbackBatchJobWorker,
)

KEEPALIVE_SECONDS = 15.0

_JOB_MUTATION_APPROVAL = agent_policy_require_approval(
    "Allow agent to control background jobs (pause, resume, cancel, delete)?"
)

_EVAL_JOB_APPROVAL = agent_policy_require_approval(
    "Run an eval in the background? This runs LLM calls across the eval set and uses AI credits."
)

_JUDGE_FEEDBACK_BATCH_JOB_APPROVAL = agent_policy_require_approval(
    "Run a judge feedback batch in the background? It makes model calls over the sampled dataset items."
)


class CreateJobResponse(BaseModel):
    """Response returned when a job is created."""

    job_id: str = Field(description="The id of the newly created job.")
    status: BackgroundJobStatus = Field(
        description="The job's status immediately after creation."
    )


class WaitForJobsRequest(BaseModel):
    """Request body for waiting on a set of jobs."""

    ids: list[str] = Field(
        default_factory=list,
        description="Job ids to wait for. All must reach a terminal state.",
    )
    timeout: float | None = Field(
        default=None,
        ge=0,
        description="Seconds to wait before giving up (504 on timeout). "
        "Omit to wait indefinitely.",
    )


def _format_sse(event: JobEvent) -> str:
    return (
        f"event: {event.event}\ndata: {json.dumps(event.data, ensure_ascii=False)}\n\n"
    )


async def _event_stream(
    job_id: str | None,
    type_name: str | None,
    project_id: str | None,
):
    """Pure-observer SSE generator.

    Subscribes to the registry event bus and forwards snapshot/job/deleted
    events, injecting a keepalive comment between events. Closing this generator
    (client disconnect, via CancellableStreamingResponse) only unsubscribes from
    the bus — it never touches any job's supervising task. Jobs keep running.
    """
    # subscribe() handles the keepalive itself, yielding a "ping" event after
    # `timeout` idle seconds.
    subscription: AsyncGenerator[JobEvent, None] = job_registry.events.subscribe(
        job_id=job_id,
        type_name=type_name,
        project_id=project_id,
        timeout=KEEPALIVE_SECONDS,
    )
    try:
        async for event in subscription:
            if event.event == "ping":
                yield ": ping\n\n"
            else:
                yield _format_sse(event)
    finally:
        await subscription.aclose()


def connect_jobs_api(app: FastAPI) -> None:
    # Register the workers this server exposes. register_type overwrites by
    # type_name, so repeated calls (e.g. multiple make_app() in tests) are safe.
    job_registry.register_type(EvalJobWorker)
    job_registry.register_type(JudgeFeedbackBatchJobWorker)

    @app.get(
        "/api/jobs/events",
        summary="Stream Job Events",
        tags=["Jobs"],
        openapi_extra=ALLOW_AGENT,
    )
    async def stream_job_events(
        job_id: Annotated[
            str | None, Query(description="Only stream events for this job id.")
        ] = None,
        type: Annotated[
            str | None, Query(description="Only stream events for this job type.")
        ] = None,
        project_id: Annotated[
            str | None, Query(description="Only stream events for this project id.")
        ] = None,
    ) -> CancellableStreamingResponse:
        """Server-sent events for jobs. Emits an initial `snapshot`, then per-job
        `job` and `deleted` events. A pure observer: disconnecting never stops a job."""
        return CancellableStreamingResponse(
            content=_event_stream(job_id, type, project_id),
            media_type="text/event-stream",
        )

    @app.get(
        "/api/jobs",
        summary="List Jobs",
        tags=["Jobs"],
        openapi_extra=ALLOW_AGENT,
    )
    async def list_jobs(
        status: Annotated[
            BackgroundJobStatus | None, Query(description="Filter by job status.")
        ] = None,
        type: Annotated[str | None, Query(description="Filter by job type.")] = None,
        project_id: Annotated[
            str | None, Query(description="Filter by project id.")
        ] = None,
        since: Annotated[
            datetime | None,
            Query(description="Only jobs created at or after this ISO-8601 time."),
        ] = None,
        limit: Annotated[
            int | None, Query(description="Maximum number of jobs to return.")
        ] = None,
    ) -> list[JobRecord]:
        return job_registry.list_jobs(
            status=status,
            type_name=type,
            project_id=project_id,
            since=since,
            limit=limit,
        )

    # Two-segment path so it can never collide with the generic single-segment
    # POST /api/jobs/{type} (i.e. type="evals"), independent of route order.
    @app.post(
        "/api/jobs/evals/run",
        summary="Run Eval Job",
        tags=["Jobs"],
        status_code=201,
        response_model=CreateJobResponse,
        openapi_extra=_EVAL_JOB_APPROVAL,
    )
    async def run_eval_job(params: EvalJobParams) -> CreateJobResponse:
        """Kick off an eval as a background job and return immediately.

        A typed, approval-gated entry point for agents. Unlike the UI's SSE
        run endpoints, this does not stream — the job runs in the background.
        Poll `GET /api/jobs/{id}` (or `/api/jobs/wait`) for progress and the
        result.
        """
        # Resolve a requested split before creating the job, so an eval with no
        # such split fails here with a 422 (or a missing eval with a 404) instead
        # of surfacing later as a failed background job. The worker resolves the
        # split again at run time; entity loads are blocking IO, so run them off
        # the event loop.
        if params.split is not None:
            split = params.split
            await asyncio.to_thread(
                lambda: split_filter_id_from_eval(
                    eval_from_id(params.project_id, params.task_id, params.eval_id),
                    split,
                )
            )
        job = await job_registry.create(
            type_name=EvalJobWorker.type_name,
            params=params,
            project_id=params.project_id,
        )
        return CreateJobResponse(job_id=job.id, status=job.status)

    # Two-segment path so it can never collide with the generic single-segment
    # POST /api/jobs/{type}, independent of route order.
    @app.post(
        "/api/jobs/judge_feedback_batch/run",
        summary="Run Judge Feedback Batch Job",
        tags=["Jobs"],
        status_code=201,
        response_model=CreateJobResponse,
        openapi_extra=_JUDGE_FEEDBACK_BATCH_JOB_APPROVAL,
    )
    async def run_judge_feedback_batch_job(
        params: JudgeFeedbackBatchJobParams,
    ) -> CreateJobResponse:
        """Run a pre-existing judge feedback batch as a background job, returning immediately.

        Create the batch first via `POST /judge_feedback_batches` (returns its id), then run
        it here — mirroring how eval jobs run a pre-existing eval, so the batch id lives in the
        job's params and is retrievable via `GET /api/jobs/{id}` even if the run fails. Lets an
        agent fire many gates and `POST /api/jobs/wait` on all of them at once instead of
        blocking on each synchronous call. The aggregate scores/usage/latency are on the job
        result; the per-item runs (with the judge's feedback) are persisted — fetch them via
        `GET /judge_feedback_batches/{id}/runs`.
        """
        job = await job_registry.create(
            type_name=JudgeFeedbackBatchJobWorker.type_name,
            params=params,
            project_id=params.project_id,
        )
        return CreateJobResponse(job_id=job.id, status=job.status)

    @app.post(
        "/api/jobs/wait",
        summary="Wait For Jobs",
        tags=["Jobs"],
        openapi_extra=ALLOW_AGENT,
    )
    async def wait_for_jobs(request: WaitForJobsRequest) -> list[JobRecord]:
        """Block until ALL the given jobs reach a terminal state, then return
        their records (order preserved). A pure observer, like the SSE stream:
        disconnecting tears down only the awaiter, never the jobs. The timeout
        bounds the whole set. Empty `ids` returns an empty list."""
        if not request.ids:
            return []
        try:
            return await job_registry.wait_many(request.ids, timeout=request.timeout)
        except JobNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"Job not found: {exc}")
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=504,
                detail="Not all jobs completed within the timeout.",
            )

    @app.get(
        "/api/jobs/{id}",
        summary="Get Job",
        tags=["Jobs"],
        openapi_extra=ALLOW_AGENT,
    )
    async def get_job(
        id: Annotated[str, Path(description="The job id.")],
    ) -> JobRecord:
        job = await job_registry.get(id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Job not found: {id}")
        return job

    @app.get(
        "/api/jobs/{id}/result",
        summary="Get Job Result",
        tags=["Jobs"],
        openapi_extra=ALLOW_AGENT,
    )
    async def get_job_result(
        id: Annotated[str, Path(description="The job id.")],
    ) -> dict[str, Any]:
        job = await job_registry.get(id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Job not found: {id}")
        if not job.status.is_terminal or job.result is None:
            raise HTTPException(
                status_code=404, detail="No result available for this job."
            )
        return job.result

    @app.get(
        "/api/jobs/{id}/errors",
        summary="Get Job Errors",
        tags=["Jobs"],
        openapi_extra=ALLOW_AGENT,
    )
    async def get_job_errors(
        id: Annotated[str, Path(description="The job id.")],
        run_id: Annotated[
            str | None,
            Query(description="Read the error log for a specific past run id."),
        ] = None,
    ) -> list[dict[str, Any]]:
        # Always 200, never errors (functional_spec §5). A plain non-reconciling
        # lookup of the current run_id — we don't recompute state for a
        # best-effort diagnostic read.
        resolved_run_id = run_id or job_registry.run_id_for(id)
        if resolved_run_id is None:
            return []
        return error_log.read_errors(resolved_run_id)

    @app.post(
        "/api/jobs/{id}/pause",
        summary="Pause Job",
        tags=["Jobs"],
        status_code=202,
        openapi_extra=_JOB_MUTATION_APPROVAL,
    )
    async def pause_job(
        id: Annotated[str, Path(description="The job id.")],
    ) -> Response:
        await _run_lifecycle(job_registry.pause, id)
        return Response(status_code=202)

    @app.post(
        "/api/jobs/{id}/resume",
        summary="Resume Job",
        tags=["Jobs"],
        status_code=202,
        openapi_extra=_JOB_MUTATION_APPROVAL,
    )
    async def resume_job(
        id: Annotated[str, Path(description="The job id.")],
    ) -> Response:
        await _run_lifecycle(job_registry.resume, id)
        return Response(status_code=202)

    @app.post(
        "/api/jobs/{id}/cancel",
        summary="Cancel Job",
        tags=["Jobs"],
        status_code=202,
        openapi_extra=_JOB_MUTATION_APPROVAL,
    )
    async def cancel_job(
        id: Annotated[str, Path(description="The job id.")],
    ) -> Response:
        await _run_lifecycle(job_registry.cancel, id)
        return Response(status_code=202)

    @app.delete(
        "/api/jobs/{id}",
        summary="Delete Job",
        tags=["Jobs"],
        status_code=204,
        openapi_extra=_JOB_MUTATION_APPROVAL,
    )
    async def delete_job(
        id: Annotated[str, Path(description="The job id.")],
    ) -> Response:
        await _run_lifecycle(job_registry.delete, id)
        return Response(status_code=204)


async def _run_lifecycle(operation, job_id: str) -> Any:
    """Invoke a registry lifecycle op, mapping its exceptions to HTTP status.

    JobNotFoundError -> 404, JobOperationError (invalid transition / unsupported
    pause / delete in-flight) -> 409.
    """
    try:
        return await operation(job_id)
    except JobNotFoundError:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    except JobOperationError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
