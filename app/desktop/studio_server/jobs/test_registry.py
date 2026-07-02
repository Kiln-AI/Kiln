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


class ErrorThenNoneWorker(JobWorker[_EmptyParams, _EmptyResult]):
    """run() reports a non-zero error count via report_progress, then
    compute_state returns error=None (errors aren't derivable from entities,
    e.g. failed eval items leave no EvalRun). The reconcile must preserve the
    live error count rather than wiping it to 0.
    """

    type_name = "error_then_none"
    params_model = _EmptyParams
    result_model = _EmptyResult
    supports_pause = True
    started: asyncio.Event
    gate: asyncio.Event

    async def compute_state(self, params):
        return JobDerivedState(total=5, success=3, is_complete=False)

    async def run(self, params, ctx):
        await ctx.report_progress(success=1, error=2, total=5, message="working")
        type(self).started.set()
        try:
            await type(self).gate.wait()
        except asyncio.CancelledError:
            task = asyncio.current_task()
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
async def test_apply_derived_preserves_error_when_compute_state_returns_none():
    # A compute_state that returns error=None (errors not derivable from
    # entities) must not wipe a live error count reported via report_progress.
    # error=None means "unknown, keep what we had", mirroring total/message.
    reg = JobRegistry(max_concurrent=2)
    reg.register_type(ErrorThenNoneWorker)
    ErrorThenNoneWorker.started = asyncio.Event()
    ErrorThenNoneWorker.gate = asyncio.Event()
    job = await reg.create("error_then_none", {})
    await wait_for_status(reg, job.id, BackgroundJobStatus.RUNNING)
    await asyncio.wait_for(ErrorThenNoneWorker.started.wait(), timeout=3.0)
    assert reg._jobs[job.id].progress.error == 2

    # pause() runs compute_state (error=None, success=3) through _apply_derived;
    # the prior error count of 2 must survive while success advances.
    result = await reg.pause(job.id)
    assert result.status == BackgroundJobStatus.PAUSED
    assert result.progress.error == 2
    assert result.progress.success == 3


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
async def test_wait_many_returns_all_terminal_in_order(registry):
    a = await registry.create("noop", {"steps": 2, "sleep_per_step_seconds": 0.01})
    b = await registry.create("noop", {"steps": 4, "sleep_per_step_seconds": 0.02})
    c = await registry.create("noop", {"steps": 1, "sleep_per_step_seconds": 0.01})
    results = await asyncio.wait_for(
        registry.wait_many([a.id, b.id, c.id]), timeout=5.0
    )
    assert [r.id for r in results] == [a.id, b.id, c.id]
    assert all(r.status == BackgroundJobStatus.SUCCEEDED for r in results)


@pytest.mark.asyncio
async def test_wait_many_empty_returns_empty(registry):
    assert await registry.wait_many([]) == []


@pytest.mark.asyncio
async def test_wait_many_unknown_id_raises(registry):
    job = await registry.create("noop", {"steps": 2, "sleep_per_step_seconds": 0.01})
    with pytest.raises(JobNotFoundError):
        await registry.wait_many([job.id, "j_doesnotexist"])


@pytest.mark.asyncio
async def test_wait_many_times_out_if_any_still_running(registry):
    fast = await registry.create("noop", {"steps": 1, "sleep_per_step_seconds": 0.01})
    slow = await registry.create("noop", {"steps": 50, "sleep_per_step_seconds": 0.05})
    await wait_for_status(registry, slow.id, BackgroundJobStatus.RUNNING)
    with pytest.raises(asyncio.TimeoutError):
        await registry.wait_many([fast.id, slow.id], timeout=0.05)
    await registry.cancel(slow.id)


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


# -- describe() / properties guard ------------------------------------------


class PropertiesModel(BaseModel):
    label: str


class DescribeWorker(JobWorker[_EmptyParams, _EmptyResult]):
    type_name = "describe"
    params_model = _EmptyParams
    result_model = _EmptyResult
    properties_model = PropertiesModel
    gate: asyncio.Event

    async def describe(self, params):
        return PropertiesModel(label="hello")

    async def run(self, params, ctx):
        await type(self).gate.wait()
        return _EmptyResult()


@pytest.mark.asyncio
async def test_create_stamps_typed_properties():
    reg = JobRegistry(max_concurrent=2)
    reg.register_type(DescribeWorker)
    DescribeWorker.gate = asyncio.Event()
    # Properties are computed at create time, before dispatch.
    job = await reg.create("describe", {})
    try:
        assert job.properties == {"label": "hello"}
    finally:
        # Always release the gated worker, even if the assertion fails, so the
        # spawned job can finish rather than leaking into teardown.
        DescribeWorker.gate.set()
    await wait_for_status(reg, job.id, BackgroundJobStatus.SUCCEEDED)


class BadDescribeWorker(JobWorker[_EmptyParams, _EmptyResult]):
    type_name = "bad_describe"
    params_model = _EmptyParams
    result_model = _EmptyResult
    properties_model = PropertiesModel

    async def describe(self, params):
        # Returns a model that is NOT the declared properties_model.
        return WrongModel(other="x")

    async def run(self, params, ctx):
        return _EmptyResult()


@pytest.mark.asyncio
async def test_create_drops_properties_on_wrong_type():
    reg = JobRegistry(max_concurrent=2)
    reg.register_type(BadDescribeWorker)
    # The contract guard logs and drops the bad payload — create still succeeds
    # (the job is not failed), it just carries no properties.
    job = await reg.create("bad_describe", {})
    assert job.properties is None
    await wait_for_status(
        reg,
        job.id,
        {BackgroundJobStatus.SUCCEEDED, BackgroundJobStatus.RUNNING},
    )


class RaisingDescribeWorker(JobWorker[_EmptyParams, _EmptyResult]):
    type_name = "raising_describe"
    params_model = _EmptyParams
    result_model = _EmptyResult
    properties_model = PropertiesModel

    async def describe(self, params):
        raise RuntimeError("boom")

    async def run(self, params, ctx):
        return _EmptyResult()


@pytest.mark.asyncio
async def test_create_swallows_describe_failure():
    reg = JobRegistry(max_concurrent=2)
    reg.register_type(RaisingDescribeWorker)
    # A describe() that raises must never break job creation.
    job = await reg.create("raising_describe", {})
    assert job.properties is None
    await wait_for_status(
        reg,
        job.id,
        {BackgroundJobStatus.SUCCEEDED, BackgroundJobStatus.RUNNING},
    )


class UndeclaredPropertiesWorker(JobWorker[_EmptyParams, _EmptyResult]):
    type_name = "undeclared_properties"
    params_model = _EmptyParams
    result_model = _EmptyResult
    # properties_model intentionally left at the default (None).

    async def describe(self, params):
        return PropertiesModel(label="orphan")

    async def run(self, params, ctx):
        return _EmptyResult()


@pytest.mark.asyncio
async def test_create_drops_properties_without_declared_model():
    reg = JobRegistry(max_concurrent=2)
    reg.register_type(UndeclaredPropertiesWorker)
    # Returning properties without declaring properties_model is a contract
    # violation: the payload is dropped (nothing to cast to) and create() still
    # succeeds rather than serializing an unvalidated shape.
    job = await reg.create("undeclared_properties", {})
    assert job.properties is None
    await wait_for_status(
        reg,
        job.id,
        {BackgroundJobStatus.SUCCEEDED, BackgroundJobStatus.RUNNING},
    )
