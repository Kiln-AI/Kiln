from __future__ import annotations

import asyncio
import logging
import os
import secrets
import traceback
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from . import error_log
from .events import JobEventBus
from .models import (
    BackgroundJobStatus,
    JobContext,
    JobDerivedState,
    JobError,
    JobProgress,
    JobProgressUpdate,
    JobRecord,
    JobWorker,
    _utc_now,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_CONCURRENT = 10
MAX_CONCURRENT_ENV_VAR = "KILN_JOBS_MAX_CONCURRENT"

_JOB_ID_ALPHABET = "abcdefghijklmnopqrstuvwxyz234567"
_JOB_ID_LENGTH = 12

# Friendly adjective-noun name assigned to every job. Not unique (the id is the
# canonical key) — just a more human label than `j_kwyevdvylgaz`.
_JOB_NAME_ADJECTIVES = (
    "amber",
    "ancient",
    "bold",
    "brave",
    "bright",
    "calm",
    "clever",
    "cosmic",
    "crisp",
    "curious",
    "dapper",
    "eager",
    "fearless",
    "fierce",
    "gentle",
    "graceful",
    "happy",
    "humble",
    "jolly",
    "keen",
    "lively",
    "lucky",
    "merry",
    "mighty",
    "noble",
    "patient",
    "polished",
    "quiet",
    "quick",
    "radiant",
    "rapid",
    "rugged",
    "scarlet",
    "serene",
    "silent",
    "silver",
    "soaring",
    "spirited",
    "steady",
    "stellar",
    "stoic",
    "sturdy",
    "swift",
    "thoughtful",
    "twilight",
    "valiant",
    "vivid",
    "warm",
    "wise",
    "zesty",
)

_JOB_NAME_NOUNS = (
    "albatross",
    "anchor",
    "aurora",
    "beacon",
    "blossom",
    "boulder",
    "breeze",
    "canyon",
    "cedar",
    "chestnut",
    "comet",
    "cypress",
    "delta",
    "ember",
    "falcon",
    "forest",
    "fox",
    "geyser",
    "glacier",
    "harbor",
    "harvest",
    "horizon",
    "hummingbird",
    "ibex",
    "island",
    "lantern",
    "lighthouse",
    "lynx",
    "maple",
    "meadow",
    "monsoon",
    "moss",
    "mountain",
    "nebula",
    "ocean",
    "orchard",
    "otter",
    "panther",
    "pebble",
    "phoenix",
    "prairie",
    "puffin",
    "raven",
    "ridge",
    "river",
    "shadow",
    "spruce",
    "summit",
    "tundra",
    "willow",
)


class JobNotFoundError(Exception):
    pass


class JobOperationError(Exception):
    """Raised for invalid lifecycle operations (e.g. pause a non-running job).

    Phase 2 maps these to 409 Conflict.
    """


def _new_job_id() -> str:
    suffix = "".join(secrets.choice(_JOB_ID_ALPHABET) for _ in range(_JOB_ID_LENGTH))
    return f"j_{suffix}"


def _new_job_name() -> str:
    return f"{secrets.choice(_JOB_NAME_ADJECTIVES)}-{secrets.choice(_JOB_NAME_NOUNS)}"


def _resolve_max_concurrent(explicit: int | None) -> int:
    if explicit is not None:
        return explicit
    raw = os.environ.get(MAX_CONCURRENT_ENV_VAR)
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            pass
    return DEFAULT_MAX_CONCURRENT


class JobRegistry:
    """In-memory registry owning job lifecycle, concurrency, and reconciliation.

    Singleton per process. The in-memory index is the only store — no disk
    persistence of state. Supervising tasks are owned here and decoupled from any
    HTTP connection.
    """

    def __init__(self, max_concurrent: int | None = None) -> None:
        self._max_concurrent = _resolve_max_concurrent(max_concurrent)
        self._workers: dict[str, JobWorker] = {}
        self._jobs: dict[str, JobRecord] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._pending_ids: list[str] = []
        self._cancel_intent: set[str] = set()
        self._pause_intent: set[str] = set()
        # Job ids whose supervising task received a real (delivered-to-a-live-
        # task) cancellation. Distinguishes "worker swallowed a cancel" from
        # "worker finished before any cancel landed" when the worker returns
        # normally — the former must transition to paused/cancelled, the latter
        # must keep its succeeded result.
        self._cancel_delivered: set[str] = set()
        # Per-job completion events for awaiters (registry.wait). Created lazily
        # by wait(); set by _emit() on the terminal transition; reclaimed in
        # delete(). Bounded to one event per waited job, tracking the same
        # lifecycle as the JobRecord. Shared across all awaiters of a job so one
        # awaiter cancelling its wait() leaves the event (and the task) untouched.
        self._completion_events: dict[str, asyncio.Event] = {}
        self._running_count = 0
        self.events = JobEventBus(snapshot_provider=self._snapshot)

    # -- registration --------------------------------------------------------

    def register_type(self, worker_cls: type[JobWorker]) -> None:
        worker = worker_cls()
        self._workers[worker_cls.type_name] = worker

    def worker_for(self, type_name: str) -> JobWorker:
        worker = self._workers.get(type_name)
        if worker is None:
            raise JobOperationError(f"Unknown job type: {type_name}")
        return worker

    # -- snapshots / reads ---------------------------------------------------

    def _snapshot(self) -> list[JobRecord]:
        return list(self._jobs.values())

    def _require(self, job_id: str) -> JobRecord:
        job = self._jobs.get(job_id)
        if job is None:
            raise JobNotFoundError(job_id)
        return job

    async def get(self, job_id: str) -> JobRecord | None:
        job = self._jobs.get(job_id)
        if job is None:
            return None
        await self._reconcile(job, emit_on_change=True)
        return job

    def run_id_for(self, job_id: str) -> str | None:
        """Current run_id for a job, or None if unknown. A plain read — no
        reconciliation (used by the best-effort errors endpoint)."""
        job = self._jobs.get(job_id)
        return job.run_id if job is not None else None

    def list_jobs(
        self,
        status: BackgroundJobStatus | None = None,
        type_name: str | None = None,
        project_id: str | None = None,
        since: datetime | None = None,
        limit: int | None = None,
    ) -> list[JobRecord]:
        records = list(self._jobs.values())
        if status is not None:
            records = [r for r in records if r.status == status]
        if type_name is not None:
            records = [r for r in records if r.type == type_name]
        if project_id is not None:
            records = [r for r in records if r.project_id == project_id]
        if since is not None:
            records = [r for r in records if r.created_at >= since]
        records.sort(key=lambda r: r.created_at, reverse=True)
        if limit is not None:
            records = records[:limit]
        return records

    # -- create --------------------------------------------------------------

    async def create(
        self,
        type_name: str,
        params: dict[str, Any] | BaseModel,
        project_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> JobRecord:
        worker = self.worker_for(type_name)
        validated = self._validate_params(worker, params)
        if idempotency_key is not None:
            await self._supersede_matching(type_name, idempotency_key)
        job_id = self._fresh_job_id()
        job = JobRecord(
            id=job_id,
            name=_new_job_name(),
            type=type_name,
            status=BackgroundJobStatus.PENDING,
            params=validated.model_dump(mode="json"),
            metadata=metadata or {},
            project_id=project_id,
            supports_pause=worker.supports_pause,
            supports_cancel=worker.supports_cancel,
            idempotency_key=idempotency_key,
        )
        self._jobs[job_id] = job
        self._pending_ids.append(job_id)
        self._emit(job)
        self._dispatch_pending()
        return job

    async def _supersede_matching(self, type_name: str, key: str) -> None:
        """Tear down any supersedable jobs with the same (type, idempotency_key).

        Supersedable = everything except FAILED. Failed jobs carry the previous
        attempt's error summary that the user may still need to inspect while
        retrying, so they stay in the panel. Pending/running/paused get cancelled
        and removed; cancelled and succeeded jobs are pure history that the
        fresh launch makes obsolete — the source-of-truth EvalRuns etc. persist
        independently, so dropping the succeeded row loses no real data.

        Idempotent workers compute their state from source-of-truth entities,
        so a fresh job will pick up wherever the superseded one left off —
        there's no progress to preserve. We cancel AND remove rather than
        leaving a Cancelled row behind, since the user's mental model is
        "Run this again," not "Cancel the old one and start a new one."
        """
        targets = [
            j
            for j in self._jobs.values()
            if j.type == type_name
            and j.idempotency_key == key
            and j.status != BackgroundJobStatus.FAILED
        ]
        for old in targets:
            await self._teardown_superseded(old)

    async def _teardown_superseded(self, job: JobRecord) -> None:
        # Mirror the lifecycle paths in cancel() — but unconditionally, since
        # this is a registry-internal teardown rather than a user action.
        # `supports_cancel=False` workers must still be replaceable here, or
        # idempotency would silently break for them.
        job_id = job.id
        if job.status == BackgroundJobStatus.PENDING:
            self._remove_pending(job_id)
        elif job.status == BackgroundJobStatus.RUNNING:
            self._cancel_intent.add(job_id)
            await self._cancel_task(job_id)
        # PAUSED needs no task teardown — there's no running task to cancel.
        # In all paths, the record is removed entirely (same cleanup as delete())
        # so the panel stays clean and resources are released.
        self._jobs.pop(job_id, None)
        self._remove_pending(job_id)
        self._completion_events.pop(job_id, None)
        if job.run_id is not None:
            error_log.delete_errors(job.run_id)
        self.events.publish_deleted(job_id, job.type, job.project_id)

    def _fresh_job_id(self) -> str:
        job_id = _new_job_id()
        while job_id in self._jobs:
            job_id = _new_job_id()
        return job_id

    def _validate_params(
        self, worker: JobWorker, params: dict[str, Any] | BaseModel
    ) -> BaseModel:
        if isinstance(params, worker.params_model):
            return params
        if isinstance(params, BaseModel):
            params = params.model_dump()
        return worker.params_model.model_validate(params)

    # -- dispatch / supervision ---------------------------------------------

    def _dispatch_pending(self) -> None:
        while self._running_count < self._max_concurrent and self._pending_ids:
            job_id = self._pending_ids.pop(0)
            job = self._jobs.get(job_id)
            if job is None or job.status != BackgroundJobStatus.PENDING:
                continue
            self._launch(job)

    def _launch(self, job: JobRecord) -> None:
        worker = self.worker_for(job.type)
        run_id = str(uuid.uuid4())
        job.run_id = run_id
        job.status = BackgroundJobStatus.RUNNING
        job.started_at = _utc_now()
        self._touch(job)
        self._running_count += 1
        self._emit(job)
        task = asyncio.create_task(self._supervise(job.id, worker, run_id))
        self._tasks[job.id] = task

    async def _supervise(self, job_id: str, worker: JobWorker, run_id: str) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            return
        params = worker.params_model.model_validate(job.params)
        ctx = self._build_context(job_id, run_id, worker)
        try:
            try:
                await self._reconcile(job, emit_on_change=True)
                if job.status == BackgroundJobStatus.SUCCEEDED:
                    return
                result = await worker.run(params, ctx)
                # The cancellation transition is unconditional (functional_spec
                # §2): a worker that catches CancelledError for cleanup and then
                # returns normally — even one that calls task.uncancel() so it is
                # never re-raised — must still land in paused/cancelled, not
                # succeeded. The registry enforces this off its own delivery
                # record rather than trusting the worker to re-raise. A worker
                # that finished naturally before any cancel landed has no
                # delivery recorded, so its result stands.
                if job_id in self._cancel_delivered:
                    self._finish_cancelled_or_paused(job)
                else:
                    self._finish_succeeded(job, result)
            except asyncio.CancelledError:
                self._finish_cancelled_or_paused(job)
                raise
            except Exception as exc:
                self._finish_failed(job, run_id, exc)
        finally:
            self._release_slot(job_id)

    def _build_context(self, job_id: str, run_id: str, worker: JobWorker) -> JobContext:
        async def report_progress(update: JobProgressUpdate) -> None:
            job = self._jobs.get(job_id)
            if job is None or job.run_id != run_id:
                return
            job.progress = JobProgress(
                total=update.total if update.total is not None else job.progress.total,
                success=update.success,
                error=update.error,
                message=update.message
                if update.message is not None
                else job.progress.message,
            )
            self._touch(job)
            self._emit(job)

        async def report_progress_detail(detail: BaseModel) -> None:
            job = self._jobs.get(job_id)
            if job is None or job.run_id != run_id:
                return
            # Guard the worker's contract: the detail must be the model the
            # worker declared, so progress_detail's shape is predictable for
            # the frontend that casts it.
            expected = worker.progress_model
            if expected is not None and not isinstance(detail, expected):
                raise TypeError(
                    f"report_progress_detail expected {expected.__name__}, "
                    f"got {type(detail).__name__}"
                )
            job.progress_detail = detail.model_dump(mode="json")
            self._touch(job)
            self._emit(job)

        async def report_error(message: str, extra: dict[str, Any]) -> None:
            error_log.append_error(run_id, {"error_message": message, **extra})

        return JobContext(
            job_id, run_id, report_progress, report_progress_detail, report_error
        )

    def _finish_succeeded(self, job: JobRecord, result: BaseModel) -> None:
        job.status = BackgroundJobStatus.SUCCEEDED
        job.result = result.model_dump(mode="json")
        job.ended_at = _utc_now()
        self._touch(job)
        self._emit(job)

    def _finish_failed(self, job: JobRecord, run_id: str, exc: Exception) -> None:
        job.status = BackgroundJobStatus.FAILED
        job.error = JobError(error=str(exc) or exc.__class__.__name__)
        job.ended_at = _utc_now()
        self._touch(job)
        error_log.append_error(
            run_id,
            {
                "error_message": str(exc) or exc.__class__.__name__,
                "traceback": "".join(
                    traceback.format_exception(type(exc), exc, exc.__traceback__)
                ),
                "fatal": True,
            },
        )
        self._emit(job)

    def _finish_cancelled_or_paused(self, job: JobRecord) -> None:
        if job.id in self._pause_intent:
            job.status = BackgroundJobStatus.PAUSED
        else:
            job.status = BackgroundJobStatus.CANCELLED
            job.ended_at = _utc_now()
        self._touch(job)
        self._emit(job)

    # -- lifecycle controls --------------------------------------------------

    async def pause(self, job_id: str) -> JobRecord:
        job = self._require(job_id)
        if not job.supports_pause:
            raise JobOperationError(f"Job type '{job.type}' does not support pause")
        if job.status != BackgroundJobStatus.RUNNING:
            raise JobOperationError(
                f"Cannot pause a job in status '{job.status.value}'"
            )
        self._pause_intent.add(job_id)
        await self._cancel_task(job_id)
        # If run() completed naturally during the cancel await, the job is
        # already terminal — leave that state intact rather than forcing paused.
        if job.status.is_terminal:
            return job
        if job.status != BackgroundJobStatus.PAUSED:
            job.status = BackgroundJobStatus.PAUSED
            self._touch(job)
        worker = self.worker_for(job.type)
        params = worker.params_model.model_validate(job.params)
        derived = await worker.compute_state(params)
        self._apply_derived(job, derived)
        self._emit(job)
        return job

    async def resume(self, job_id: str) -> JobRecord:
        job = self._require(job_id)
        if job.status != BackgroundJobStatus.PAUSED:
            raise JobOperationError(
                f"Cannot resume a job in status '{job.status.value}'"
            )
        worker = self.worker_for(job.type)
        params = worker.params_model.model_validate(job.params)
        derived = await worker.compute_state(params)
        if derived is not None and derived.is_complete:
            self._apply_derived(job, derived)
            job.status = BackgroundJobStatus.SUCCEEDED
            job.ended_at = _utc_now()
            self._touch(job)
            self._emit(job)
            return job
        self._apply_derived(job, derived)
        job.status = BackgroundJobStatus.PENDING
        self._touch(job)
        self._pending_ids.append(job_id)
        self._emit(job)
        self._dispatch_pending()
        return job

    async def cancel(self, job_id: str) -> JobRecord:
        job = self._require(job_id)
        if not job.supports_cancel:
            raise JobOperationError(f"Job type '{job.type}' does not support cancel")
        if job.status.is_terminal:
            raise JobOperationError(
                f"Cannot cancel a job in status '{job.status.value}'"
            )
        if job.status == BackgroundJobStatus.PENDING:
            self._remove_pending(job_id)
            job.status = BackgroundJobStatus.CANCELLED
            job.ended_at = _utc_now()
            self._touch(job)
            self._emit(job)
            return job
        if job.status == BackgroundJobStatus.PAUSED:
            job.status = BackgroundJobStatus.CANCELLED
            job.ended_at = _utc_now()
            self._touch(job)
            self._emit(job)
            return job
        self._cancel_intent.add(job_id)
        await self._cancel_task(job_id)
        if not job.status.is_terminal:
            job.status = BackgroundJobStatus.CANCELLED
            job.ended_at = _utc_now()
            self._touch(job)
            self._emit(job)
        return self._jobs[job_id]

    async def delete(self, job_id: str) -> None:
        job = self._require(job_id)
        if not job.status.is_terminal:
            raise JobOperationError(
                f"Cannot delete a job in status '{job.status.value}'"
            )
        self._jobs.pop(job_id, None)
        self._remove_pending(job_id)
        self._completion_events.pop(job_id, None)
        if job.run_id is not None:
            error_log.delete_errors(job.run_id)
        self.events.publish_deleted(job_id, job.type, job.project_id)

    async def _cancel_task(self, job_id: str) -> None:
        task = self._tasks.get(job_id)
        if task is None:
            return
        # cancel() returns True only if the request landed on a not-yet-done
        # task — i.e. the cancellation is actually delivered to the worker. If
        # it returns False the worker already finished naturally; we must not
        # override that terminal result.
        if task.cancel():
            self._cancel_delivered.add(job_id)
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            # The worker raised while we awaited its cancellation. _supervise
            # already routed this to the failed/terminal state and logged it;
            # we only debug-log here so it isn't silently discarded.
            logger.debug(
                "Worker for job %s raised during cancel await", job_id, exc_info=True
            )
        # If the task was cancelled before its coroutine body ever ran, its own
        # finally never executed, so reclaim the slot here. Idempotent: whoever
        # pops job_id from _tasks first owns the single decrement.
        self._release_slot(job_id)

    def _release_slot(self, job_id: str) -> None:
        if self._tasks.pop(job_id, None) is None:
            return
        self._cancel_intent.discard(job_id)
        self._pause_intent.discard(job_id)
        self._cancel_delivered.discard(job_id)
        self._running_count -= 1
        self._dispatch_pending()

    def _remove_pending(self, job_id: str) -> None:
        try:
            self._pending_ids.remove(job_id)
        except ValueError:
            pass

    # -- reconciliation ------------------------------------------------------

    async def _reconcile(self, job: JobRecord, emit_on_change: bool) -> bool:
        worker = self._workers.get(job.type)
        if worker is None:
            return False
        params = worker.params_model.model_validate(job.params)
        derived = await worker.compute_state(params)
        if derived is None:
            return False
        changed = self._apply_derived(job, derived)
        if derived.is_complete and not job.status.is_terminal:
            job.status = BackgroundJobStatus.SUCCEEDED
            job.ended_at = _utc_now()
            self._touch(job)
            changed = True
        if changed and emit_on_change:
            self._emit(job)
        return changed

    def _apply_derived(self, job: JobRecord, derived: JobDerivedState | None) -> bool:
        if derived is None:
            return False
        new_progress = JobProgress(
            total=derived.total if derived.total is not None else job.progress.total,
            success=derived.success,
            # error=None means "no opinion" — preserve the prior runtime count
            # so View Errors stays available across a pause when the worker's
            # source-of-truth entities don't track failures.
            error=derived.error if derived.error is not None else job.progress.error,
            message=derived.message
            if derived.message is not None
            else job.progress.message,
        )
        before = job.progress.model_dump(exclude={"updated_at"})
        after = new_progress.model_dump(exclude={"updated_at"})
        if before == after:
            return False
        job.progress = new_progress
        self._touch(job)
        return True

    # -- helpers -------------------------------------------------------------

    def _touch(self, job: JobRecord) -> None:
        job.updated_at = _utc_now()

    def _emit(self, job: JobRecord) -> None:
        self.events.publish_job(job)
        if job.status.is_terminal:
            ev = self._completion_events.get(job.id)
            if ev is not None:
                ev.set()

    # -- await completion ----------------------------------------------------

    async def wait(self, job_id: str, timeout: float | None = None) -> JobRecord:
        """Observe a job until it reaches a terminal state, then return its record.

        A pure observer, mirroring the SSE stream's decoupling: cancelling this
        await (caller drops off / client disconnects) tears down only the awaiter
        — the job's supervising task is owned by the registry and keeps running.
        Multi-waiter safe: all awaiters of a job share one Event. timeout=None
        waits indefinitely; on timeout asyncio.wait_for raises
        asyncio.TimeoutError, which propagates to the caller.
        """
        job = self._require(job_id)
        # Create the event before the terminal check so there's no race window:
        # single-threaded asyncio guarantees no await between setdefault and the
        # check, and _emit only sets the event if it already exists here.
        ev = self._completion_events.setdefault(job_id, asyncio.Event())
        if job.status.is_terminal:
            return job
        await asyncio.wait_for(ev.wait(), timeout)
        return job


job_registry = JobRegistry()
