from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from app.desktop.studio_server.jobs.models import (
    BackgroundJobStatus,
    JobContext,
    JobProgressUpdate,
)
from app.desktop.studio_server.jobs.registry import JobRegistry
from app.desktop.studio_server.jobs.workers.finetune import (
    FinetuneJobFailedError,
    FinetuneJobParams,
    FinetuneJobResult,
    FinetuneJobWorker,
    FinetuneStatusUnknownError,
)
from kiln_ai.adapters.fine_tune.base_finetune import FineTuneStatus
from kiln_ai.datamodel import FineTuneStatusType


class _FakeFinetune:
    def __init__(self, provider: str = "openai") -> None:
        self.provider = provider
        self.id = "ft_test_id"
        self.name = "Test FT"


class _ProbeContext(JobContext):
    """JobContext that records every report_progress call for assertions."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

        async def _report_progress(update: JobProgressUpdate) -> None:
            self.events.append(update.model_dump())

        async def _report_progress_detail(detail: Any) -> None:
            pass

        async def _report_error(message: str, extra: dict[str, Any]) -> None:
            pass

        async def _report_display(update: Any) -> None:
            pass

        async def _report_metadata_patch(patch: dict[str, Any]) -> None:
            pass

        super().__init__(
            job_id="j_test",
            run_id="r_test",
            report_progress=_report_progress,
            report_progress_detail=_report_progress_detail,
            report_error=_report_error,
            report_display=_report_display,
            report_metadata_patch=_report_metadata_patch,
        )


@pytest.fixture(autouse=True)
def _zero_poll_interval():
    # Drive the poll loop in zero wall-clock time but keep asyncio.sleep as the
    # real function so it still yields control to the event loop — otherwise
    # the supervising task in end-to-end tests would never get to run.
    with patch.object(FinetuneJobWorker, "POLL_INTERVAL_SECONDS", 0):
        yield


@pytest.fixture
def stub_finetune_load():
    with patch(
        "app.desktop.studio_server.jobs.workers.finetune.finetune_from_id",
        return_value=_FakeFinetune(),
    ) as m:
        yield m


def _stub_status_sequence(statuses: list[FineTuneStatus]):
    """Patch the finetune registry so the adapter's .status() yields the given
    sequence in order. The worker calls status() once per poll cycle.
    """

    adapter_status_mock = AsyncMock(side_effect=statuses)
    fake_adapter_cls = type(
        "FakeAdapter",
        (),
        {"__init__": lambda self, ft: None, "status": adapter_status_mock},
    )
    return patch(
        "app.desktop.studio_server.jobs.workers.finetune.finetune_registry",
        {"openai": fake_adapter_cls},
    )


PARAMS = FinetuneJobParams(project_id="p1", task_id="t1", finetune_id="ft_test_id")


@pytest.mark.asyncio
async def test_run_returns_result_when_status_is_completed(stub_finetune_load):
    """Provider reports completed on first poll → worker returns success."""
    with _stub_status_sequence(
        [FineTuneStatus(status=FineTuneStatusType.completed, message="all done")]
    ):
        worker = FinetuneJobWorker()
        ctx = _ProbeContext()
        result = await worker.run(PARAMS, ctx)
    assert isinstance(result, FinetuneJobResult)
    assert result.status == "completed"
    # Final progress event marks success=1 of total=1.
    assert ctx.events[-1] == {
        "success": 1,
        "error": 0,
        "total": 1,
        "message": "all done",
    }


@pytest.mark.asyncio
async def test_run_raises_on_failed_status(stub_finetune_load):
    """A failed status must surface as a raised exception so the registry
    drives the job to FAILED with error_details captured in the error log."""
    with _stub_status_sequence(
        [
            FineTuneStatus(
                status=FineTuneStatusType.failed,
                message="training broke",
                error_details="quota exceeded",
            )
        ]
    ):
        worker = FinetuneJobWorker()
        ctx = _ProbeContext()
        with pytest.raises(FinetuneJobFailedError) as exc_info:
            await worker.run(PARAMS, ctx)
    assert "quota exceeded" in str(exc_info.value)


@pytest.mark.asyncio
async def test_run_polls_until_terminal(stub_finetune_load):
    """Non-terminal statuses keep the worker polling. Each poll reports a
    fresh progress update so the UI message stays current."""
    sequence = [
        FineTuneStatus(status=FineTuneStatusType.pending, message="queued"),
        FineTuneStatus(status=FineTuneStatusType.running, message="step 5/10"),
        FineTuneStatus(status=FineTuneStatusType.completed, message="finished"),
    ]
    with _stub_status_sequence(sequence):
        worker = FinetuneJobWorker()
        ctx = _ProbeContext()
        result = await worker.run(PARAMS, ctx)
    assert result.status == "completed"
    # One event per poll: pending, running, completed.
    assert [e["message"] for e in ctx.events] == [
        "queued",
        "step 5/10",
        "finished",
    ]
    # Non-terminal polls report success=0 with no total (avoids a misleading
    # 0% progress bar); the completion event reports total=1, success=1.
    assert ctx.events[0]["total"] is None
    assert ctx.events[1]["total"] is None
    assert ctx.events[2]["total"] == 1


@pytest.mark.asyncio
async def test_run_raises_on_unknown_provider(stub_finetune_load):
    """If the Finetune's provider isn't resolvable, polling can't make progress
    — better to fail fast than spin forever on unknowns."""

    class _UnresolvableFakeFinetune(_FakeFinetune):
        def __init__(self) -> None:
            super().__init__(provider="not_a_real_provider")

    stub_finetune_load.return_value = _UnresolvableFakeFinetune()
    worker = FinetuneJobWorker()
    ctx = _ProbeContext()
    with pytest.raises(FinetuneStatusUnknownError):
        await worker.run(PARAMS, ctx)


@pytest.mark.asyncio
async def test_compute_state_marks_completed_as_done(stub_finetune_load):
    with _stub_status_sequence(
        [FineTuneStatus(status=FineTuneStatusType.completed, message="done")]
    ):
        worker = FinetuneJobWorker()
        state = await worker.compute_state(PARAMS)
    assert state is not None
    assert state.is_complete is True
    assert state.success == 1
    assert state.total == 1


@pytest.mark.asyncio
async def test_compute_state_marks_failed_as_done(stub_finetune_load):
    """Failed is terminal even though the user-visible outcome is bad — the
    registry uses is_complete to decide whether to skip a launch on resume."""
    with _stub_status_sequence(
        [FineTuneStatus(status=FineTuneStatusType.failed, message="oh no")]
    ):
        worker = FinetuneJobWorker()
        state = await worker.compute_state(PARAMS)
    assert state is not None
    assert state.is_complete is True
    assert state.success == 0


@pytest.mark.asyncio
async def test_compute_state_marks_running_as_not_done(stub_finetune_load):
    with _stub_status_sequence(
        [FineTuneStatus(status=FineTuneStatusType.running, message="going")]
    ):
        worker = FinetuneJobWorker()
        state = await worker.compute_state(PARAMS)
    assert state is not None
    assert state.is_complete is False
    assert state.success == 0


@pytest.mark.asyncio
async def test_worker_advertises_no_pause_or_cancel():
    """Sanity: the worker's class-level flags must be False so the registry
    stamps the JobRecord correctly and the UI hides both buttons."""
    assert FinetuneJobWorker.supports_pause is False
    assert FinetuneJobWorker.supports_cancel is False


@pytest.mark.asyncio
async def test_end_to_end_through_registry_completes(stub_finetune_load):
    """Drive the worker through the real JobRegistry to confirm the
    success-with-immediate-completion path produces a SUCCEEDED record."""
    with _stub_status_sequence(
        [FineTuneStatus(status=FineTuneStatusType.completed, message="done")]
    ):
        reg = JobRegistry(max_concurrent=2)
        reg.register_type(FinetuneJobWorker)
        job = await reg.create(
            "finetune",
            {
                "project_id": "p1",
                "task_id": "t1",
                "finetune_id": "ft_test_id",
            },
        )
        # compute_state at launch reports is_complete=True so the registry
        # short-circuits to SUCCEEDED without invoking run().
        for _ in range(100):
            if reg._jobs[job.id].status in {
                BackgroundJobStatus.SUCCEEDED,
                BackgroundJobStatus.FAILED,
            }:
                break
            await asyncio.sleep(0.01)
        assert reg._jobs[job.id].status == BackgroundJobStatus.SUCCEEDED
        # The job record reflects the worker's no-cancel/no-pause posture.
        assert reg._jobs[job.id].supports_cancel is False
        assert reg._jobs[job.id].supports_pause is False
