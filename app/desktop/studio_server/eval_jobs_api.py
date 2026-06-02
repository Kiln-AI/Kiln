from __future__ import annotations

import asyncio
import json
import logging
from typing import Annotated, AsyncGenerator, Awaitable

from fastapi import FastAPI, HTTPException, Path, Query
from kiln_server.cancellable_streaming_response import CancellableStreamingResponse
from kiln_server.git_sync_decorators import no_write_lock
from kiln_server.utils.agent_checks.policy import agent_policy_require_approval

from .eval_api import (
    eval_config_from_id,
    get_all_run_configs,
    task_run_config_from_id,
)
from .jobs.events import JobEvent, KeepalivePing, iter_with_keepalive
from .jobs.models import BackgroundJobStatus, JobRecord
from .jobs.registry import JobOperationError, job_registry

logger = logging.getLogger(__name__)

# Keepalive cadence for the aggregate SSE stream. Mirrors jobs/api.py so a
# stalled subscription (e.g. all tracked jobs deleted out from under us) can't
# silently hold the HTTP connection open forever.
KEEPALIVE_SECONDS = 15.0


def _job_from_event(event: JobEvent) -> JobRecord | None:
    if event.event != "job":
        return None
    return JobRecord.model_validate(event.data)


def _aggregate_payload(jobs: dict[str, JobRecord]) -> str:
    progress = sum(j.progress.success for j in jobs.values())
    total = sum((j.progress.total or 0) for j in jobs.values())
    errors = sum(j.progress.error for j in jobs.values())
    return json.dumps({"progress": progress, "total": total, "errors": errors})


def _all_terminal(jobs: dict[str, JobRecord]) -> bool:
    return all(j.status.is_terminal for j in jobs.values())


def _schedule_cleanup_on_disconnect(job_ids: list[str]) -> None:
    """Fire-and-forget cleanup of this request's jobs on client disconnect.

    Called from the dying SSE generator's teardown path. The work runs as a
    single detached, ordered coroutine so it outlives the request's cancelled
    scope and so the ordering below is guaranteed within one task (rather than
    racing N independent tasks). Pausing a running job frees a concurrency slot
    that `_dispatch_pending` would immediately hand to a still-`pending` job,
    promoting it to RUNNING and running it to completion unattended — so we
    cancel the pending jobs FIRST (removing them from the queue) and only then
    pause the running ones.
    """
    task = asyncio.create_task(_cleanup(job_ids))
    task.add_done_callback(_log_cleanup_result)


async def _cleanup(job_ids: list[str]) -> None:
    # Snapshot the registry once into a dict so each id is an O(1) lookup rather
    # than a fresh O(N) list_jobs() scan per id. cancel() is the first thing
    # that can mutate these statuses, so the snapshot is accurate for the
    # pending pass below.
    records = {job.id: job for job in job_registry.list_jobs()}
    # Cancel pending jobs first: a pending->cancelled transition is a clean
    # terminal move that removes the job from the dispatch queue, so it can't be
    # promoted into a slot freed by the pauses that follow.
    for job_id in job_ids:
        record = records.get(job_id)
        if record is None or record.status != BackgroundJobStatus.PENDING:
            continue
        await _safe_op(job_registry.cancel(job_id), job_id, "cancel pending")
    # Then pause the running jobs (resumable; the idempotent eval jobs skip
    # already-scored items on resume). Re-snapshot once: cancelling the pending
    # jobs above may have advanced other jobs' statuses (and the JobRecord
    # objects are mutated in place, so re-reading the dict reflects that).
    records = {job.id: job for job in job_registry.list_jobs()}
    for job_id in job_ids:
        record = records.get(job_id)
        if record is None or record.status != BackgroundJobStatus.RUNNING:
            continue
        await _safe_op(job_registry.pause(job_id), job_id, "pause running")


async def _safe_op(coro: Awaitable[object], job_id: str, label: str) -> None:
    # A job that changed status mid-cleanup can raise JobOperationError; swallow
    # and log it so one stale job never aborts cleanup of the rest.
    try:
        await coro
    except JobOperationError:
        logger.info(
            "Skipping %s for eval job %s on disconnect (status changed)",
            label,
            job_id,
        )
    except Exception:
        logger.warning(
            "Failed to %s for eval job %s on client disconnect",
            label,
            job_id,
            exc_info=True,
        )


def _log_cleanup_result(task: asyncio.Task) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.warning("Eval job disconnect cleanup task failed", exc_info=True)


async def _aggregate_progress_stream(
    project_id: str, job_ids: list[str]
) -> AsyncGenerator[str, None]:
    """Aggregate per-job progress from the event bus into the legacy SSE format.

    Seeds from the bus snapshot, then folds in `job` events for our N ids,
    emitting `data: {"progress","total","errors"}` on change and a final
    `data: complete` once all N jobs are terminal. A client disconnect tears
    down this generator before completion — arriving as GeneratorExit at a
    suspended `yield` (CancellableStreamingResponse closes the body iterator)
    or as CancelledError at an await. Either way the `finally` runs without
    `completed` set, so the detached cleanup cancels still-pending jobs and
    pauses still-running ones. Normal completion (all terminal -> complete sent)
    sets `completed` and does not clean up.

    A tracked job deleted in the window between the route's create() and our
    subscribe() never appears here. We handle `deleted` events by dropping that
    id from `id_set` so the all-terminal check can still be reached.

    Keepalive goes through the shared `iter_with_keepalive` feeder-task helper:
    a quiet window yields a PING (emitted as an SSE comment) WITHOUT cancelling
    the underlying subscription. The old `asyncio.wait_for(__anext__())` form
    cancelled the in-flight pull on timeout, tearing down the subscription
    generator, ending the stream, and — because `completed` was still False —
    pausing/cancelling still-running jobs on a still-connected client after a
    single quiet window (e.g. a slow first model call). The feeder task keeps
    the subscription alive across pings; only a real disconnect (GeneratorExit /
    CancelledError) or normal completion ends the stream.
    """
    id_set = set(job_ids)
    tracked: dict[str, JobRecord] = {}
    subscription: AsyncGenerator[JobEvent, None] = job_registry.events.subscribe(
        type_name="eval",
        project_id=project_id,
    )
    completed = False
    try:
        async for item in iter_with_keepalive(subscription, KEEPALIVE_SECONDS):
            if isinstance(item, KeepalivePing):
                yield ": ping\n\n"
                continue
            event = item

            if event.event == "snapshot":
                for raw in event.data.get("jobs", []):
                    record = JobRecord.model_validate(raw)
                    if record.id in id_set:
                        tracked[record.id] = record
            elif event.event == "deleted":
                # A tracked job deleted out from under us would otherwise never
                # become terminal in `tracked`, wedging the all-terminal check
                # forever. Drop it from both the id set and tracked so progress
                # can complete.
                deleted_id = event.data.get("id")
                if deleted_id in id_set:
                    id_set.discard(deleted_id)
                    tracked.pop(deleted_id, None)
            else:
                record = _job_from_event(event)
                if record is None or record.id not in id_set:
                    continue
                tracked[record.id] = record

            if len(tracked) < len(id_set):
                continue

            yield f"data: {_aggregate_payload(tracked)}\n\n"

            if _all_terminal(tracked):
                yield "data: complete\n\n"
                completed = True
                return
    finally:
        # `completed` still gates cleanup: it is set only on the normal
        # all-terminal path. A keepalive ping is just a `continue` (never sets
        # it) and no longer ends the stream, so a quiet window can't trip
        # cleanup. A real disconnect (GeneratorExit at a yield / CancelledError)
        # leaves `completed` False, so still-pending jobs are cancelled and
        # still-running ones paused. The `async for` over the helper closes it
        # on exit, which cancels the feeder and aclose()s the subscription.
        if not completed:
            _schedule_cleanup_on_disconnect(job_ids)


async def run_eval_comparison_via_jobs(
    project_id: str,
    task_id: str,
    eval_id: str,
    eval_config_id: str,
    run_config_ids: list[str],
    all_run_configs: bool,
    spec_id: str | None = None,
) -> CancellableStreamingResponse:
    """Shared spawn-and-stream entry point for both the new `run_comparison_jobs`
    endpoint and the legacy `run_comparison` endpoint. Spawns one tracked job per
    run-config and streams aggregate progress in the legacy SSE shape so existing
    consumers (UI button, agent skill) keep working unchanged while the work is
    now visible in the jobs panel."""
    eval_config = eval_config_from_id(project_id, task_id, eval_id, eval_config_id)
    eval = eval_config.parent_eval()
    if eval is None:
        raise HTTPException(status_code=404, detail="Eval config has no parent eval.")

    if all_run_configs:
        run_config_id_list = [
            str(rc.id) for rc in get_all_run_configs(project_id, task_id)
        ]
    else:
        if len(run_config_ids) == 0:
            raise HTTPException(
                status_code=400,
                detail="No run config ids provided. At least one run config id is required.",
            )
        run_config_id_list = run_config_ids

    job_ids: list[str] = []
    for run_config_id in run_config_id_list:
        run_config = task_run_config_from_id(project_id, task_id, run_config_id)
        job = await job_registry.create(
            "eval",
            {
                "project_id": project_id,
                "task_id": task_id,
                "eval_id": str(eval.id),
                "eval_config_id": eval_config_id,
                "run_config_id": run_config_id,
            },
            project_id=project_id,
            metadata={
                "tag": {
                    "kind": "eval",
                    "task_id": task_id,
                    "spec_id": spec_id,
                    "eval_id": str(eval.id),
                    "eval_config_id": eval_config_id,
                    "run_config_id": run_config_id,
                },
                # Per-kind summary stashed at create time. Producers populate
                # `metadata.display` and the jobs widget renders it verbatim,
                # so the table stays generic across feature kinds.
                "display": {
                    "primary": f"Eval: {eval.name}",
                    "secondary": [
                        f"Judge: {eval_config.name}",
                        f"Run config: {run_config.name}",
                    ],
                },
            },
            # Lifecycle identity: an eval run targets a specific
            # (eval, eval_config, run_config) triple. Re-launching the same
            # triple supersedes the older row instead of stacking a new one.
            # EvalRunner is idempotent (skips already-scored items), so the
            # successor picks up wherever the predecessor left off.
            idempotency_key=f"{eval.id}:{eval_config_id}:{run_config_id}",
        )
        job_ids.append(job.id)

    return CancellableStreamingResponse(
        content=_aggregate_progress_stream(project_id, job_ids),
        media_type="text/event-stream",
    )


def connect_eval_jobs_api(app: FastAPI) -> None:
    # JS SSE client (EventSource) only does GET, so we mirror run_comparison's
    # GET shape and stream aggregate progress over N background eval jobs.
    @app.get(
        "/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/eval_config/{eval_config_id}/run_comparison_jobs",
        summary="Run Run Config Comparison (Jobs)",
        tags=["Evals"],
        openapi_extra=agent_policy_require_approval("Run eval comparison?"),
    )
    @no_write_lock
    async def run_eval_config_jobs(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        eval_id: Annotated[str, Path(description="The unique identifier of the eval.")],
        eval_config_id: Annotated[
            str, Path(description="The unique identifier of the eval configuration.")
        ],
        run_config_ids: Annotated[
            list[str],
            Query(description="The list of run configuration IDs to evaluate."),
        ] = [],
        all_run_configs: Annotated[
            bool,
            Query(
                description="Whether to evaluate all run configurations for the task."
            ),
        ] = False,
        spec_id: Annotated[
            str | None,
            Query(
                description="Optional spec id from the calling page; stored on the "
                "job's tag so the jobs widget can link back to the right page."
            ),
        ] = None,
    ) -> CancellableStreamingResponse:
        """Run an eval config against one or more run configs as background jobs
        (one job per run config) and stream aggregate progress via SSE.

        Mirrors run_comparison's params and SSE shape, but is backed by the
        background job system. Closing the stream cancels still-pending jobs and
        pauses still-running ones; the idempotent eval jobs are resumable and
        skip already-scored items."""
        return await run_eval_comparison_via_jobs(
            project_id=project_id,
            task_id=task_id,
            eval_id=eval_id,
            eval_config_id=eval_config_id,
            run_config_ids=run_config_ids,
            all_run_configs=all_run_configs,
            spec_id=spec_id,
        )
