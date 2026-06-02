from __future__ import annotations

import asyncio
import json

import httpx
import pytest
import pytest_asyncio
from app.desktop.studio_server import eval_jobs_api
from app.desktop.studio_server.eval_jobs_api import connect_eval_jobs_api
from app.desktop.studio_server.jobs import api as jobs_api
from app.desktop.studio_server.jobs.events import JobEvent
from app.desktop.studio_server.jobs.models import (
    BackgroundJobStatus,
    JobContext,
    JobDerivedState,
    JobRecord,
    JobWorker,
)
from app.desktop.studio_server.jobs.registry import JobRegistry
from fastapi import FastAPI
from pydantic import BaseModel

PATH = "/api/projects/project1/tasks/task1/evals/eval1/eval_config/eval_config1/run_comparison_jobs"


class _StubEvalParams(BaseModel):
    project_id: str
    task_id: str
    eval_id: str
    eval_config_id: str
    run_config_id: str


class _StubEvalResult(BaseModel):
    total: int
    success: int
    error: int


class _StubEvalWorker(JobWorker[_StubEvalParams, _StubEvalResult]):
    """Stands in for EvalJobWorker under the same `eval` type_name.

    Pausable and idempotent like the real worker, but reports progress over a
    handful of sleep steps instead of driving a real EvalRunner — fast and
    deterministic for SSE/pause tests. Cancellation lands the job in paused
    (the registry's unconditional pause transition), mirroring the real worker.
    """

    type_name = "eval"
    params_model = _StubEvalParams
    result_model = _StubEvalResult
    supports_pause = True
    steps = 6
    sleep_per_step_seconds = 0.05

    async def compute_state(self, params):
        return JobDerivedState(total=type(self).steps, success=0, error=0)

    async def run(self, params: _StubEvalParams, ctx: JobContext) -> _StubEvalResult:
        success = 0
        for _ in range(type(self).steps):
            await asyncio.sleep(type(self).sleep_per_step_seconds)
            success += 1
            await ctx.report_progress(success=success, error=0, total=type(self).steps)
        return _StubEvalResult(total=type(self).steps, success=success, error=0)


@pytest.fixture
def registry(monkeypatch):
    reg = JobRegistry(max_concurrent=10)
    reg.register_type(_StubEvalWorker)
    monkeypatch.setattr(eval_jobs_api, "job_registry", reg)
    monkeypatch.setattr(jobs_api, "job_registry", reg)
    return reg


@pytest.fixture
def stub_eval_loaders(monkeypatch):
    """Bypass the real datamodel loaders: a fake eval config whose parent eval
    has id 'eval1', and a fixed three-run-config list for all_run_configs."""

    class _FakeEval:
        id = "eval1"
        name = "Fake Eval"

    class _FakeEvalConfig:
        name = "Fake Judge"

        def parent_eval(self):
            return _FakeEval()

    class _FakeRunConfig:
        def __init__(self, rc_id):
            self.id = rc_id
            self.name = f"run-config-{rc_id}"

    monkeypatch.setattr(
        eval_jobs_api,
        "eval_config_from_id",
        lambda *a, **k: _FakeEvalConfig(),
    )
    monkeypatch.setattr(
        eval_jobs_api,
        "get_all_run_configs",
        lambda *a, **k: [_FakeRunConfig("rc_a"), _FakeRunConfig("rc_b")],
    )
    monkeypatch.setattr(
        eval_jobs_api,
        "task_run_config_from_id",
        lambda project_id, task_id, run_config_id: _FakeRunConfig(run_config_id),
    )


@pytest.fixture
def app(registry, stub_eval_loaders):
    app = FastAPI()
    connect_eval_jobs_api(app)
    return app


@pytest_asyncio.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as http_client:
        yield http_client


def _parse_sse_blocks(text: str) -> list[str]:
    """Return the `data:` payloads (stripped) from raw SSE text."""
    payloads: list[str] = []
    for line in text.splitlines():
        if line.startswith("data:"):
            payloads.append(line[len("data:") :].strip())
    return payloads


@pytest.mark.asyncio
async def test_creates_one_job_per_run_config(client, registry):
    async with client.stream(
        "GET",
        PATH,
        params={"all_run_configs": "false", "run_config_ids": ["rc1", "rc2", "rc3"]},
    ) as response:
        assert response.status_code == 200
        eval_jobs = registry.list_jobs(type_name="eval", project_id="project1")
        assert len(eval_jobs) == 3
        assert {j.params["run_config_id"] for j in eval_jobs} == {"rc1", "rc2", "rc3"}
        assert {j.params["eval_id"] for j in eval_jobs} == {"eval1"}
        await response.aread()


@pytest.mark.asyncio
async def test_all_run_configs_uses_loader(client, registry):
    async with client.stream(
        "GET", PATH, params={"all_run_configs": "true"}
    ) as response:
        assert response.status_code == 200
        eval_jobs = registry.list_jobs(type_name="eval", project_id="project1")
        assert {j.params["run_config_id"] for j in eval_jobs} == {"rc_a", "rc_b"}
        await response.aread()


@pytest.mark.asyncio
async def test_no_run_config_ids_is_400(client):
    response = await client.get(PATH, params={"all_run_configs": "false"})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_stream_emits_aggregate_then_complete(client, registry):
    async with client.stream(
        "GET",
        PATH,
        params={"all_run_configs": "false", "run_config_ids": ["rc1", "rc2"]},
    ) as response:
        assert response.status_code == 200
        body = await response.aread()

    payloads = _parse_sse_blocks(body.decode())
    assert payloads[-1] == "complete"

    aggregates = [json.loads(p) for p in payloads if p != "complete"]
    assert len(aggregates) >= 1
    # Final aggregate sums both jobs: 6 + 6 = 12 successes, total 12, no errors.
    final = aggregates[-1]
    assert final == {"progress": 12, "total": 12, "errors": 0}
    # Progress is monotonic non-decreasing across the stream.
    progresses = [a["progress"] for a in aggregates]
    assert progresses == sorted(progresses)

    eval_jobs = registry.list_jobs(type_name="eval", project_id="project1")
    assert all(j.status == BackgroundJobStatus.SUCCEEDED for j in eval_jobs)


@pytest.mark.asyncio
async def test_disconnect_leaves_jobs_running(app, registry, monkeypatch):
    """The SSE stream is a pure observer: closing the stream (client disconnect)
    does NOT pause or cancel the underlying eval jobs. They keep running in the
    registry until they finish on their own — same as every other job in the
    system."""
    monkeypatch.setattr(_StubEvalWorker, "steps", 200)
    monkeypatch.setattr(_StubEvalWorker, "sleep_per_step_seconds", 0.05)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as http_client:

        async def read_stream() -> None:
            async with http_client.stream(
                "GET",
                PATH,
                params={
                    "all_run_configs": "false",
                    "run_config_ids": ["rc1", "rc2"],
                },
            ) as response:
                assert response.status_code == 200
                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        break

        # Cancelling the in-flight read drops the connection mid-stream — the
        # same signal uvicorn delivers on a real client disconnect.
        reader = asyncio.create_task(read_stream())
        await asyncio.sleep(0.3)
        reader.cancel()
        try:
            await reader
        except asyncio.CancelledError:
            pass

        eval_jobs = registry.list_jobs(type_name="eval", project_id="project1")
        assert len(eval_jobs) == 2
        # The jobs MUST still be alive (pending/running) immediately after the
        # disconnect — never paused or cancelled by the stream teardown.
        for job in eval_jobs:
            assert job.status in (
                BackgroundJobStatus.PENDING,
                BackgroundJobStatus.RUNNING,
            ), f"unexpected status after disconnect: {job.status}"

        # Tear down for test isolation: cancel the still-running jobs so they
        # don't outlive the test event loop. Outside production-relevant flow.
        for job in eval_jobs:
            try:
                await registry.cancel(job.id)
            except Exception:
                pass


@pytest.mark.asyncio
async def test_deleted_tracked_job_unblocks_stream(registry, monkeypatch):
    # A tracked job that is deleted out from under the stream (e.g. deleted in
    # the window between create() and the generator's subscribe()) would never
    # become terminal in `tracked`, so the all-terminal check never trips and
    # the stream blocks forever holding the connection. Handling the `deleted`
    # event drops that id from the id set so completion can still be reached.
    #
    # Drive the generator against a fake subscription so the ordering is
    # deterministic: a snapshot missing the ghost, the real job going terminal,
    # then a deleted tombstone for the ghost.
    real = JobRecord(
        id="j_real",
        type="eval",
        status=BackgroundJobStatus.SUCCEEDED,
        params={},
        project_id="project1",
    )

    async def fake_subscription():
        # Snapshot only carries the real job; the ghost was deleted before we
        # subscribed, so it never shows up as a record.
        yield JobEvent(
            event="snapshot",
            data={"jobs": [real.model_dump(mode="json")]},
        )
        yield JobEvent(event="job", data=real.model_dump(mode="json"))
        # Tombstone for the ghost id arrives on the bus.
        yield JobEvent(event="deleted", data={"id": "j_ghost"})
        # Block forever afterwards, mimicking a live bus with nothing more for
        # us: if the deleted handling didn't unblock, the test would hang here.
        await asyncio.Event().wait()

    monkeypatch.setattr(
        registry.events, "subscribe", lambda *a, **k: fake_subscription()
    )

    gen = eval_jobs_api._aggregate_progress_stream("project1", ["j_real", "j_ghost"])
    chunks: list[str] = []
    async for chunk in gen:
        chunks.append(chunk)

    assert any(c.strip() == "data: complete" for c in chunks)


@pytest.mark.asyncio
async def test_keepalive_does_not_tear_down_subscription(registry, monkeypatch):
    # Regression: the old `asyncio.wait_for(subscription.__anext__(), ...)` form
    # cancelled the in-flight pull on each keepalive timeout, ending the stream
    # after the first quiet window. The shared `iter_with_keepalive` feeder-task
    # helper now keeps the subscription alive across pings.
    #
    # Drive the REAL bus (no fake subscription): one slow job whose first
    # progress event is far enough out that several keepalive intervals elapse
    # first. Assert that more than one ping is emitted across those quiet
    # intervals — proving the subscription survived. The job status is now
    # trivially unaffected by stream lifecycle (pure observer), but we still
    # assert it as a sanity check.
    monkeypatch.setattr(eval_jobs_api, "KEEPALIVE_SECONDS", 0.05)
    # A long first step (relative to the 0.05s keepalive) creates a quiet window
    # spanning many keepalive intervals before any `job` event reaches the bus.
    monkeypatch.setattr(_StubEvalWorker, "steps", 50)
    monkeypatch.setattr(_StubEvalWorker, "sleep_per_step_seconds", 0.5)

    job = await registry.create(
        "eval",
        {
            "project_id": "project1",
            "task_id": "task1",
            "eval_id": "eval1",
            "eval_config_id": "eval_config1",
            "run_config_id": "rc1",
        },
        project_id="project1",
    )

    gen = eval_jobs_api._aggregate_progress_stream("project1", [job.id])
    pings = 0
    try:
        # Consume across ~6 keepalive intervals (0.3s), well inside the 0.5s
        # first-step gap, so every chunk we pull here is a keepalive ping.
        deadline = asyncio.get_event_loop().time() + 0.3
        while asyncio.get_event_loop().time() < deadline:
            chunk = await asyncio.wait_for(gen.__anext__(), timeout=1.0)
            if chunk.strip() == ": ping":
                pings += 1

        # The subscription survived multiple pings (would have died after the
        # first under the old wait_for-cancels-__anext__ bug).
        assert pings > 1

        # Still-connected client: the job must not have been paused or cancelled
        # by a torn-down stream.
        current = registry._jobs[job.id]
        assert current.status not in (
            BackgroundJobStatus.PAUSED,
            BackgroundJobStatus.CANCELLED,
        )
    finally:
        await gen.aclose()
        # Closing the generator before completion is a disconnect: clean up the
        # still-running job so it doesn't outlive the test.
        await _safe_cleanup(registry, job.id)


async def _safe_cleanup(registry: JobRegistry, job_id: str) -> None:
    job = registry._jobs.get(job_id)
    if job is None or job.status.is_terminal:
        return
    try:
        await registry.cancel(job_id)
    except Exception:
        pass


@pytest.mark.asyncio
async def test_normal_completion_does_not_pause(client, registry):
    async with client.stream(
        "GET",
        PATH,
        params={"all_run_configs": "false", "run_config_ids": ["rc1"]},
    ) as response:
        await response.aread()

    eval_jobs = registry.list_jobs(type_name="eval", project_id="project1")
    assert len(eval_jobs) == 1
    assert eval_jobs[0].status == BackgroundJobStatus.SUCCEEDED
