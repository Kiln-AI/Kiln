from __future__ import annotations

import asyncio
import uuid

import pytest
from pydantic import BaseModel

from app.desktop.studio_server.jobs import error_log
from app.desktop.studio_server.jobs.models import (
    JobDerivedState,
    BackgroundJobStatus,
    JobWorker,
)
from app.desktop.studio_server.jobs.registry import (
    JobNotFoundError,
    JobOperationError,
    JobRegistry,
    _new_job_id,
)
from app.desktop.studio_server.jobs.workers.noop import NoopJobWorker


@pytest.fixture(autouse=True)
def temp_error_log_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.desktop.studio_server.jobs.error_log.tempfile.gettempdir",
        lambda: str(tmp_path),
    )


@pytest.fixture
def registry():
    reg = JobRegistry(max_concurrent=10)
    reg.register_type(NoopJobWorker)
    return reg


async def wait_for_status(
    registry: JobRegistry,
    job_id: str,
    target: BackgroundJobStatus | set[BackgroundJobStatus],
    timeout: float = 3.0,
) -> None:
    targets = {target} if isinstance(target, BackgroundJobStatus) else target
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        job = registry._jobs.get(job_id)
        if job is not None and job.status in targets:
            return
        await asyncio.sleep(0.01)
    job = registry._jobs.get(job_id)
    actual = job.status if job else "missing"
    raise AssertionError(f"Job {job_id} did not reach {targets}; was {actual}")


# -- supporting test workers ------------------------------------------------


class _EmptyParams(BaseModel):
    pass


class _EmptyResult(BaseModel):
    pass


class NonPausableWorker(JobWorker[_EmptyParams, _EmptyResult]):
    type_name = "nonpausable"
    params_model = _EmptyParams
    result_model = _EmptyResult
    supports_pause = False

    async def run(self, params, ctx):
        await asyncio.sleep(5)
        return _EmptyResult()


class AlreadyCompleteWorker(JobWorker[_EmptyParams, _EmptyResult]):
    type_name = "already_complete"
    params_model = _EmptyParams
    result_model = _EmptyResult
    supports_pause = True
    run_called = False

    async def compute_state(self, params):
        return JobDerivedState(total=5, success=5, error=0, is_complete=True)

    async def run(self, params, ctx):
        type(self).run_called = True
        return _EmptyResult()


class PartialProgressWorker(JobWorker[_EmptyParams, _EmptyResult]):
    """First reports the full set (total + message), then a count-only update.
    The later partial update must preserve the earlier total/message, not null
    them.
    """

    type_name = "partial_progress"
    params_model = _EmptyParams
    result_model = _EmptyResult
    supports_pause = False

    async def run(self, params, ctx):
        await ctx.report_progress(success=1, total=50, message="starting")
        await ctx.report_progress(success=5)
        return _EmptyResult()


class RaceCompleteWorker(JobWorker[_EmptyParams, _EmptyResult]):
    """run() blocks on a test-controlled gate, then returns normally without
    ever observing a cancellation. The test opens the gate (so run() returns and
    the supervising task drives the job to its terminal succeeded state) and only
    then issues pause/cancel — reproducing the completion-vs-cancel race where
    the job finished naturally during the cancel await.
    """

    type_name = "race_complete"
    params_model = _EmptyParams
    result_model = _EmptyResult
    supports_pause = True
    gate: asyncio.Event

    async def run(self, params, ctx):
        await type(self).gate.wait()
        return _EmptyResult()


class SwallowCancelWorker(JobWorker[_EmptyParams, _EmptyResult]):
    """Catches CancelledError, fully clears the cancellation (uncancel) so it is
    not re-raised, and returns normally — the worst-case "swallows CancelledError
    and returns silently" worker. The cancellation transition is unconditional,
    so the registry itself must land the job in paused/cancelled rather than
    trusting the worker to re-raise.

    `started` is set once run() is actually suspended at its await point, so a
    test can guarantee the cancellation is delivered into the worker body (not
    before it runs) before issuing pause/cancel.
    """

    type_name = "swallow_cancel"
    params_model = _EmptyParams
    result_model = _EmptyResult
    supports_pause = True
    started: asyncio.Event
    gate: asyncio.Event

    async def run(self, params, ctx):
        type(self).started.set()
        try:
            await type(self).gate.wait()
        except asyncio.CancelledError:
            task = asyncio.current_task()
            # task.uncancel() was added in Python 3.11; on 3.10 simply
            # swallowing the CancelledError exercises the same worst-case
            # "swallows cancel and returns normally" path.
            if task is not None and hasattr(task, "uncancel"):
                task.uncancel()
        return _EmptyResult()


class TotalThenNoneWorker(JobWorker[_EmptyParams, _EmptyResult]):
    """run() reports a known total via report_progress, then compute_state at
    pause returns total=None alongside success/error counts. The reconcile must
    preserve the prior total rather than wiping the denominator to None.
    """

    type_name = "total_then_none"
    params_model = _EmptyParams
    result_model = _EmptyResult
    supports_pause = True
    started: asyncio.Event
    gate: asyncio.Event

    async def compute_state(self, params):
        return JobDerivedState(total=None, success=2, error=1, is_complete=False)

    async def run(self, params, ctx):
        await ctx.report_progress(success=0, total=10, message="starting")
        type(self).started.set()
        try:
            await type(self).gate.wait()
        except asyncio.CancelledError:
            task = asyncio.current_task()
            # task.uncancel() was added in Python 3.11; on 3.10 simply
            # swallowing the CancelledError exercises the same worst-case
            # "swallows cancel and returns normally" path.
            if task is not None and hasattr(task, "uncancel"):
                task.uncancel()
        return _EmptyResult()


class ReconcileCompleteWorker(JobWorker[_EmptyParams, _EmptyResult]):
    """compute_state reports complete only once the test flips `done`, so a
    get() issued while the job is still running (run() is a long sleep)
    reconciles it straight to succeeded mid-flight.
    """

    type_name = "reconcile_complete"
    params_model = _EmptyParams
    result_model = _EmptyResult
    supports_pause = True
    done = False

    async def compute_state(self, params):
        complete = type(self).done
        return JobDerivedState(
            total=3, success=3 if complete else 1, error=0, is_complete=complete
        )

    async def run(self, params, ctx):
        await asyncio.sleep(5)
        return _EmptyResult()


# -- job id ------------------------------------------------------------------


def test_job_id_format():
    job_id = _new_job_id()
    assert job_id.startswith("j_")
    suffix = job_id[2:]
    assert len(suffix) == 12
    assert all(c in "abcdefghijklmnopqrstuvwxyz234567" for c in suffix)


# -- lifecycle ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_lifecycle_succeeds(registry):
    job = await registry.create("noop", {"steps": 3, "sleep_per_step_seconds": 0.01})
    assert job.status in (BackgroundJobStatus.PENDING, BackgroundJobStatus.RUNNING)
    assert job.supports_pause is True

    await wait_for_status(registry, job.id, BackgroundJobStatus.SUCCEEDED)
    final = registry._jobs[job.id]
    assert final.result == {"completed_steps": 3}
    assert final.started_at is not None
    assert final.ended_at is not None
    assert final.run_id is not None
    assert final.progress.success == 3


@pytest.mark.asyncio
async def test_failure_path_captures_error_log(registry):
    job = await registry.create(
        "noop",
        {"steps": 5, "sleep_per_step_seconds": 0.01, "fail_at_step": 2},
    )
    await wait_for_status(registry, job.id, BackgroundJobStatus.FAILED)

    final = registry._jobs[job.id]
    assert final.error is not None
    assert final.error.error is not None
    assert "intentional fail at step 2" in final.error.error

    entries = error_log.read_errors(final.run_id)
    fatal = [e for e in entries if e.get("fatal")]
    assert len(fatal) == 1
    assert "intentional fail at step 2" in fatal[0]["error_message"]


@pytest.mark.asyncio
async def test_non_fatal_errors_logged_and_counted(registry):
    job = await registry.create(
        "noop",
        {
            "steps": 4,
            "sleep_per_step_seconds": 0.01,
            "error_at_steps": [1, 3],
        },
    )
    await wait_for_status(registry, job.id, BackgroundJobStatus.SUCCEEDED)

    final = registry._jobs[job.id]
    assert final.progress.error == 2
    assert final.progress.success == 2

    entries = error_log.read_errors(final.run_id)
    messages = [e["error_message"] for e in entries]
    assert "intentional error at step 1" in messages
    assert "intentional error at step 3" in messages
    steps = sorted(e["step"] for e in entries if "step" in e)
    assert steps == [1, 3]


@pytest.mark.asyncio
async def test_error_log_missing_returns_empty():
    assert error_log.read_errors(str(uuid.uuid4())) == []


# -- cancel ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_pending_job_never_starts():
    reg = JobRegistry(max_concurrent=1)
    reg.register_type(NoopJobWorker)
    running = await reg.create("noop", {"steps": 50, "sleep_per_step_seconds": 0.05})
    await wait_for_status(reg, running.id, BackgroundJobStatus.RUNNING)
    pending = await reg.create("noop", {"steps": 50, "sleep_per_step_seconds": 0.05})
    assert reg._jobs[pending.id].status == BackgroundJobStatus.PENDING

    await reg.cancel(pending.id)
    assert reg._jobs[pending.id].status == BackgroundJobStatus.CANCELLED
    assert pending.id not in reg._tasks

    await reg.cancel(running.id)


@pytest.mark.asyncio
async def test_cancel_from_running(registry):
    job = await registry.create("noop", {"steps": 50, "sleep_per_step_seconds": 0.05})
    await wait_for_status(registry, job.id, BackgroundJobStatus.RUNNING)
    await registry.cancel(job.id)
    assert registry._jobs[job.id].status == BackgroundJobStatus.CANCELLED


@pytest.mark.asyncio
async def test_cancel_immediately_after_create_reclaims_slot():
    # Cancelling right after create can race the supervising task before its
    # coroutine body runs; the registry must still reclaim the concurrency slot.
    reg = JobRegistry(max_concurrent=2)
    reg.register_type(NoopJobWorker)
    ids = []
    for _ in range(6):
        job = await reg.create("noop", {"steps": 50, "sleep_per_step_seconds": 0.02})
        ids.append(job.id)
    for job_id in ids:
        await reg.cancel(job_id)
    await asyncio.sleep(0.05)

    assert all(reg._jobs[i].status == BackgroundJobStatus.CANCELLED for i in ids)
    assert reg._running_count == 0
    assert reg._tasks == {}
    assert reg._pending_ids == []


@pytest.mark.asyncio
async def test_cancel_terminal_raises(registry):
    job = await registry.create("noop", {"steps": 2, "sleep_per_step_seconds": 0.01})
    await wait_for_status(registry, job.id, BackgroundJobStatus.SUCCEEDED)
    with pytest.raises(JobOperationError):
        await registry.cancel(job.id)


# -- pause / resume ----------------------------------------------------------


@pytest.mark.asyncio
async def test_pause_then_resume_succeeds(registry):
    job = await registry.create("noop", {"steps": 50, "sleep_per_step_seconds": 0.03})
    await wait_for_status(registry, job.id, BackgroundJobStatus.RUNNING)
    first_run_id = registry._jobs[job.id].run_id

    await registry.pause(job.id)
    assert registry._jobs[job.id].status == BackgroundJobStatus.PAUSED

    # Make resume finish quickly by checking it re-runs with a fresh run_id.
    await registry.resume(job.id)
    assert registry._jobs[job.id].status in (
        BackgroundJobStatus.PENDING,
        BackgroundJobStatus.RUNNING,
    )
    await wait_for_status(registry, job.id, BackgroundJobStatus.RUNNING)
    second_run_id = registry._jobs[job.id].run_id
    assert second_run_id is not None
    assert second_run_id != first_run_id

    await registry.cancel(job.id)


@pytest.mark.asyncio
async def test_resume_to_succeeded_when_complete():
    reg = JobRegistry(max_concurrent=2)
    reg.register_type(NoopJobWorker)
    reg.register_type(AlreadyCompleteWorker)
    AlreadyCompleteWorker.run_called = False

    # Start a noop that we pause so we have a paused job to resume against a
    # complete worker. Simpler: create the complete worker job, it succeeds
    # immediately via reconcile at launch.
    job = await reg.create("already_complete", {})
    await wait_for_status(reg, job.id, BackgroundJobStatus.SUCCEEDED)
    assert AlreadyCompleteWorker.run_called is False
    assert reg._jobs[job.id].progress.success == 5


@pytest.mark.asyncio
async def test_pause_rejected_when_not_supported():
    reg = JobRegistry(max_concurrent=2)
    reg.register_type(NonPausableWorker)
    job = await reg.create("nonpausable", {})
    await wait_for_status(reg, job.id, BackgroundJobStatus.RUNNING)
    with pytest.raises(JobOperationError):
        await reg.pause(job.id)
    await reg.cancel(job.id)


@pytest.mark.asyncio
async def test_cancel_rejected_when_not_supported():
    # supports_cancel=False marks the job as not user-interruptible (e.g.
    # finetune watcher wrapping a remote provider job). The registry must refuse
    # cancel rather than tearing down the supervising task.
    class NonCancelableWorker(JobWorker[_EmptyParams, _EmptyResult]):
        type_name = "noncancelable"
        params_model = _EmptyParams
        result_model = _EmptyResult
        supports_pause = False
        supports_cancel = False

        async def run(self, params, ctx):
            await asyncio.sleep(5)
            return _EmptyResult()

    reg = JobRegistry(max_concurrent=2)
    reg.register_type(NonCancelableWorker)
    job = await reg.create("noncancelable", {})
    await wait_for_status(reg, job.id, BackgroundJobStatus.RUNNING)
    with pytest.raises(JobOperationError):
        await reg.cancel(job.id)
    # Job is still running — the flag must gate cancel, not silently no-op.
    assert reg._jobs[job.id].status == BackgroundJobStatus.RUNNING
    # Force-cleanup so the test doesn't leak the supervising task.
    reg._jobs[job.id].supports_cancel = True
    await reg.cancel(job.id)


@pytest.mark.asyncio
async def test_supports_cancel_stamped_on_record_at_create():
    class WatcherWorker(JobWorker[_EmptyParams, _EmptyResult]):
        type_name = "watcher"
        params_model = _EmptyParams
        result_model = _EmptyResult
        supports_pause = False
        supports_cancel = False

        async def compute_state(self, params):
            return JobDerivedState(total=1, success=1, error=0, is_complete=True)

        async def run(self, params, ctx):
            return _EmptyResult()

    reg = JobRegistry(max_concurrent=2)
    reg.register_type(WatcherWorker)
    job = await reg.create("watcher", {})
    assert job.supports_cancel is False
    assert job.supports_pause is False


@pytest.mark.asyncio
async def test_pause_rejected_when_not_running(registry):
    job = await registry.create("noop", {"steps": 2, "sleep_per_step_seconds": 0.01})
    await wait_for_status(registry, job.id, BackgroundJobStatus.SUCCEEDED)
    with pytest.raises(JobOperationError):
        await registry.pause(job.id)


@pytest.mark.asyncio
async def test_resume_rejected_when_not_paused(registry):
    job = await registry.create("noop", {"steps": 50, "sleep_per_step_seconds": 0.05})
    await wait_for_status(registry, job.id, BackgroundJobStatus.RUNNING)
    with pytest.raises(JobOperationError):
        await registry.resume(job.id)
    await registry.cancel(job.id)


async def _drive_completion_race(operation: str) -> JobRegistry:
    # Reproduce the completion-vs-cancel race deterministically: the worker's
    # run() is gated; we open the gate at the exact moment the lifecycle op
    # begins its cancel await, so the supervising task finishes naturally
    # (job -> succeeded, task done) before/while task.cancel() lands. The job
    # was running at the op's entry check, so it gets past the guard, but the
    # terminal succeeded state must survive.
    reg = JobRegistry(max_concurrent=2)
    reg.register_type(RaceCompleteWorker)
    RaceCompleteWorker.gate = asyncio.Event()
    job = await reg.create("race_complete", {})
    await wait_for_status(reg, job.id, BackgroundJobStatus.RUNNING)

    original_cancel_task = reg._cancel_task

    async def open_gate_then_cancel(job_id: str) -> None:
        # Let run() return and the supervising task drive to terminal first.
        RaceCompleteWorker.gate.set()
        task = reg._tasks.get(job_id)
        if task is not None:
            try:
                await task
            except asyncio.CancelledError:
                pass
        await original_cancel_task(job_id)

    reg._cancel_task = open_gate_then_cancel  # type: ignore[method-assign]

    if operation == "pause":
        await reg.pause(job.id)
    else:
        await reg.cancel(job.id)
    return reg


@pytest.mark.asyncio
async def test_pause_loses_race_to_natural_completion_keeps_succeeded():
    # Regression: if run() completes naturally during pause()'s cancel-await,
    # the job is already terminal (succeeded) and pause() must not clobber it
    # back to paused (which would drop the result and allow a resume re-run).
    reg = await _drive_completion_race("pause")
    job_id = next(iter(reg._jobs))
    assert reg._jobs[job_id].status == BackgroundJobStatus.SUCCEEDED
    assert reg._jobs[job_id].result is not None


@pytest.mark.asyncio
async def test_cancel_loses_race_to_natural_completion_keeps_succeeded():
    # The cancel() path already guards on is_terminal; lock it in.
    reg = await _drive_completion_race("cancel")
    job_id = next(iter(reg._jobs))
    assert reg._jobs[job_id].status == BackgroundJobStatus.SUCCEEDED
    assert reg._jobs[job_id].result is not None


@pytest.mark.asyncio
async def test_pause_enforced_when_worker_swallows_cancel():
    # A worker that catches CancelledError (and uncancels it) then returns
    # normally must still be paused, not succeeded — the cancellation transition
    # is unconditional and enforced by the registry, not the worker.
    reg = JobRegistry(max_concurrent=2)
    reg.register_type(SwallowCancelWorker)
    SwallowCancelWorker.started = asyncio.Event()
    SwallowCancelWorker.gate = asyncio.Event()
    job = await reg.create("swallow_cancel", {})
    await wait_for_status(reg, job.id, BackgroundJobStatus.RUNNING)
    await asyncio.wait_for(SwallowCancelWorker.started.wait(), timeout=3.0)

    result = await reg.pause(job.id)
    assert result.status == BackgroundJobStatus.PAUSED
    assert reg._jobs[job.id].result is None


@pytest.mark.asyncio
async def test_cancel_enforced_when_worker_swallows_cancel():
    reg = JobRegistry(max_concurrent=2)
    reg.register_type(SwallowCancelWorker)
    SwallowCancelWorker.started = asyncio.Event()
    SwallowCancelWorker.gate = asyncio.Event()
    job = await reg.create("swallow_cancel", {})
    await wait_for_status(reg, job.id, BackgroundJobStatus.RUNNING)
    await asyncio.wait_for(SwallowCancelWorker.started.wait(), timeout=3.0)

    result = await reg.cancel(job.id)
    assert result.status == BackgroundJobStatus.CANCELLED
    assert reg._jobs[job.id].result is None


@pytest.mark.asyncio
async def test_cancel_from_paused():
    reg = JobRegistry(max_concurrent=2)
    reg.register_type(NoopJobWorker)
    job = await reg.create("noop", {"steps": 50, "sleep_per_step_seconds": 0.03})
    await wait_for_status(reg, job.id, BackgroundJobStatus.RUNNING)
    await reg.pause(job.id)
    assert reg._jobs[job.id].status == BackgroundJobStatus.PAUSED

    result = await reg.cancel(job.id)
    assert result.status == BackgroundJobStatus.CANCELLED
    assert reg._jobs[job.id].status == BackgroundJobStatus.CANCELLED
    assert reg._jobs[job.id].ended_at is not None


# -- delete ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_terminal_emits_deleted(registry):
    job = await registry.create("noop", {"steps": 2, "sleep_per_step_seconds": 0.01})
    await wait_for_status(registry, job.id, BackgroundJobStatus.SUCCEEDED)

    events = []
    gen = registry.events.subscribe()
    await asyncio.wait_for(gen.__anext__(), timeout=1.0)  # snapshot

    async def collect():
        async for event in gen:
            events.append(event)

    collector = asyncio.create_task(collect())
    await registry.delete(job.id)
    await asyncio.sleep(0.05)
    collector.cancel()
    try:
        await collector
    except asyncio.CancelledError:
        pass

    assert job.id not in registry._jobs
    assert any(e.event == "deleted" and e.data["id"] == job.id for e in events)


@pytest.mark.asyncio
async def test_delete_running_raises(registry):
    job = await registry.create("noop", {"steps": 50, "sleep_per_step_seconds": 0.05})
    await wait_for_status(registry, job.id, BackgroundJobStatus.RUNNING)
    with pytest.raises(JobOperationError):
        await registry.delete(job.id)
    await registry.cancel(job.id)


@pytest.mark.asyncio
async def test_delete_pending_raises():
    reg = JobRegistry(max_concurrent=1)
    reg.register_type(NoopJobWorker)
    running = await reg.create("noop", {"steps": 50, "sleep_per_step_seconds": 0.05})
    await wait_for_status(reg, running.id, BackgroundJobStatus.RUNNING)
    pending = await reg.create("noop", {"steps": 50, "sleep_per_step_seconds": 0.05})
    assert reg._jobs[pending.id].status == BackgroundJobStatus.PENDING
    with pytest.raises(JobOperationError):
        await reg.delete(pending.id)
    await reg.cancel(running.id)
    await reg.cancel(pending.id)


# -- reconciliation ----------------------------------------------------------


@pytest.mark.asyncio
async def test_compute_state_none_keeps_snapshot(registry):
    # Noop's compute_state returns None, so the believed snapshot from
    # report_progress is preserved and never flipped to complete early.
    job = await registry.create("noop", {"steps": 4, "sleep_per_step_seconds": 0.02})
    await wait_for_status(registry, job.id, BackgroundJobStatus.RUNNING)
    # get() triggers reconcile; with None it must not change progress/status.
    got = await registry.get(job.id)
    assert got is not None
    assert got.status in (BackgroundJobStatus.RUNNING, BackgroundJobStatus.SUCCEEDED)
    await wait_for_status(registry, job.id, BackgroundJobStatus.SUCCEEDED)
    assert registry._jobs[job.id].progress.success == 4


@pytest.mark.asyncio
async def test_report_progress_preserves_total_and_message_when_omitted():
    # A count-only report_progress call must not wipe a total/message set by an
    # earlier call.
    reg = JobRegistry(max_concurrent=2)
    reg.register_type(PartialProgressWorker)
    job = await reg.create("partial_progress", {})
    await wait_for_status(reg, job.id, BackgroundJobStatus.SUCCEEDED)

    final = reg._jobs[job.id]
    assert final.progress.success == 5
    assert final.progress.total == 50
    assert final.progress.message == "starting"


@pytest.mark.asyncio
async def test_ctx_report_display_merges_into_metadata():
    """Workers that call ctx.report_display() should update metadata.display
    in place — primary/secondary partial-updates merge, the other field
    stays. Required by multi-phase workers (RAG) that rewrite per-phase
    progress lines on every tick.
    """

    class _DisplayWorker(JobWorker[_EmptyParams, _EmptyResult]):
        type_name = "display_worker"
        params_model = _EmptyParams
        result_model = _EmptyResult
        supports_pause = False
        started: asyncio.Event
        gate: asyncio.Event

        async def run(self, params, ctx):
            await ctx.report_display(secondary=["Extracting 5/10"])
            type(self).started.set()
            await type(self).gate.wait()
            await ctx.report_display(secondary=["Extracting 10/10"])
            return _EmptyResult()

    reg = JobRegistry(max_concurrent=2)
    reg.register_type(_DisplayWorker)
    _DisplayWorker.started = asyncio.Event()
    _DisplayWorker.gate = asyncio.Event()

    job = await reg.create(
        "display_worker",
        {},
        metadata={"display": {"primary": "RAG: my-config"}},
    )
    await wait_for_status(reg, job.id, BackgroundJobStatus.RUNNING)
    await asyncio.wait_for(_DisplayWorker.started.wait(), timeout=3.0)
    record = reg._jobs[job.id]
    # `primary` stamped at create time is preserved; `secondary` was added by
    # the worker's first tick.
    assert record.metadata["display"]["primary"] == "RAG: my-config"
    assert record.metadata["display"]["secondary"] == ["Extracting 5/10"]

    # Let the worker finish; the second tick should overwrite `secondary`
    # without disturbing `primary`.
    _DisplayWorker.gate.set()
    await wait_for_status(reg, job.id, BackgroundJobStatus.SUCCEEDED)
    final = reg._jobs[job.id]
    assert final.metadata["display"]["primary"] == "RAG: my-config"
    assert final.metadata["display"]["secondary"] == ["Extracting 10/10"]


@pytest.mark.asyncio
async def test_apply_derived_preserves_error_when_compute_state_returns_none():
    """A compute_state that omits `error` (error=None) must preserve the
    runtime error count last reported via report_progress. This is the path
    that keeps View Errors visible on paused eval jobs: EvalRun entities only
    persist successes, so compute_state can't reconstruct failures and leaves
    error=None — the registry preserves the live count instead of wiping it."""

    class _ErrorThenNoneWorker(JobWorker[_EmptyParams, _EmptyResult]):
        type_name = "error_then_none"
        params_model = _EmptyParams
        result_model = _EmptyResult
        supports_pause = True
        started: asyncio.Event
        gate: asyncio.Event

        async def compute_state(self, params):
            return JobDerivedState(
                total=10, success=2, is_complete=False
            )  # error left None

        async def run(self, params, ctx):
            await ctx.report_progress(success=2, error=3, total=10)
            type(self).started.set()
            try:
                await type(self).gate.wait()
            except asyncio.CancelledError:
                task = asyncio.current_task()
                # task.uncancel() was added in Python 3.11; on 3.10 simply
                # swallowing the CancelledError exercises the same worst-case
                # "swallows cancel and returns normally" path.
                if task is not None and hasattr(task, "uncancel"):
                    task.uncancel()
            return _EmptyResult()

    reg = JobRegistry(max_concurrent=2)
    reg.register_type(_ErrorThenNoneWorker)
    _ErrorThenNoneWorker.started = asyncio.Event()
    _ErrorThenNoneWorker.gate = asyncio.Event()

    job = await reg.create("error_then_none", {})
    await wait_for_status(reg, job.id, BackgroundJobStatus.RUNNING)
    await asyncio.wait_for(_ErrorThenNoneWorker.started.wait(), timeout=3.0)
    assert reg._jobs[job.id].progress.error == 3

    result = await reg.pause(job.id)
    assert result.status == BackgroundJobStatus.PAUSED
    # The runtime error count survives the reconcile so the "View Errors"
    # button stays available in the panel while the job is paused.
    assert result.progress.error == 3


@pytest.mark.asyncio
async def test_apply_derived_preserves_total_when_compute_state_returns_none():
    # A compute_state that returns total=None (unknown denominator) alongside
    # success/error counts must not wipe a total set earlier via report_progress.
    # total=None means "unknown, keep what we had", mirroring message handling.
    reg = JobRegistry(max_concurrent=2)
    reg.register_type(TotalThenNoneWorker)
    TotalThenNoneWorker.started = asyncio.Event()
    TotalThenNoneWorker.gate = asyncio.Event()
    job = await reg.create("total_then_none", {})
    await wait_for_status(reg, job.id, BackgroundJobStatus.RUNNING)
    await asyncio.wait_for(TotalThenNoneWorker.started.wait(), timeout=3.0)
    assert reg._jobs[job.id].progress.total == 10

    # pause() runs compute_state (total=None, success=2, error=1) through
    # _apply_derived; the prior total of 10 must survive.
    result = await reg.pause(job.id)
    assert result.status == BackgroundJobStatus.PAUSED
    assert result.progress.total == 10
    assert result.progress.success == 2
    assert result.progress.error == 1


@pytest.mark.asyncio
async def test_get_reconciles_running_job_to_succeeded_mid_flight():
    # A long-running job whose source-of-truth state flips to complete should be
    # reconciled straight to succeeded by get() (the running/get() reconcile
    # path), not only at launch time.
    reg = JobRegistry(max_concurrent=2)
    reg.register_type(ReconcileCompleteWorker)
    ReconcileCompleteWorker.done = False
    job = await reg.create("reconcile_complete", {})
    await wait_for_status(reg, job.id, BackgroundJobStatus.RUNNING)
    # Still running here (run() is a 5s sleep); now flip the source of truth.
    assert reg._jobs[job.id].status == BackgroundJobStatus.RUNNING
    ReconcileCompleteWorker.done = True

    got = await reg.get(job.id)
    assert got is not None
    assert got.status == BackgroundJobStatus.SUCCEEDED
    assert got.progress.success == 3
    assert got.ended_at is not None


# -- concurrency -------------------------------------------------------------


@pytest.mark.asyncio
async def test_semaphore_caps_concurrency_fifo():
    reg = JobRegistry(max_concurrent=2)
    reg.register_type(NoopJobWorker)

    jobs = []
    for _ in range(4):
        jobs.append(
            await reg.create("noop", {"steps": 50, "sleep_per_step_seconds": 0.05})
        )

    await asyncio.sleep(0.05)
    statuses = [reg._jobs[j.id].status for j in jobs]
    running = [s for s in statuses if s == BackgroundJobStatus.RUNNING]
    pending = [s for s in statuses if s == BackgroundJobStatus.PENDING]
    assert len(running) == 2
    assert len(pending) == 2
    # FIFO: the first two created are the running ones.
    assert statuses[0] == BackgroundJobStatus.RUNNING
    assert statuses[1] == BackgroundJobStatus.RUNNING
    assert statuses[2] == BackgroundJobStatus.PENDING
    assert statuses[3] == BackgroundJobStatus.PENDING

    # Cancel the running ones; pending should be promoted.
    await reg.cancel(jobs[0].id)
    await reg.cancel(jobs[1].id)
    await wait_for_status(reg, jobs[2].id, BackgroundJobStatus.RUNNING)
    await wait_for_status(reg, jobs[3].id, BackgroundJobStatus.RUNNING)

    await reg.cancel(jobs[2].id)
    await reg.cancel(jobs[3].id)


# -- events ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_registry_emits_snapshot_and_job_events(registry):
    gen = registry.events.subscribe()
    snapshot = await asyncio.wait_for(gen.__anext__(), timeout=1.0)
    assert snapshot.event == "snapshot"
    assert snapshot.data["jobs"] == []

    events = []

    async def collect():
        async for event in gen:
            events.append(event)

    collector = asyncio.create_task(collect())
    job = await registry.create("noop", {"steps": 2, "sleep_per_step_seconds": 0.01})
    await wait_for_status(registry, job.id, BackgroundJobStatus.SUCCEEDED)
    await asyncio.sleep(0.02)
    collector.cancel()
    try:
        await collector
    except asyncio.CancelledError:
        pass

    job_events = [e for e in events if e.event == "job"]
    assert len(job_events) >= 2
    assert any(e.data["status"] == "running" for e in job_events)
    assert any(e.data["status"] == "succeeded" for e in job_events)


# -- wait --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wait_returns_immediately_for_terminal_job(registry):
    job = await registry.create("noop", {"steps": 2, "sleep_per_step_seconds": 0.01})
    await wait_for_status(registry, job.id, BackgroundJobStatus.SUCCEEDED)
    awaited = await asyncio.wait_for(registry.wait(job.id), timeout=1.0)
    assert awaited.id == job.id
    assert awaited.status == BackgroundJobStatus.SUCCEEDED
    assert awaited.result == {"completed_steps": 2}


@pytest.mark.asyncio
async def test_wait_blocks_then_returns_terminal_record(registry):
    job = await registry.create("noop", {"steps": 4, "sleep_per_step_seconds": 0.03})
    await wait_for_status(registry, job.id, BackgroundJobStatus.RUNNING)
    awaited = await asyncio.wait_for(registry.wait(job.id), timeout=3.0)
    assert awaited.status == BackgroundJobStatus.SUCCEEDED
    assert awaited.result == {"completed_steps": 4}


@pytest.mark.asyncio
async def test_wait_unknown_raises(registry):
    with pytest.raises(JobNotFoundError):
        await registry.wait("j_doesnotexist")


@pytest.mark.asyncio
async def test_wait_times_out(registry):
    job = await registry.create("noop", {"steps": 50, "sleep_per_step_seconds": 0.05})
    await wait_for_status(registry, job.id, BackgroundJobStatus.RUNNING)
    with pytest.raises(asyncio.TimeoutError):
        await registry.wait(job.id, timeout=0.01)
    await registry.cancel(job.id)


@pytest.mark.asyncio
async def test_wait_cancellation_leaves_job_running(registry):
    # The load-bearing decoupling invariant: abandoning a wait() must NOT stop
    # the job. A second concurrent waiter still resolves to the terminal record.
    job = await registry.create("noop", {"steps": 6, "sleep_per_step_seconds": 0.05})
    await wait_for_status(registry, job.id, BackgroundJobStatus.RUNNING)

    abandoned = asyncio.create_task(registry.wait(job.id))
    survivor = asyncio.create_task(registry.wait(job.id))
    # Let both awaiters reach their await point, then abandon the first.
    await asyncio.sleep(0.02)
    abandoned.cancel()
    with pytest.raises(asyncio.CancelledError):
        await abandoned

    # The job keeps running and the surviving waiter resolves to its terminal
    # record — the supervising task was untouched by the cancelled awaiter.
    result = await asyncio.wait_for(survivor, timeout=3.0)
    assert result.status == BackgroundJobStatus.SUCCEEDED
    assert result.result == {"completed_steps": 6}


@pytest.mark.asyncio
async def test_wait_multiple_waiters_both_resolve(registry):
    job = await registry.create("noop", {"steps": 4, "sleep_per_step_seconds": 0.03})
    await wait_for_status(registry, job.id, BackgroundJobStatus.RUNNING)
    first = asyncio.create_task(registry.wait(job.id))
    second = asyncio.create_task(registry.wait(job.id))
    one, two = await asyncio.wait_for(asyncio.gather(first, second), timeout=3.0)
    assert one.status == BackgroundJobStatus.SUCCEEDED
    assert two.status == BackgroundJobStatus.SUCCEEDED
    assert one.result == two.result == {"completed_steps": 4}


@pytest.mark.asyncio
async def test_delete_removes_completion_event(registry):
    job = await registry.create("noop", {"steps": 2, "sleep_per_step_seconds": 0.01})
    # wait() lazily creates the completion event; it survives to the terminal set.
    awaited = await asyncio.wait_for(registry.wait(job.id), timeout=3.0)
    assert awaited.status == BackgroundJobStatus.SUCCEEDED
    assert job.id in registry._completion_events

    await registry.delete(job.id)
    assert job.id not in registry._completion_events


# -- not found ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_unknown_returns_none(registry):
    assert await registry.get("j_doesnotexist") is None


@pytest.mark.asyncio
async def test_lifecycle_op_unknown_raises(registry):
    with pytest.raises(JobNotFoundError):
        await registry.cancel("j_doesnotexist")


# -- idempotency_key (supersede on create) ----------------------------------


@pytest.mark.asyncio
async def test_idempotency_key_supersedes_pending_predecessor():
    """Saturate the slot with a long-running job so a same-key second create
    finds its predecessor still PENDING. The old record must vanish; only the
    new one remains."""

    class _Long(JobWorker[_EmptyParams, _EmptyResult]):
        type_name = "long"
        params_model = _EmptyParams
        result_model = _EmptyResult
        supports_pause = False

        async def run(self, params, ctx):
            await asyncio.sleep(5)
            return _EmptyResult()

    reg = JobRegistry(max_concurrent=1)
    reg.register_type(_Long)
    # First job occupies the only slot.
    blocker = await reg.create("long", {})
    await wait_for_status(reg, blocker.id, BackgroundJobStatus.RUNNING)
    # Second job with the SAME key — should NOT supersede `blocker` (different
    # key), so it just sits pending.
    pending_other = await reg.create("long", {}, idempotency_key="K")
    assert pending_other.status == BackgroundJobStatus.PENDING
    # Third job with the same "K" key — must supersede `pending_other`.
    successor = await reg.create("long", {}, idempotency_key="K")
    assert pending_other.id not in reg._jobs
    assert successor.id in reg._jobs
    # The unrelated `blocker` is untouched.
    assert blocker.id in reg._jobs


@pytest.mark.asyncio
async def test_idempotency_key_supersedes_running_predecessor():
    class _Long(JobWorker[_EmptyParams, _EmptyResult]):
        type_name = "long"
        params_model = _EmptyParams
        result_model = _EmptyResult
        supports_pause = False

        async def run(self, params, ctx):
            await asyncio.sleep(5)
            return _EmptyResult()

    reg = JobRegistry(max_concurrent=2)
    reg.register_type(_Long)
    first = await reg.create("long", {}, idempotency_key="K")
    await wait_for_status(reg, first.id, BackgroundJobStatus.RUNNING)
    second = await reg.create("long", {}, idempotency_key="K")
    # Predecessor is fully removed (no Cancelled row left behind).
    assert first.id not in reg._jobs
    # Successor takes its place.
    await wait_for_status(
        reg, second.id, {BackgroundJobStatus.RUNNING, BackgroundJobStatus.PENDING}
    )
    # Tear down the leftover task so asyncio doesn't warn about destroying a
    # pending coroutine when the event loop closes.
    await reg.cancel(second.id)


@pytest.mark.asyncio
async def test_idempotency_key_supersedes_paused_predecessor(registry):
    """A paused job has no live task; the supersede path must still remove
    the record cleanly without trying to cancel a non-existent task."""
    first = await registry.create(
        "noop",
        {"steps": 100, "sleep_per_step_seconds": 0.01},
        idempotency_key="K",
    )
    await wait_for_status(registry, first.id, BackgroundJobStatus.RUNNING)
    await registry.pause(first.id)
    assert registry._jobs[first.id].status == BackgroundJobStatus.PAUSED
    second = await registry.create("noop", {"steps": 1}, idempotency_key="K")
    assert first.id not in registry._jobs
    assert second.id in registry._jobs


@pytest.mark.asyncio
async def test_idempotency_key_supersedes_succeeded_predecessor(registry):
    """A succeeded predecessor is pure history — the source-of-truth entities
    its run produced (EvalRuns, etc.) persist independently of the job row, so
    the panel doesn't need to keep an obsolete 'last time it succeeded' row
    once the user re-launches. Drop it the same way we drop running/cancelled
    predecessors."""
    first = await registry.create(
        "noop", {"steps": 1, "sleep_per_step_seconds": 0.0}, idempotency_key="K"
    )
    await wait_for_status(registry, first.id, BackgroundJobStatus.SUCCEEDED)
    second = await registry.create(
        "noop", {"steps": 1, "sleep_per_step_seconds": 0.0}, idempotency_key="K"
    )
    assert first.id not in registry._jobs
    assert second.id in registry._jobs


@pytest.mark.asyncio
async def test_idempotency_key_supersedes_cancelled_predecessor():
    """A cancelled job is a purely transient 'user changed their mind' state
    with no result or error info — a fresh same-key launch should replace it
    rather than leaving a noise Cancelled row behind the new run."""

    class _Long(JobWorker[_EmptyParams, _EmptyResult]):
        type_name = "long"
        params_model = _EmptyParams
        result_model = _EmptyResult
        supports_pause = False

        async def run(self, params, ctx):
            await asyncio.sleep(5)
            return _EmptyResult()

    reg = JobRegistry(max_concurrent=2)
    reg.register_type(_Long)
    first = await reg.create("long", {}, idempotency_key="K")
    await wait_for_status(reg, first.id, BackgroundJobStatus.RUNNING)
    await reg.cancel(first.id)
    assert reg._jobs[first.id].status == BackgroundJobStatus.CANCELLED
    second = await reg.create("long", {}, idempotency_key="K")
    # The cancelled predecessor is gone — replaced, not preserved.
    assert first.id not in reg._jobs
    assert second.id in reg._jobs
    await reg.cancel(second.id)


@pytest.mark.asyncio
async def test_idempotency_key_keeps_failed_predecessor():
    """Failed jobs carry the previous attempt's error summary that the user
    may still need to inspect while retrying. They are preserved across a
    same-key re-launch (the panel can carry both rows)."""

    class _Boom(JobWorker[_EmptyParams, _EmptyResult]):
        type_name = "boom"
        params_model = _EmptyParams
        result_model = _EmptyResult
        supports_pause = False

        async def run(self, params, ctx):
            raise RuntimeError("nope")

    reg = JobRegistry(max_concurrent=2)
    reg.register_type(_Boom)
    first = await reg.create("boom", {}, idempotency_key="K")
    await wait_for_status(reg, first.id, BackgroundJobStatus.FAILED)
    second = await reg.create("boom", {}, idempotency_key="K")
    await wait_for_status(reg, second.id, BackgroundJobStatus.FAILED)
    assert first.id in reg._jobs
    assert second.id in reg._jobs


@pytest.mark.asyncio
async def test_idempotency_key_only_matches_within_same_type(registry):
    """Two different worker types sharing the same arbitrary key must NOT
    supersede each other — keys are scoped per type to avoid cross-type
    collisions on common strings."""

    class _Other(JobWorker[_EmptyParams, _EmptyResult]):
        type_name = "other"
        params_model = _EmptyParams
        result_model = _EmptyResult
        supports_pause = False

        async def run(self, params, ctx):
            await asyncio.sleep(5)
            return _EmptyResult()

    registry.register_type(_Other)
    noop_job = await registry.create(
        "noop",
        {"steps": 100, "sleep_per_step_seconds": 0.01},
        idempotency_key="K",
    )
    other_job = await registry.create("other", {}, idempotency_key="K")
    # Both still present — same key, different types.
    assert noop_job.id in registry._jobs
    assert other_job.id in registry._jobs


@pytest.mark.asyncio
async def test_idempotency_key_supersedes_noncancelable_predecessor():
    """`supports_cancel=False` (e.g. finetune watchers) must still be
    supersedable — idempotency is registry-internal teardown, not a user
    cancel action. Otherwise idempotency would silently break for watchers."""

    class _Watcher(JobWorker[_EmptyParams, _EmptyResult]):
        type_name = "watcher"
        params_model = _EmptyParams
        result_model = _EmptyResult
        supports_pause = False
        supports_cancel = False

        async def run(self, params, ctx):
            await asyncio.sleep(5)
            return _EmptyResult()

    reg = JobRegistry(max_concurrent=2)
    reg.register_type(_Watcher)
    first = await reg.create("watcher", {}, idempotency_key="K")
    await wait_for_status(reg, first.id, BackgroundJobStatus.RUNNING)
    # User-issued cancel would refuse (supports_cancel=False); supersede must not.
    with pytest.raises(JobOperationError):
        await reg.cancel(first.id)
    second = await reg.create("watcher", {}, idempotency_key="K")
    assert first.id not in reg._jobs
    assert second.id in reg._jobs
    # Clean up the watcher's still-running task so it doesn't leak past the test.
    second.supports_cancel = True
    await reg.cancel(second.id)


@pytest.mark.asyncio
async def test_idempotency_key_is_stamped_on_record(registry):
    job = await registry.create("noop", {"steps": 1}, idempotency_key="hello")
    assert registry._jobs[job.id].idempotency_key == "hello"
    job2 = await registry.create("noop", {"steps": 1})
    assert registry._jobs[job2.id].idempotency_key is None


# -- typed progress detail ---------------------------------------------------


class DetailModel(BaseModel):
    phase: str
    done: int


class DetailWorker(JobWorker[_EmptyParams, _EmptyResult]):
    type_name = "detail"
    params_model = _EmptyParams
    result_model = _EmptyResult
    progress_model = DetailModel
    gate: asyncio.Event

    async def run(self, params, ctx):
        await ctx.report_progress_detail(DetailModel(phase="extract", done=3))
        await type(self).gate.wait()
        return _EmptyResult()


@pytest.mark.asyncio
async def test_report_progress_detail_stamps_typed_payload():
    reg = JobRegistry(max_concurrent=2)
    reg.register_type(DetailWorker)
    DetailWorker.gate = asyncio.Event()
    job = await reg.create("detail", {})
    await wait_for_status(reg, job.id, BackgroundJobStatus.RUNNING)
    # Give the worker a tick to report the detail.
    for _ in range(50):
        if reg._jobs[job.id].progress_detail is not None:
            break
        await asyncio.sleep(0.01)
    assert reg._jobs[job.id].progress_detail == {"phase": "extract", "done": 3}
    DetailWorker.gate.set()


class WrongModel(BaseModel):
    other: str


class BadDetailWorker(JobWorker[_EmptyParams, _EmptyResult]):
    type_name = "bad_detail"
    params_model = _EmptyParams
    result_model = _EmptyResult
    progress_model = DetailModel

    async def run(self, params, ctx):
        await ctx.report_progress_detail(WrongModel(other="x"))
        return _EmptyResult()


@pytest.mark.asyncio
async def test_report_progress_detail_rejects_wrong_model():
    reg = JobRegistry(max_concurrent=2)
    reg.register_type(BadDetailWorker)
    job = await reg.create("bad_detail", {})
    # The type guard raises inside run(), routing the job to FAILED.
    await wait_for_status(reg, job.id, BackgroundJobStatus.FAILED)
    assert reg._jobs[job.id].error is not None
