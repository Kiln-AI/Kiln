from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Annotated, Any, AsyncGenerator

from fastapi import FastAPI, HTTPException, Path, Query, Response
from kiln_ai.adapters.eval.eval_runner import EvalRunner
from kiln_server.cancellable_streaming_response import CancellableStreamingResponse
from kiln_server.task_api import task_from_id
from kiln_server.utils.agent_checks.policy import (
    ALLOW_AGENT,
    agent_policy_require_approval,
)
from pydantic import BaseModel, Field, ValidationError

from app.desktop.studio_server.eval_api import (
    eval_config_from_id,
    eval_from_id,
    require_dataset_run_items_or_400,
    resolved_split_or_422,
    task_run_config_from_id,
)

from . import error_log
from .events import JobEvent
from .models import BackgroundJobStatus, JobRecord, WaitTimeoutBounds
from .registry import JobNotFoundError, JobOperationError, job_registry
from .workers.eval import EvalJobParams, EvalJobWorker
from .workers.noop import NoopJobWorker

KEEPALIVE_SECONDS = 15.0

_JOB_MUTATION_APPROVAL = agent_policy_require_approval(
    "Allow agent to control background jobs (pause, resume, cancel, delete)?"
)

_EVAL_JOB_APPROVAL = agent_policy_require_approval(
    "Run an eval in the background? This runs LLM calls across the eval's dataset split and uses AI credits."
)


class CreateJobRequest(BaseModel):
    """Request body for creating a job. Params are validated per job type."""

    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Type-specific job parameters, validated against the type's params model.",
    )
    project_id: str | None = Field(
        default=None,
        description="Project to scope this job to (for filtering/visibility). "
        "Falls back to the params' project_id when omitted.",
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Free-form pass-through attribution, stored verbatim.",
    )


class CreateJobResponse(BaseModel):
    """Response returned when a job is created."""

    job_id: str = Field(description="The id of the newly created job.")
    status: BackgroundJobStatus = Field(
        description="The job's status immediately after creation."
    )


def _project_id_from_params(validated_params: BaseModel) -> str | None:
    return getattr(validated_params, "project_id", None)


class WaitForJobsRequest(BaseModel):
    """Request body for waiting on a set of jobs."""

    ids: list[str] = Field(
        default_factory=list,
        description="Job ids to wait for. All must reach a terminal state.",
    )
    timeout: float = Field(
        default=WaitTimeoutBounds.DEFAULT,
        ge=0,
        le=WaitTimeoutBounds.MAX,
        description="Seconds to wait before giving up (504 on timeout; jobs keep "
        f"running — re-issue the wait to keep waiting). Defaults to "
        f"{WaitTimeoutBounds.DEFAULT:.0f}s, capped at {WaitTimeoutBounds.MAX:.0f}s: "
        "the wait is always bounded, since a job that never terminates (e.g. "
        "paused by the user) would otherwise hang the caller indefinitely.",
    )


def _check_eval_job_request(params: EvalJobParams) -> None:
    """Raise unless the job can run: 404 if the eval, the eval config or the run config
    is missing, 422 if the eval has no such split or if `item_ids` names an item that is
    not in the split, and 400 for the checks the run_comparison endpoint also makes
    before it runs (a V1 judge on items it can't score, multi-turn items that can't be
    driven). Without those, the job would start and fail every item one by one.

    Deliberately discards what it resolved. The worker resolves the split again when the
    job actually runs, because a job runs the items as they are then, not as they were
    when it was requested.
    """
    eval = eval_from_id(params.project_id, params.task_id, params.eval_id)
    eval_config = eval_config_from_id(
        params.project_id, params.task_id, params.eval_id, params.eval_config_id
    )
    run_config = task_run_config_from_id(
        params.project_id, params.task_id, params.run_config_id
    )
    task = task_from_id(params.project_id, params.task_id)
    split = resolved_split_or_422(task, eval, params.split)
    if params.item_ids is not None:
        split_ids = {item.id for item in split.items}
        outside = [item_id for item_id in params.item_ids if item_id not in split_ids]
        if outside:
            raise HTTPException(
                status_code=422,
                detail=f"Items not in the '{params.split}' split of eval '{eval.id}': "
                + ", ".join(outside),
            )
    require_dataset_run_items_or_400(eval, eval_config.config_type, split)
    try:
        EvalRunner(
            eval_configs=[eval_config],
            run_configs=[run_config],
            eval_run_type="task_run_eval",
            split=split,
        ).validate_multi_turn_drive_readiness()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


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
    job_registry.register_type(NoopJobWorker)
    job_registry.register_type(EvalJobWorker)

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

    # Registered before POST /api/jobs/{type}: routes match in registration order,
    # and "wait" is a single segment that the generic route would otherwise take.
    # The registry also reserves "wait" and "evals" as job type names.
    @app.post(
        "/api/jobs/wait",
        summary="Wait For Jobs",
        tags=["Jobs"],
        openapi_extra=ALLOW_AGENT,
    )
    async def wait_for_jobs(request: WaitForJobsRequest) -> list[JobRecord]:
        """Block until ALL the given jobs reach a terminal state, then return
        their records in the order given. A pure observer: disconnecting never
        stops a job. The timeout covers the whole set. Empty `ids` returns an
        empty list. A paused job is not terminal, so a wait on one runs out
        the timeout (504)."""
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

    @app.post(
        "/api/jobs/evals/run",
        summary="Run Eval Job",
        tags=["Jobs"],
        status_code=201,
        response_model=CreateJobResponse,
        openapi_extra=_EVAL_JOB_APPROVAL,
    )
    async def run_eval_job(params: EvalJobParams) -> CreateJobResponse:
        """Start a background job that runs one split of an eval against one run
        config, and return at once. Items that already have a score for this eval
        config and run config are skipped. Poll `GET /api/jobs/{id}` or
        `POST /api/jobs/wait` for progress and the result."""
        # Entity loads are blocking IO, so run them off the event loop.
        await asyncio.to_thread(_check_eval_job_request, params)
        job = await job_registry.create(
            type_name=EvalJobWorker.type_name,
            params=params,
            project_id=params.project_id,
        )
        return CreateJobResponse(job_id=job.id, status=job.status)

    @app.post(
        "/api/jobs/{type}",
        summary="Create Job",
        tags=["Jobs"],
        status_code=201,
        response_model=CreateJobResponse | JobRecord,
        openapi_extra=ALLOW_AGENT,
    )
    async def create_job(
        type: Annotated[str, Path(description="The registered job type to run.")],
        request: CreateJobRequest,
        wait: Annotated[
            bool,
            Query(
                description="When true, block until the job reaches a terminal "
                "state and return the full JobRecord instead of CreateJobResponse."
            ),
        ] = False,
        timeout: Annotated[
            float | None,
            Query(
                ge=0,
                description="Seconds to wait when wait=true (504 on timeout). "
                "Omit to wait indefinitely.",
            ),
        ] = None,
    ) -> CreateJobResponse | JobRecord:
        try:
            worker = job_registry.worker_for(type)
        except JobOperationError:
            raise HTTPException(status_code=404, detail=f"Unknown job type: {type}")
        if worker.create_path is not None:
            raise HTTPException(
                status_code=400,
                detail=f"Create '{type}' jobs with POST {worker.create_path}.",
            )
        if not worker.generic_create_allowed:
            raise HTTPException(
                status_code=400,
                detail=f"'{type}' jobs cannot be created with this endpoint.",
            )

        try:
            validated = worker.params_model.model_validate(request.params)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors())

        job = await job_registry.create(
            type_name=type,
            params=validated,
            project_id=request.project_id or _project_id_from_params(validated),
            metadata=request.metadata,
        )
        if not wait:
            return CreateJobResponse(job_id=job.id, status=job.status)
        try:
            return await job_registry.wait(job.id, timeout=timeout)
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=504, detail="Job did not complete within the timeout."
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
        "/api/jobs/{id}/wait",
        summary="Wait For Job",
        tags=["Jobs"],
        openapi_extra=ALLOW_AGENT,
    )
    async def wait_for_job(
        id: Annotated[str, Path(description="The job id.")],
        timeout: Annotated[
            float | None,
            Query(
                ge=0,
                description="Seconds to wait before giving up (504 on timeout). "
                "Omit to wait indefinitely.",
            ),
        ] = None,
    ) -> JobRecord:
        """Block until the job reaches a terminal state, then return its record.

        A pure observer, like the SSE stream: if the client disconnects, uvicorn
        cancels this handler coroutine, which cancels the wait() await and tears
        down only the awaiter — the job's supervising task keeps running."""
        try:
            return await job_registry.wait(id, timeout=timeout)
        except JobNotFoundError:
            raise HTTPException(status_code=404, detail=f"Job not found: {id}")
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=504, detail="Job did not complete within the timeout."
            )

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
