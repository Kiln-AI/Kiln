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
from pydantic import BaseModel, Field, ValidationError

from . import error_log
from .events import JobEvent, KeepalivePing, iter_with_keepalive
from .models import BackgroundJobStatus, JobRecord
from .registry import (
    JobNotFoundError,
    JobOperationError,
    job_registry,
)
from .workers.eval import EvalJobWorker
from .workers.finetune import FinetuneJobWorker
from .workers.noop import NoopJobWorker

KEEPALIVE_SECONDS = 15.0

_JOB_MUTATION_APPROVAL = agent_policy_require_approval(
    "Allow agent to control background jobs (pause, resume, cancel, delete)?"
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
    idempotency_key: str | None = Field(
        default=None,
        description="Optional lifecycle identity. When set, any non-terminal "
        "job of the same type with the same key is torn down before this one "
        "is created, so re-running the same logical job doesn't pile up "
        "duplicate rows.",
    )


class CreateJobResponse(BaseModel):
    """Response returned when a job is created."""

    job_id: str = Field(description="The id of the newly created job.")
    status: BackgroundJobStatus = Field(
        description="The job's status immediately after creation."
    )


def _project_id_from_params(validated_params: BaseModel) -> str | None:
    return getattr(validated_params, "project_id", None)


def _format_sse(event: JobEvent) -> str:
    return f"event: {event.event}\ndata: {json.dumps(event.data)}\n\n"


async def _event_stream(
    job_id: str | None,
    type_name: str | None,
    project_id: str | None,
):
    """Pure-observer SSE generator.

    Subscribes to the registry event bus and forwards snapshot/job/deleted
    events, injecting a keepalive comment during quiet windows. Closing this
    generator (client disconnect, via CancellableStreamingResponse) only
    unsubscribes from the bus — it never touches any job's supervising task.
    Jobs keep running.

    The keepalive goes through the shared `iter_with_keepalive` feeder-task
    helper so a quiet-window timeout can never cancel (and thus tear down) the
    underlying subscription. Here that only saved a churny 15s reconnect, but it
    shares the fix with the eval stream, where a torn-down subscription would
    otherwise pause/cancel still-running jobs on a still-connected client.
    """
    subscription: AsyncGenerator[JobEvent, None] = job_registry.events.subscribe(
        job_id=job_id,
        type_name=type_name,
        project_id=project_id,
    )
    async for item in iter_with_keepalive(subscription, KEEPALIVE_SECONDS):
        if isinstance(item, KeepalivePing):
            yield ": ping\n\n"
        else:
            yield _format_sse(item)


def connect_jobs_api(app: FastAPI) -> None:
    # Register the workers this server exposes. register_type overwrites by
    # type_name, so repeated calls (e.g. multiple make_app() in tests) are safe.
    job_registry.register_type(NoopJobWorker)
    job_registry.register_type(EvalJobWorker)
    job_registry.register_type(FinetuneJobWorker)

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

        try:
            validated = worker.params_model.model_validate(request.params)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors())

        job = await job_registry.create(
            type_name=type,
            params=validated,
            project_id=request.project_id or _project_id_from_params(validated),
            metadata=request.metadata,
            idempotency_key=request.idempotency_key,
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
