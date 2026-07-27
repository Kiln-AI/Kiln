from __future__ import annotations

import asyncio
import json
import uuid

from unittest.mock import patch

import httpx
import pytest
import pytest_asyncio
from app.desktop.studio_server.jobs import api as jobs_api
from app.desktop.studio_server.jobs import error_log
from app.desktop.studio_server.jobs.api import connect_jobs_api
from app.desktop.studio_server.jobs.models import (
    BackgroundJobStatus,
    JobDerivedState,
    JobWorker,
)
from app.desktop.studio_server.jobs.registry import JobOperationError, JobRegistry
from app.desktop.studio_server.jobs.workers.eval import (
    EvalJobResult,
    EvalJobWorker,
)
from app.desktop.studio_server.jobs.workers.noop import NoopJobWorker
from fastapi import FastAPI
from kiln_ai.datamodel import TaskOutputRatingType
from kiln_ai.datamodel.eval import Eval, EvalOutputScore
from pydantic import BaseModel


async def _safe_cancel(registry: JobRegistry, job_id: str) -> None:
    """Best-effort cleanup cancel; ignore a job that already reached terminal."""
    try:
        await registry.cancel(job_id)
    except JobOperationError:
        pass


@pytest.fixture(autouse=True)
def temp_error_log_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.desktop.studio_server.jobs.error_log.tempfile.gettempdir",
        lambda: str(tmp_path),
    )


# -- supporting test workers -------------------------------------------------


class _ProjectParams(BaseModel):
    project_id: str
    steps: int = 50
    sleep_per_step_seconds: float = 0.05


class _EmptyResult(BaseModel):
    pass


class ProjectScopedWorker(JobWorker[_ProjectParams, _EmptyResult]):
    """A worker whose params carry a project_id, so the record gets one."""

    type_name = "project_scoped"
    params_model = _ProjectParams
    result_model = _EmptyResult
    supports_pause = True

    async def run(self, params, ctx):
        await asyncio.sleep(5)
        return _EmptyResult()


class _EmptyParams(BaseModel):
    pass


class ReconcileCompleteWorker(JobWorker[_EmptyParams, _EmptyResult]):
    """compute_state flips to complete once `done` is set, so a GET reconciles
    the running job straight to succeeded."""

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


class NonPausableWorker(JobWorker[_EmptyParams, _EmptyResult]):
    type_name = "nonpausable"
    params_model = _EmptyParams
    result_model = _EmptyResult
    supports_pause = False

    async def run(self, params, ctx):
        await asyncio.sleep(5)
        return _EmptyResult()


# -- fixtures ----------------------------------------------------------------


@pytest.fixture
def registry(monkeypatch):
    """Patch a fresh registry in for isolation, then register the test workers."""
    reg = JobRegistry(max_concurrent=10)
    monkeypatch.setattr(jobs_api, "job_registry", reg)
    reg.register_type(NoopJobWorker)
    reg.register_type(ProjectScopedWorker)
    reg.register_type(ReconcileCompleteWorker)
    reg.register_type(NonPausableWorker)
    return reg


@pytest.fixture
def app(registry):
    app = FastAPI()
    connect_jobs_api(app)
    return app


@pytest_asyncio.fixture
async def client(app):
    # Async client over ASGI so handlers AND the registry's background tasks
    # share the test's event loop — background jobs progress while we await.
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as http_client:
        yield http_client


async def _wait_for_status(
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


async def _create_noop(registry: JobRegistry, **params) -> str:
    body = {"steps": 50, "sleep_per_step_seconds": 0.05}
    body.update(params)
    job = await registry.create("noop", body)
    return job.id


# -- create eval (typed endpoint) --------------------------------------------


_EVAL_PARAMS = {
    "project_id": "p_eval",
    "task_id": "t1",
    "eval_id": "e1",
    "eval_config_id": "ec1",
    "run_config_id": "rc1",
    "concurrency": None,
    "split": None,
}


_EVAL_RUN_PATH = "/api/jobs/evals/run"


@pytest.fixture
def stub_eval_worker(monkeypatch):
    """Keep the EvalJobWorker off disk so the eval-run endpoint can be exercised
    without real Kiln entities: compute_state is a no-op and run returns a
    fixed result."""

    async def fake_compute_state(self, params):
        return None

    async def fake_run(self, params, ctx):
        return EvalJobResult(total=0, success=0, error=0)

    monkeypatch.setattr(EvalJobWorker, "compute_state", fake_compute_state)
    monkeypatch.setattr(EvalJobWorker, "run", fake_run)


@pytest.mark.asyncio
async def test_run_eval_job_creates_typed_eval_job(client, registry, stub_eval_worker):
    resp = await client.post(_EVAL_RUN_PATH, json=_EVAL_PARAMS)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    job_id = body["job_id"]
    assert body["status"] in {
        BackgroundJobStatus.PENDING.value,
        BackgroundJobStatus.RUNNING.value,
    }

    job = registry._jobs[job_id]
    assert job.type == "eval"
    assert job.project_id == "p_eval"
    assert job.params == _EVAL_PARAMS


@pytest.mark.asyncio
async def test_run_eval_job_invalid_params_422(client, registry):
    # Missing required eval params.
    resp = await client.post(_EVAL_RUN_PATH, json={"project_id": "p_eval"})
    assert resp.status_code == 422


def _eval_with_splits(train_set_filter_id: str | None) -> Eval:
    return Eval(
        id="e1",
        name="Test Eval",
        eval_set_filter_id="tag::eval_set",
        eval_configs_filter_id="tag::golden",
        train_set_filter_id=train_set_filter_id,
        output_scores=[
            EvalOutputScore(
                name="Accuracy",
                instruction="Check accuracy",
                type=TaskOutputRatingType.pass_fail,
            ),
        ],
    )


@pytest.mark.asyncio
async def test_run_eval_job_with_split_creates_job(client, registry, stub_eval_worker):
    with patch.object(
        jobs_api, "eval_from_id", return_value=_eval_with_splits("tag::train_set")
    ) as mock_eval_from_id:
        resp = await client.post(
            _EVAL_RUN_PATH, json={**_EVAL_PARAMS, "split": "train"}
        )

    assert resp.status_code == 201, resp.text
    mock_eval_from_id.assert_called_once_with("p_eval", "t1", "e1")
    job = registry._jobs[resp.json()["job_id"]]
    assert job.params == {**_EVAL_PARAMS, "split": "train"}


@pytest.mark.asyncio
async def test_run_eval_job_split_unset_on_eval_422(client, registry):
    # The eval exists but has no train split configured: fail at creation with
    # a 422 — never create a job doomed to fail in the background.
    with patch.object(jobs_api, "eval_from_id", return_value=_eval_with_splits(None)):
        resp = await client.post(
            _EVAL_RUN_PATH, json={**_EVAL_PARAMS, "split": "train"}
        )

    assert resp.status_code == 422
    assert "no train split configured" in resp.json()["detail"]
    assert registry._jobs == {}


@pytest.mark.asyncio
async def test_run_eval_job_unknown_split_422(client, registry):
    resp = await client.post(_EVAL_RUN_PATH, json={**_EVAL_PARAMS, "split": "golden"})
    assert resp.status_code == 422
    assert registry._jobs == {}


@pytest.mark.asyncio
async def test_run_eval_job_without_split_skips_resolution(
    client, registry, stub_eval_worker
):
    # No split requested: today's behavior — no eval load, no resolution.
    with patch.object(jobs_api, "eval_from_id") as mock_eval_from_id:
        resp = await client.post(_EVAL_RUN_PATH, json=_EVAL_PARAMS)

    assert resp.status_code == 201, resp.text
    mock_eval_from_id.assert_not_called()


# -- list --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_empty(client):
    resp = await client.get("/api/jobs")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_returns_jobs_sorted_desc(client, registry):
    first = await _create_noop(registry)
    second = await _create_noop(registry)
    resp = await client.get("/api/jobs")
    assert resp.status_code == 200
    ids = [r["id"] for r in resp.json()]
    assert ids[0] == second
    assert ids[1] == first
    await registry.cancel(first)
    await registry.cancel(second)


@pytest.mark.asyncio
async def test_list_filter_by_type(client, registry):
    await _create_noop(registry)
    await registry.create("project_scoped", {"project_id": "p1"})
    resp = await client.get("/api/jobs", params={"type": "project_scoped"})
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["type"] == "project_scoped"


@pytest.mark.asyncio
async def test_list_filter_by_status(client, registry):
    job_id = await _create_noop(registry, steps=2, sleep_per_step_seconds=0.01)
    await _wait_for_status(registry, job_id, BackgroundJobStatus.SUCCEEDED)
    resp = await client.get("/api/jobs", params={"status": "succeeded"})
    assert [r["id"] for r in resp.json()] == [job_id]
    resp = await client.get("/api/jobs", params={"status": "running"})
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_filter_by_project_id(client, registry):
    await registry.create("project_scoped", {"project_id": "p_one"}, project_id="p_one")
    await registry.create("project_scoped", {"project_id": "p_two"}, project_id="p_two")
    resp = await client.get("/api/jobs", params={"project_id": "p_one"})
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["project_id"] == "p_one"


@pytest.mark.asyncio
async def test_list_limit(client, registry):
    for _ in range(3):
        await _create_noop(registry)
    resp = await client.get("/api/jobs", params={"limit": 2})
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_list_since_excludes_older(client, registry):
    old_id = await _create_noop(registry)
    newer_id = await _create_noop(registry)
    cutoff = registry._jobs[newer_id].created_at.isoformat()
    resp = await client.get("/api/jobs", params={"since": cutoff})
    ids = [r["id"] for r in resp.json()]
    assert newer_id in ids
    assert old_id not in ids


# -- get ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_returns_record(client, registry):
    job_id = await _create_noop(registry)
    resp = await client.get(f"/api/jobs/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == job_id
    assert body["type"] == "noop"
    assert "progress" in body
    await registry.cancel(job_id)


@pytest.mark.asyncio
async def test_get_unknown_404(client):
    resp = await client.get("/api/jobs/j_missing")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_reconciles_to_succeeded(client, registry):
    ReconcileCompleteWorker.done = False
    job = await registry.create("reconcile_complete", {})
    job_id = job.id
    await _wait_for_status(registry, job_id, BackgroundJobStatus.RUNNING)
    ReconcileCompleteWorker.done = True
    got = await client.get(f"/api/jobs/{job_id}")
    assert got.status_code == 200
    assert got.json()["status"] == "succeeded"
    assert got.json()["progress"]["success"] == 3


# -- result ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_result_200_when_terminal(client, registry):
    job_id = await _create_noop(registry, steps=3, sleep_per_step_seconds=0.01)
    await _wait_for_status(registry, job_id, BackgroundJobStatus.SUCCEEDED)
    resp = await client.get(f"/api/jobs/{job_id}/result")
    assert resp.status_code == 200
    assert resp.json() == {"completed_steps": 3}


@pytest.mark.asyncio
async def test_result_404_when_not_terminal(client, registry):
    job_id = await _create_noop(registry)
    await _wait_for_status(registry, job_id, BackgroundJobStatus.RUNNING)
    resp = await client.get(f"/api/jobs/{job_id}/result")
    assert resp.status_code == 404
    await registry.cancel(job_id)


@pytest.mark.asyncio
async def test_result_404_unknown(client):
    resp = await client.get("/api/jobs/j_missing/result")
    assert resp.status_code == 404


# -- errors ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_errors_returns_array(client, registry):
    job_id = await _create_noop(
        registry, steps=4, sleep_per_step_seconds=0.01, error_at_steps=[1, 3]
    )
    await _wait_for_status(registry, job_id, BackgroundJobStatus.SUCCEEDED)
    resp = await client.get(f"/api/jobs/{job_id}/errors")
    assert resp.status_code == 200
    messages = [e["error_message"] for e in resp.json()]
    assert "intentional error at step 1" in messages
    assert "intentional error at step 3" in messages


@pytest.mark.asyncio
async def test_errors_empty_when_none(client, registry):
    job_id = await _create_noop(registry, steps=2, sleep_per_step_seconds=0.01)
    await _wait_for_status(registry, job_id, BackgroundJobStatus.SUCCEEDED)
    resp = await client.get(f"/api/jobs/{job_id}/errors")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_errors_unknown_job_returns_empty_200(client):
    resp = await client.get("/api/jobs/j_missing/errors")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_errors_specific_run_id(client):
    run_id = str(uuid.uuid4())
    error_log.append_error(run_id, {"error_message": "from a past run"})
    resp = await client.get("/api/jobs/j_missing/errors", params={"run_id": run_id})
    assert resp.status_code == 200
    assert resp.json() == [{"error_message": "from a past run"}]


# -- pause / resume / cancel -------------------------------------------------


@pytest.mark.asyncio
async def test_pause_then_resume(client, registry):
    job_id = await _create_noop(registry, steps=50, sleep_per_step_seconds=0.03)
    await _wait_for_status(registry, job_id, BackgroundJobStatus.RUNNING)

    resp = await client.post(f"/api/jobs/{job_id}/pause")
    assert resp.status_code == 202
    assert registry._jobs[job_id].status == BackgroundJobStatus.PAUSED

    resp = await client.post(f"/api/jobs/{job_id}/resume")
    assert resp.status_code == 202
    assert registry._jobs[job_id].status in (
        BackgroundJobStatus.PENDING,
        BackgroundJobStatus.RUNNING,
    )

    await registry.cancel(job_id)


@pytest.mark.asyncio
async def test_pause_409_when_not_running(client, registry):
    job_id = await _create_noop(registry, steps=2, sleep_per_step_seconds=0.01)
    await _wait_for_status(registry, job_id, BackgroundJobStatus.SUCCEEDED)
    resp = await client.post(f"/api/jobs/{job_id}/pause")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_pause_409_when_unsupported(client, registry):
    job = await registry.create("nonpausable", {})
    job_id = job.id
    await _wait_for_status(registry, job_id, BackgroundJobStatus.RUNNING)
    resp = await client.post(f"/api/jobs/{job_id}/pause")
    assert resp.status_code == 409
    await registry.cancel(job_id)


@pytest.mark.asyncio
async def test_pause_unknown_404(client):
    resp = await client.post("/api/jobs/j_missing/pause")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_resume_409_when_not_paused(client, registry):
    job_id = await _create_noop(registry)
    await _wait_for_status(registry, job_id, BackgroundJobStatus.RUNNING)
    resp = await client.post(f"/api/jobs/{job_id}/resume")
    assert resp.status_code == 409
    await registry.cancel(job_id)


@pytest.mark.asyncio
async def test_cancel_202(client, registry):
    job_id = await _create_noop(registry)
    await _wait_for_status(registry, job_id, BackgroundJobStatus.RUNNING)
    resp = await client.post(f"/api/jobs/{job_id}/cancel")
    assert resp.status_code == 202
    assert registry._jobs[job_id].status == BackgroundJobStatus.CANCELLED


@pytest.mark.asyncio
async def test_cancel_409_when_terminal(client, registry):
    job_id = await _create_noop(registry, steps=2, sleep_per_step_seconds=0.01)
    await _wait_for_status(registry, job_id, BackgroundJobStatus.SUCCEEDED)
    resp = await client.post(f"/api/jobs/{job_id}/cancel")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_cancel_unknown_404(client):
    resp = await client.post("/api/jobs/j_missing/cancel")
    assert resp.status_code == 404


# -- delete ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_204_when_terminal(client, registry):
    job_id = await _create_noop(registry, steps=2, sleep_per_step_seconds=0.01)
    await _wait_for_status(registry, job_id, BackgroundJobStatus.SUCCEEDED)
    resp = await client.delete(f"/api/jobs/{job_id}")
    assert resp.status_code == 204
    assert job_id not in registry._jobs
    assert (await client.get("/api/jobs")).json() == []


@pytest.mark.asyncio
async def test_delete_409_when_in_flight(client, registry):
    job_id = await _create_noop(registry)
    await _wait_for_status(registry, job_id, BackgroundJobStatus.RUNNING)
    resp = await client.delete(f"/api/jobs/{job_id}")
    assert resp.status_code == 409
    await registry.cancel(job_id)


@pytest.mark.asyncio
async def test_delete_unknown_404(client):
    resp = await client.delete("/api/jobs/j_missing")
    assert resp.status_code == 404


# -- wait --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wait_many_endpoint_returns_all_records(client, registry):
    a = await _create_noop(registry, steps=2, sleep_per_step_seconds=0.02)
    b = await _create_noop(registry, steps=3, sleep_per_step_seconds=0.02)
    got = await client.post(
        "/api/jobs/wait", json={"ids": [a, b], "timeout": 10.0}, timeout=10.0
    )
    assert got.status_code == 200, got.text
    body = got.json()
    assert {r["id"] for r in body} == {a, b}
    assert all(r["status"] == "succeeded" for r in body)


@pytest.mark.asyncio
async def test_wait_many_endpoint_empty_ids_returns_empty(client):
    got = await client.post("/api/jobs/wait", json={})
    assert got.status_code == 200
    assert got.json() == []


@pytest.mark.asyncio
async def test_wait_many_endpoint_404_unknown(client, registry):
    job_id = await _create_noop(registry, steps=2, sleep_per_step_seconds=0.02)
    resp = await client.post("/api/jobs/wait", json={"ids": [job_id, "j_missing"]})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_wait_many_endpoint_504_on_timeout(client, registry):
    fast = await _create_noop(registry, steps=1, sleep_per_step_seconds=0.01)
    slow = await _create_noop(registry, steps=50, sleep_per_step_seconds=0.05)
    await _wait_for_status(registry, slow, BackgroundJobStatus.RUNNING)
    resp = await client.post(
        "/api/jobs/wait", json={"ids": [fast, slow], "timeout": 0.05}
    )
    assert resp.status_code == 504
    await registry.cancel(slow)


# -- wiring ------------------------------------------------------------------


def test_connect_jobs_api_registers_eval_idempotently(monkeypatch):
    reg = JobRegistry(max_concurrent=2)
    monkeypatch.setattr(jobs_api, "job_registry", reg)
    app = FastAPI()
    connect_jobs_api(app)
    connect_jobs_api(app)  # second call must not raise
    assert "eval" in reg._workers


# -- SSE ---------------------------------------------------------------------


def test_format_sse_wire_format():
    from app.desktop.studio_server.jobs.events import JobEvent

    event = JobEvent(event="job", data={"id": "j_abc", "status": "running"})
    wire = jobs_api._format_sse(event)
    assert wire == 'event: job\ndata: {"id": "j_abc", "status": "running"}\n\n'


@pytest.mark.asyncio
async def test_event_stream_forwards_snapshot_then_job(registry):
    # Unit-level test of the generator (independent of any HTTP transport): a
    # subscriber gets the initial snapshot, and a job created afterward produces
    # a `job` event. Proves pure-observer forwarding of the Phase 1 bus.
    stream = jobs_api._event_stream(job_id=None, type_name=None, project_id=None)
    try:
        first = await asyncio.wait_for(stream.__anext__(), timeout=3.0)
        assert first.startswith("event: snapshot\n")

        job = await registry.create(
            "noop", {"steps": 40, "sleep_per_step_seconds": 0.05}
        )
        # Drain until we see a job event for our job.
        deadline = asyncio.get_event_loop().time() + 3.0
        saw_job = False
        while asyncio.get_event_loop().time() < deadline:
            chunk = await asyncio.wait_for(stream.__anext__(), timeout=3.0)
            if chunk.startswith("event: job\n") and job.id in chunk:
                saw_job = True
                break
        assert saw_job
        await _safe_cancel(registry, job.id)
    finally:
        await stream.aclose()


def _parse_sse_block(block: str) -> tuple[str | None, dict | None]:
    event_name: str | None = None
    data: dict | None = None
    for line in block.splitlines():
        if line.startswith("event:"):
            event_name = line[len("event:") :].strip()
        elif line.startswith("data:"):
            data = json.loads(line[len("data:") :].strip())
    return event_name, data


# The SSE endpoint is now a correctly *infinite* stream (it pings forever until
# the client disconnects or the bus shuts down). httpx's ASGITransport runs the
# app to completion and buffers the whole body before returning a response, and
# its `receive()` only yields http.disconnect once the response is complete — so
# it cannot exercise an open-ended stream incrementally or simulate a mid-stream
# disconnect. We therefore drive `_event_stream` / `subscribe` directly for the
# streaming-content behavior, and keep one HTTP-level test that ends the stream
# via `events.shutdown()` so ASGITransport can return the buffered response.


async def _read_stream_until(stream, target: str, timeout: float = 3.0) -> dict:
    """Pull SSE blocks straight from the `_event_stream` async generator until
    one matches `target`; return its parsed data."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        chunk = await asyncio.wait_for(stream.__anext__(), timeout=timeout)
        event_name, data = _parse_sse_block(chunk)
        if event_name == target and data is not None:
            return data
    raise AssertionError(f"did not see event '{target}' within {timeout}s")


def _parse_sse_body(body: str) -> list[tuple[str | None, dict | None]]:
    return [_parse_sse_block(b) for b in body.split("\n\n") if b.strip()]


@pytest.mark.asyncio
async def test_sse_endpoint_returns_event_stream_and_ends_on_shutdown(app, registry):
    # Full HTTP path: correct status + content-type and an initial snapshot.
    # The stream is infinite, and ASGITransport buffers the whole body, so we
    # end it with events.shutdown() (the same hook the server uses on reload)
    # to let the buffered response come back.
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as http_client:
        get = asyncio.ensure_future(http_client.get("/api/jobs/events"))
        # Wait until the endpoint's subscription is registered, then shut the
        # bus so the (otherwise infinite) stream returns.
        for _ in range(300):
            if registry.events._subscribers:
                break
            await asyncio.sleep(0.01)
        else:
            raise AssertionError("SSE subscription never registered")
        registry.events.shutdown()

        response = await asyncio.wait_for(get, timeout=3.0)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        blocks = _parse_sse_body(response.text)
        assert ("snapshot", {"jobs": []}) in blocks


@pytest.mark.asyncio
async def test_event_stream_emits_keepalive_ping(registry, monkeypatch):
    # The keepalive is the regression we fixed: a timeout must yield a `: ping`
    # comment WITHOUT finalizing the generator, so MANY pings arrive over time.
    monkeypatch.setattr(jobs_api, "KEEPALIVE_SECONDS", 0.05)
    stream = jobs_api._event_stream(job_id=None, type_name=None, project_id=None)
    try:
        first = await asyncio.wait_for(stream.__anext__(), timeout=3.0)
        assert first.startswith("event: snapshot\n")
        # Two consecutive pings prove the stream survives repeated timeouts.
        for _ in range(2):
            chunk = await asyncio.wait_for(stream.__anext__(), timeout=3.0)
            assert chunk == ": ping\n\n"
    finally:
        await stream.aclose()


@pytest.mark.asyncio
async def test_event_stream_filters_by_job_id(registry):
    # Both jobs run; only `target`'s events reach a job_id-filtered stream.
    other = await registry.create("noop", {"steps": 40, "sleep_per_step_seconds": 0.05})
    target = await registry.create(
        "noop", {"steps": 40, "sleep_per_step_seconds": 0.05}
    )
    stream = jobs_api._event_stream(job_id=target.id, type_name=None, project_id=None)
    try:
        snapshot = await _read_stream_until(stream, "snapshot")
        snapshot_ids = {j["id"] for j in snapshot["jobs"]}
        assert target.id in snapshot_ids
        assert other.id not in snapshot_ids

        # Every live event that arrives is for the target, never `other`.
        data = await _read_stream_until(stream, "job")
        assert data["id"] == target.id
    finally:
        await stream.aclose()
    await _safe_cancel(registry, other.id)
    await _safe_cancel(registry, target.id)


@pytest.mark.asyncio
async def test_event_stream_disconnect_leaves_job_running(registry):
    """The decoupling guarantee: dropping the SSE stream mid-run must NOT stop
    the job. Only explicit cancel/pause stops a job. Closing the generator is
    exactly what CancellableStreamingResponse does on a real client disconnect."""
    job = await registry.create("noop", {"steps": 6, "sleep_per_step_seconds": 0.05})

    stream = jobs_api._event_stream(job_id=None, type_name=None, project_id=None)
    await _read_stream_until(stream, "snapshot")
    # Observe at least one live job event so we know the run is underway.
    await _read_stream_until(stream, "job")
    # Simulate the client disconnecting mid-stream.
    await stream.aclose()

    assert registry._jobs[job.id].status in (
        BackgroundJobStatus.RUNNING,
        BackgroundJobStatus.SUCCEEDED,
    )
    await _wait_for_status(registry, job.id, BackgroundJobStatus.SUCCEEDED)
    assert registry._jobs[job.id].result == {"completed_steps": 6}
