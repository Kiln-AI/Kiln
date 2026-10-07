from __future__ import annotations

import asyncio
import json
import uuid
from unittest.mock import patch

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from kiln_ai.adapters.eval.eval_runner import EvalRunner
from kiln_ai.adapters.ml_model_list import ModelProviderName
from kiln_ai.datamodel import (
    DataSource,
    DataSourceType,
    Project,
    Task,
    TaskOutput,
    TaskOutputRatingType,
    TaskRun,
)
from kiln_ai.datamodel.eval import (
    Eval,
    EvalConfig,
    EvalInputSplit,
    EvalOutputScore,
    EvalRun,
)
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.datamodel.task import StructuredOutputMode, TaskRunConfig
from pydantic import BaseModel

from app.desktop.studio_server.jobs import api as jobs_api
from app.desktop.studio_server.jobs import error_log
from app.desktop.studio_server.jobs.api import connect_jobs_api
from app.desktop.studio_server.jobs.models import (
    JOB_MAX_CONCURRENCY,
    BackgroundJobStatus,
    JobDerivedState,
    JobWorker,
)
from app.desktop.studio_server.jobs.registry import JobOperationError, JobRegistry
from app.desktop.studio_server.jobs.workers.eval import EvalJobResult, EvalJobWorker
from app.desktop.studio_server.jobs.workers.noop import NoopJobWorker


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
    generic_create_allowed = True

    async def run(self, params, ctx):
        await asyncio.sleep(5)
        return _EmptyResult()


class _EmptyParams(BaseModel):
    pass


class ReconcileCompleteWorker(JobWorker[_EmptyParams, _EmptyResult]):
    """compute_state flips to complete once `done` is set, so a GET reconciles
    the job to succeeded once no live task supervises it."""

    type_name = "reconcile_complete"
    params_model = _EmptyParams
    result_model = _EmptyResult
    supports_pause = True
    generic_create_allowed = True
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
    generic_create_allowed = True

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


async def _create_noop(client, **params) -> str:
    body = {"steps": 50, "sleep_per_step_seconds": 0.05}
    body.update(params)
    resp = await client.post("/api/jobs/noop", json={"params": body})
    assert resp.status_code == 201, resp.text
    return resp.json()["job_id"]


# -- create ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_returns_201_and_status(client):
    resp = await client.post(
        "/api/jobs/noop",
        json={"params": {"steps": 3, "sleep_per_step_seconds": 0.01}},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["job_id"].startswith("j_")
    assert body["status"] in ("pending", "running")


@pytest.mark.asyncio
async def test_create_unknown_type_404(client):
    resp = await client.post("/api/jobs/does_not_exist", json={"params": {}})
    assert resp.status_code == 404
    assert "Unknown job type" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_create_invalid_params_422(client):
    resp = await client.post("/api/jobs/noop", json={"params": {"steps": "not-an-int"}})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_stores_metadata_and_project_id(client, registry):
    resp = await client.post(
        "/api/jobs/project_scoped",
        json={"params": {"project_id": "p_abc"}, "metadata": {"source": "test"}},
    )
    assert resp.status_code == 201
    job_id = resp.json()["job_id"]
    record = registry._jobs[job_id]
    assert record.project_id == "p_abc"
    assert record.metadata == {"source": "test"}
    await registry.cancel(job_id)


@pytest.mark.asyncio
async def test_create_noop_has_null_project_id(client, registry):
    job_id = await _create_noop(client)
    assert registry._jobs[job_id].project_id is None
    await registry.cancel(job_id)


@pytest.mark.asyncio
async def test_create_explicit_project_id_scopes_typeless_job(client, registry):
    # A job whose params carry no project_id (noop) still gets scoped when the
    # request body sets project_id explicitly — this is what the project-filtered
    # jobs panel / SSE stream rely on to show such jobs.
    resp = await client.post(
        "/api/jobs/noop",
        json={
            "params": {"steps": 50, "sleep_per_step_seconds": 0.05},
            "project_id": "p_explicit",
        },
    )
    assert resp.status_code == 201
    job_id = resp.json()["job_id"]
    assert registry._jobs[job_id].project_id == "p_explicit"
    rows = (await client.get("/api/jobs", params={"project_id": "p_explicit"})).json()
    assert any(r["id"] == job_id for r in rows)
    await registry.cancel(job_id)


# -- list --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_empty(client):
    resp = await client.get("/api/jobs")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_returns_jobs_sorted_desc(client, registry):
    first = await _create_noop(client)
    second = await _create_noop(client)
    resp = await client.get("/api/jobs")
    assert resp.status_code == 200
    ids = [r["id"] for r in resp.json()]
    assert ids[0] == second
    assert ids[1] == first
    await registry.cancel(first)
    await registry.cancel(second)


@pytest.mark.asyncio
async def test_list_filter_by_type(client, registry):
    await _create_noop(client)
    await client.post("/api/jobs/project_scoped", json={"params": {"project_id": "p1"}})
    resp = await client.get("/api/jobs", params={"type": "project_scoped"})
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["type"] == "project_scoped"


@pytest.mark.asyncio
async def test_list_filter_by_status(client, registry):
    job_id = await _create_noop(client, steps=2, sleep_per_step_seconds=0.01)
    await _wait_for_status(registry, job_id, BackgroundJobStatus.SUCCEEDED)
    resp = await client.get("/api/jobs", params={"status": "succeeded"})
    assert [r["id"] for r in resp.json()] == [job_id]
    resp = await client.get("/api/jobs", params={"status": "running"})
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_filter_by_project_id(client):
    await client.post(
        "/api/jobs/project_scoped", json={"params": {"project_id": "p_one"}}
    )
    await client.post(
        "/api/jobs/project_scoped", json={"params": {"project_id": "p_two"}}
    )
    resp = await client.get("/api/jobs", params={"project_id": "p_one"})
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["project_id"] == "p_one"


@pytest.mark.asyncio
async def test_list_limit(client):
    for _ in range(3):
        await _create_noop(client)
    resp = await client.get("/api/jobs", params={"limit": 2})
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_list_since_excludes_older(client, registry):
    old_id = await _create_noop(client)
    newer_id = await _create_noop(client)
    cutoff = registry._jobs[newer_id].created_at.isoformat()
    resp = await client.get("/api/jobs", params={"since": cutoff})
    ids = [r["id"] for r in resp.json()]
    assert newer_id in ids
    assert old_id not in ids


# -- get ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_returns_record(client, registry):
    job_id = await _create_noop(client)
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
    # A running job keeps its status on a GET and takes only the new progress:
    # its worker finishes it. A paused job has no worker, so a GET finishes it.
    ReconcileCompleteWorker.done = False
    resp = await client.post("/api/jobs/reconcile_complete", json={"params": {}})
    job_id = resp.json()["job_id"]
    await _wait_for_status(registry, job_id, BackgroundJobStatus.RUNNING)
    # The supervisor's check before run() sets the total; after it, run() owns the job.
    while registry._jobs[job_id].progress.total != 3:
        await asyncio.sleep(0.01)
    ReconcileCompleteWorker.done = True
    got = await client.get(f"/api/jobs/{job_id}")
    assert got.status_code == 200
    assert got.json()["status"] == "running"
    assert got.json()["progress"]["success"] == 3

    paused = await client.post(f"/api/jobs/{job_id}/pause")
    assert paused.status_code == 202, paused.text
    got = await client.get(f"/api/jobs/{job_id}")
    assert got.status_code == 200
    assert got.json()["status"] == "succeeded"
    assert got.json()["progress"]["success"] == 3


# -- result ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_result_200_when_terminal(client, registry):
    job_id = await _create_noop(client, steps=3, sleep_per_step_seconds=0.01)
    await _wait_for_status(registry, job_id, BackgroundJobStatus.SUCCEEDED)
    resp = await client.get(f"/api/jobs/{job_id}/result")
    assert resp.status_code == 200
    assert resp.json() == {"completed_steps": 3}


@pytest.mark.asyncio
async def test_result_404_when_not_terminal(client, registry):
    job_id = await _create_noop(client)
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
    resp = await client.post(
        "/api/jobs/noop",
        json={
            "params": {
                "steps": 4,
                "sleep_per_step_seconds": 0.01,
                "error_at_steps": [1, 3],
            }
        },
    )
    job_id = resp.json()["job_id"]
    await _wait_for_status(registry, job_id, BackgroundJobStatus.SUCCEEDED)
    resp = await client.get(f"/api/jobs/{job_id}/errors")
    assert resp.status_code == 200
    messages = [e["error_message"] for e in resp.json()]
    assert "intentional error at step 1" in messages
    assert "intentional error at step 3" in messages


@pytest.mark.asyncio
async def test_errors_empty_when_none(client, registry):
    job_id = await _create_noop(client, steps=2, sleep_per_step_seconds=0.01)
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
    job_id = await _create_noop(client, steps=50, sleep_per_step_seconds=0.03)
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
    job_id = await _create_noop(client, steps=2, sleep_per_step_seconds=0.01)
    await _wait_for_status(registry, job_id, BackgroundJobStatus.SUCCEEDED)
    resp = await client.post(f"/api/jobs/{job_id}/pause")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_pause_409_when_unsupported(client, registry):
    resp = await client.post("/api/jobs/nonpausable", json={"params": {}})
    job_id = resp.json()["job_id"]
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
    job_id = await _create_noop(client)
    await _wait_for_status(registry, job_id, BackgroundJobStatus.RUNNING)
    resp = await client.post(f"/api/jobs/{job_id}/resume")
    assert resp.status_code == 409
    await registry.cancel(job_id)


@pytest.mark.asyncio
async def test_cancel_202(client, registry):
    job_id = await _create_noop(client)
    await _wait_for_status(registry, job_id, BackgroundJobStatus.RUNNING)
    resp = await client.post(f"/api/jobs/{job_id}/cancel")
    assert resp.status_code == 202
    assert registry._jobs[job_id].status == BackgroundJobStatus.CANCELLED


@pytest.mark.asyncio
async def test_cancel_409_when_terminal(client, registry):
    job_id = await _create_noop(client, steps=2, sleep_per_step_seconds=0.01)
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
    job_id = await _create_noop(client, steps=2, sleep_per_step_seconds=0.01)
    await _wait_for_status(registry, job_id, BackgroundJobStatus.SUCCEEDED)
    resp = await client.delete(f"/api/jobs/{job_id}")
    assert resp.status_code == 204
    assert job_id not in registry._jobs
    assert (await client.get("/api/jobs")).json() == []


@pytest.mark.asyncio
async def test_delete_409_when_in_flight(client, registry):
    job_id = await _create_noop(client)
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
async def test_wait_endpoint_200_terminal_record(client):
    resp = await client.post(
        "/api/jobs/noop", json={"params": {"steps": 3, "sleep_per_step_seconds": 0.02}}
    )
    job_id = resp.json()["job_id"]
    got = await client.get(f"/api/jobs/{job_id}/wait", timeout=10.0)
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["id"] == job_id
    assert body["status"] == "succeeded"
    assert body["result"] == {"completed_steps": 3}


@pytest.mark.asyncio
async def test_wait_endpoint_404_unknown(client):
    resp = await client.get("/api/jobs/j_missing/wait")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_wait_endpoint_504_on_timeout(client, registry):
    job_id = await _create_noop(client, steps=50, sleep_per_step_seconds=0.05)
    await _wait_for_status(registry, job_id, BackgroundJobStatus.RUNNING)
    resp = await client.get(f"/api/jobs/{job_id}/wait", params={"timeout": 0.01})
    assert resp.status_code == 504
    await registry.cancel(job_id)


@pytest.mark.asyncio
async def test_create_wait_true_returns_terminal_record(client):
    resp = await client.post(
        "/api/jobs/noop",
        params={"wait": "true"},
        json={"params": {"steps": 3, "sleep_per_step_seconds": 0.02}},
        timeout=10.0,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["id"].startswith("j_")
    assert body["status"] == "succeeded"
    assert body["result"] == {"completed_steps": 3}


@pytest.mark.asyncio
async def test_create_wait_false_returns_create_response(client, registry):
    resp = await client.post(
        "/api/jobs/noop",
        params={"wait": "false"},
        json={"params": {"steps": 50, "sleep_per_step_seconds": 0.05}},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["job_id"].startswith("j_")
    assert body["status"] in ("pending", "running")
    assert "result" not in body
    await registry.cancel(body["job_id"])


@pytest.mark.asyncio
async def test_create_wait_true_timeout_504(client, registry):
    resp = await client.post(
        "/api/jobs/noop",
        params={"wait": "true", "timeout": 0.01},
        json={"params": {"steps": 50, "sleep_per_step_seconds": 0.05}},
    )
    assert resp.status_code == 504
    # The job was still created and keeps running despite the awaiter timing out.
    running = [r for r in registry.list_jobs() if not r.status.is_terminal]
    assert len(running) == 1
    await registry.cancel(running[0].id)


# -- wiring ------------------------------------------------------------------


def test_connect_jobs_api_registers_noop_idempotently(monkeypatch):
    reg = JobRegistry(max_concurrent=2)
    monkeypatch.setattr(jobs_api, "job_registry", reg)
    app = FastAPI()
    connect_jobs_api(app)
    connect_jobs_api(app)  # second call must not raise
    assert "noop" in reg._workers
    assert "eval" in reg._workers


@pytest.mark.parametrize("name", ["wait", "evals"])
def test_route_segment_names_are_reserved_job_types(name):
    class ReservedWorker(NoopJobWorker):
        type_name = name

    with pytest.raises(ValueError, match="reserved"):
        JobRegistry(max_concurrent=2).register_type(ReservedWorker)


def test_static_job_routes_register_before_the_generic_create(app):
    # Routes match in registration order, so the static POST routes must come
    # before POST /api/jobs/{type}, or "wait" would be read as a job type.
    post_paths = [
        route.path
        for route in app.routes
        if "POST" in getattr(route, "methods", set())
        and getattr(route, "path", "").startswith("/api/jobs/")
    ]
    generic = post_paths.index("/api/jobs/{type}")
    assert post_paths.index("/api/jobs/wait") < generic
    assert post_paths.index("/api/jobs/evals/run") < generic


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


# -- eval jobs (typed endpoint) ------------------------------------------------


_EVAL_RUN_PATH = "/api/jobs/evals/run"

_EVAL_PARAMS = {
    "project_id": "p_split",
    "task_id": "t_split",
    "eval_id": "e_split",
    "eval_config_id": "ec_split",
    "run_config_id": "rc_split",
    "concurrency": None,
    "split": "test",
    "item_ids": None,
}


def _eval_params(**overrides) -> dict:
    return {**_EVAL_PARAMS, **overrides}


@pytest.fixture
def stub_eval_worker(monkeypatch):
    """Keep the EvalJobWorker's run off disk: compute_state is a no-op and run
    returns a fixed result. Request checks and describe() still read disk."""

    async def fake_compute_state(self, params):
        return None

    async def fake_run(self, params, ctx):
        return EvalJobResult(total=0, success=0, error=0)

    monkeypatch.setattr(EvalJobWorker, "compute_state", fake_compute_state)
    monkeypatch.setattr(EvalJobWorker, "run", fake_run)


@pytest.fixture
def split_eval(tmp_path):
    """A real on-disk eval with a test and a train split but no val split, plus
    the eval config and run config that _EVAL_PARAMS names.

    task_from_id binds project_from_id into kiln_server.task_api, so it is
    patched there (the name as looked up), not at its definition site.
    """
    project = Project(
        id="p_split", name="Split Project", path=tmp_path / "project.kiln"
    )
    project.save_to_file()
    task = Task(
        id="t_split",
        name="Split Task",
        description="test",
        instruction="do the thing",
        parent=project,
    )
    task.save_to_file()
    eval = Eval(
        id="e_split",
        name="Split Eval",
        description="test",
        eval_set_filter_id="tag::eval_set",
        train_set_filter_id="tag::train_set",
        output_scores=[
            EvalOutputScore(
                name="Accuracy",
                instruction="Check accuracy",
                type=TaskOutputRatingType.pass_fail,
            ),
        ],
        parent=task,
    )
    eval.save_to_file()
    EvalConfig(
        id="ec_split",
        name="Split Eval Config",
        model_name="gpt-4",
        model_provider="openai",
        properties={"eval_steps": ["step1"]},
        parent=eval,
    ).save_to_file()
    TaskRunConfig(
        id="rc_split",
        name="Split Run Config",
        description="test",
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
            structured_output_mode=StructuredOutputMode.json_schema,
        ),
        parent=task,
    ).save_to_file()
    with patch("kiln_server.task_api.project_from_id", return_value=project):
        yield eval


def _make_split_item(eval: Eval, tag: str) -> TaskRun:
    task = eval.parent_task()
    assert task is not None
    task_run = TaskRun(
        parent=task,
        input="test",
        input_source=DataSource(
            type=DataSourceType.synthetic,
            properties={
                "model_name": "gpt-4",
                "model_provider": "openai",
                "adapter_name": "test_adapter",
            },
        ),
        tags=[tag],
        output=TaskOutput(output="test"),
    )
    task_run.save_to_file()
    return task_run


@pytest.mark.asyncio
async def test_run_eval_job_creates_typed_eval_job(
    client, registry, stub_eval_worker, split_eval
):
    resp = await client.post(_EVAL_RUN_PATH, json=_EVAL_PARAMS)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] in {
        BackgroundJobStatus.PENDING.value,
        BackgroundJobStatus.RUNNING.value,
    }

    job = registry._jobs[body["job_id"]]
    assert job.type == "eval"
    assert job.project_id == "p_split"
    assert job.params == _EVAL_PARAMS
    # describe() runs unstubbed against the fixture's entities, and registry.create
    # swallows its exceptions. A populated block proves it succeeded.
    assert job.properties is not None
    assert job.properties["eval_name"] == "Split Eval"


@pytest.mark.asyncio
async def test_run_eval_job_without_a_split_422(client, registry, stub_eval_worker):
    params = {k: v for k, v in _EVAL_PARAMS.items() if k != "split"}
    resp = await client.post(_EVAL_RUN_PATH, json=params)

    assert resp.status_code == 422, resp.text
    assert registry._jobs == {}


@pytest.mark.asyncio
async def test_run_eval_job_with_a_split_the_eval_lacks_422(
    client, registry, stub_eval_worker, split_eval
):
    resp = await client.post(_EVAL_RUN_PATH, json=_eval_params(split="val"))

    assert resp.status_code == 422, resp.text
    # This test app is a bare FastAPI without the studio's error-shape handlers, so
    # assert on the raw body rather than a field name the real app would rewrite.
    assert "'val' split" in resp.text
    assert "e_split" in resp.text
    assert registry._jobs == {}


@pytest.mark.asyncio
async def test_run_eval_job_with_an_unknown_eval_404(
    client, registry, stub_eval_worker, split_eval
):
    resp = await client.post(_EVAL_RUN_PATH, json=_eval_params(eval_id="e_missing"))

    assert resp.status_code == 404, resp.text
    assert registry._jobs == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("override", "missing"),
    [
        ({"eval_config_id": "ec_missing"}, "ec_missing"),
        ({"run_config_id": "rc_missing"}, "rc_missing"),
    ],
)
async def test_run_eval_job_with_an_unknown_config_404(
    client, registry, stub_eval_worker, split_eval, override, missing
):
    resp = await client.post(_EVAL_RUN_PATH, json=_eval_params(**override))

    assert resp.status_code == 404, resp.text
    assert missing in resp.text
    assert registry._jobs == {}


@pytest.mark.asyncio
async def test_run_eval_job_with_a_v1_judge_on_eval_inputs_400(
    client, registry, stub_eval_worker, split_eval
):
    task = split_eval.parent_task()
    assert task is not None
    input_eval = Eval(
        id="e_inputs",
        name="Input Eval",
        description="test",
        splits={"test": EvalInputSplit(filter_id="tag::inputs")},
        output_scores=split_eval.output_scores,
        parent=task,
    )
    input_eval.save_to_file()
    EvalConfig(
        id="ec_inputs",
        name="V1 Judge",
        model_name="gpt-4",
        model_provider="openai",
        properties={"eval_steps": ["step1"]},
        parent=input_eval,
    ).save_to_file()

    resp = await client.post(
        _EVAL_RUN_PATH,
        json=_eval_params(eval_id="e_inputs", eval_config_id="ec_inputs"),
    )

    assert resp.status_code == 400, resp.text
    assert registry._jobs == {}


@pytest.mark.asyncio
async def test_run_eval_job_with_undrivable_multi_turn_items_400(
    client, registry, stub_eval_worker, split_eval
):
    with patch.object(
        EvalRunner,
        "validate_multi_turn_drive_readiness",
        side_effect=ValueError("run config 'MCP one' is not a Kiln agent config"),
    ):
        resp = await client.post(_EVAL_RUN_PATH, json=_EVAL_PARAMS)

    assert resp.status_code == 400, resp.text
    assert "MCP one" in resp.text
    assert registry._jobs == {}


@pytest.mark.asyncio
async def test_run_eval_job_with_items_outside_their_world_400(
    client, registry, stub_eval_worker, split_eval
):
    with patch.object(
        EvalRunner,
        "validate_world_readiness",
        side_effect=ValueError(
            "Cannot run this eval's items in their worlds: eval input ei_1 has no "
            "world_reset."
        ),
    ):
        resp = await client.post(_EVAL_RUN_PATH, json=_EVAL_PARAMS)

    assert resp.status_code == 400, resp.text
    assert "ei_1" in resp.text
    assert registry._jobs == {}


@pytest.mark.asyncio
async def test_run_eval_job_checks_the_worlds_of_the_requested_items(
    client, registry, stub_eval_worker, split_eval
):
    with patch.object(EvalRunner, "validate_world_readiness") as check:
        resp = await client.post(_EVAL_RUN_PATH, json=_EVAL_PARAMS)

    assert resp.status_code == 201, resp.text
    check.assert_called_once_with()


def _torn_read() -> json.JSONDecodeError:
    # What a load raises on a file that another writer has truncated and not yet
    # written.
    return json.JSONDecodeError("Expecting value", "", 0)


@pytest.mark.asyncio
async def test_run_eval_job_reads_again_after_a_torn_read(
    client, registry, stub_eval_worker, split_eval, monkeypatch
):
    monkeypatch.setattr("kiln_ai.utils.torn_read.TORN_READ_RETRY_DELAY_SECONDS", 0)
    original = jobs_api.task_run_config_from_id
    calls: list[int] = []

    def task_run_config_from_id(*args):
        calls.append(1)
        if len(calls) == 1:
            raise _torn_read()
        return original(*args)

    monkeypatch.setattr(jobs_api, "task_run_config_from_id", task_run_config_from_id)

    resp = await client.post(_EVAL_RUN_PATH, json=_EVAL_PARAMS)

    assert resp.status_code == 201, resp.text
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_run_eval_job_is_503_when_the_read_stays_torn(
    client, registry, stub_eval_worker, split_eval, monkeypatch
):
    # A file that is still unreadable after the retry is a server state, not a bad
    # request: the client can try again.
    monkeypatch.setattr("kiln_ai.utils.torn_read.TORN_READ_RETRY_DELAY_SECONDS", 0)

    def task_run_config_from_id(*args):
        raise _torn_read()

    monkeypatch.setattr(jobs_api, "task_run_config_from_id", task_run_config_from_id)

    resp = await client.post(_EVAL_RUN_PATH, json=_EVAL_PARAMS)

    assert resp.status_code == 503, resp.text
    assert "try again" in resp.json()["detail"]
    assert resp.headers["retry-after"] == "1"
    assert registry._jobs == {}


@pytest.mark.asyncio
async def test_run_eval_job_torn_read_in_the_runner_check_is_503_not_400(
    client, registry, stub_eval_worker, split_eval, monkeypatch
):
    # JSONDecodeError is a ValueError. The runner check maps a ValueError to 400,
    # so a torn read there must not be taken for a bad request.
    monkeypatch.setattr("kiln_ai.utils.torn_read.TORN_READ_RETRY_DELAY_SECONDS", 0)
    with patch.object(
        EvalRunner, "validate_multi_turn_drive_readiness", side_effect=_torn_read()
    ):
        resp = await client.post(_EVAL_RUN_PATH, json=_EVAL_PARAMS)

    assert resp.status_code == 503, resp.text
    assert registry._jobs == {}


@pytest.mark.asyncio
async def test_run_eval_job_with_an_invalid_split_value_422(
    client, registry, stub_eval_worker, split_eval
):
    resp = await client.post(_EVAL_RUN_PATH, json=_eval_params(split="holdout"))

    assert resp.status_code == 422, resp.text
    assert registry._jobs == {}


@pytest.mark.asyncio
async def test_run_eval_job_with_items_outside_the_split_422(
    client, registry, stub_eval_worker, split_eval
):
    inside = _make_split_item(split_eval, "train_set")
    other_split = _make_split_item(split_eval, "eval_set")

    resp = await client.post(
        _EVAL_RUN_PATH,
        json=_eval_params(split="train", item_ids=[inside.id, other_split.id, "nope"]),
    )

    assert resp.status_code == 422, resp.text
    assert str(other_split.id) in resp.text
    assert "nope" in resp.text
    assert str(inside.id) not in resp.text
    assert registry._jobs == {}


@pytest.mark.asyncio
async def test_run_eval_job_with_empty_item_ids_422(
    client, registry, stub_eval_worker, split_eval
):
    resp = await client.post(_EVAL_RUN_PATH, json=_eval_params(item_ids=[]))

    assert resp.status_code == 422, resp.text
    assert registry._jobs == {}


@pytest.mark.asyncio
async def test_run_eval_job_with_concurrency_above_the_max_422(
    client, registry, stub_eval_worker, split_eval
):
    resp = await client.post(
        _EVAL_RUN_PATH, json=_eval_params(concurrency=JOB_MAX_CONCURRENCY + 1)
    )

    assert resp.status_code == 422, resp.text
    assert "concurrency" in resp.text
    assert registry._jobs == {}


@pytest.mark.asyncio
async def test_run_eval_job_with_concurrency_at_the_max_201(
    client, registry, stub_eval_worker, split_eval
):
    resp = await client.post(
        _EVAL_RUN_PATH, json=_eval_params(concurrency=JOB_MAX_CONCURRENCY)
    )

    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_run_eval_job_invalid_params_422(client, registry):
    resp = await client.post(_EVAL_RUN_PATH, json={"project_id": "p_split"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_generic_create_refuses_a_type_with_a_typed_endpoint(
    client, registry, split_eval
):
    # The generic route is agent-allowed; the typed route asks for approval and
    # checks the split. The generic route must not be a way around either.
    resp = await client.post("/api/jobs/eval", json={"params": _EVAL_PARAMS})

    assert resp.status_code == 400, resp.text
    assert _EVAL_RUN_PATH in resp.json()["detail"]
    assert registry._jobs == {}


class _NotOptedInWorker(JobWorker[_EmptyParams, _EmptyResult]):
    type_name = "not_opted_in"
    params_model = _EmptyParams
    result_model = _EmptyResult

    async def run(self, params, ctx):
        return _EmptyResult()


@pytest.mark.asyncio
async def test_generic_create_refuses_a_type_that_did_not_opt_in(client, registry):
    # The generic route lets an agent create a job without approval, so a worker
    # that declares nothing is refused there rather than allowed by default.
    registry.register_type(_NotOptedInWorker)

    resp = await client.post("/api/jobs/not_opted_in", json={"params": {}})

    assert resp.status_code == 400, resp.text
    assert registry._jobs == {}


def test_eval_endpoints_agent_policy(app):
    schema = app.openapi()
    run = schema["paths"][_EVAL_RUN_PATH]["post"]["x-agent-policy"]
    assert run["permission"] == "allow"
    assert run["requires_approval"] is True
    wait = schema["paths"]["/api/jobs/wait"]["post"]["x-agent-policy"]
    assert wait["permission"] == "allow"
    assert wait["requires_approval"] is False


# -- eval jobs: the contract an external client relies on ---------------------


class _ScriptedRunJob:
    """Stands in for EvalRunner.run_job: stores an EvalRun for each item, except
    items in `failing`, which raise the way a failed judge call does."""

    def __init__(self) -> None:
        self.failing: set[str] = set()
        self.seen: list[str] = []

    async def run_job(self, runner, job) -> bool:
        item_id = str(job.item.id)
        self.seen.append(item_id)
        if item_id in self.failing:
            raise ValueError(f"judge failed on {item_id}")
        EvalRun(
            parent=job.eval_config,
            dataset_id=job.item.id,
            task_run_config_id=job.task_run_config.id,
            input="test",
            output="test",
            scores={"accuracy": 1.0},
        ).save_to_file()
        return True


@pytest.fixture
def scripted_run_job():
    script = _ScriptedRunJob()

    async def run_job(runner, job) -> bool:
        return await script.run_job(runner, job)

    with patch("kiln_ai.adapters.eval.eval_runner.EvalRunner.run_job", new=run_job):
        yield script


async def _run_eval_job(client, **overrides) -> tuple[dict, list[dict]]:
    created = await client.post(_EVAL_RUN_PATH, json=_eval_params(**overrides))
    assert created.status_code == 201, created.text
    job_id = created.json()["job_id"]
    waited = await client.post(
        "/api/jobs/wait", json={"ids": [job_id], "timeout": 10.0}, timeout=10.0
    )
    assert waited.status_code == 200, waited.text
    assert waited.json()[0]["id"] == job_id
    # GET reconciles against disk, which is where a lost error count would show.
    record = (await client.get(f"/api/jobs/{job_id}")).json()
    errors = (await client.get(f"/api/jobs/{job_id}/errors")).json()
    return record, errors


@pytest.mark.asyncio
async def test_eval_job_contract_failures_retries_and_skips(
    client, registry, split_eval, scripted_run_job
):
    items = [_make_split_item(split_eval, "train_set") for _ in range(3)]
    _make_split_item(split_eval, "eval_set")
    failing_id = str(items[1].id)
    scripted_run_job.failing = {failing_id}

    # A failed item does not fail the job. It stays counted in progress.error, and
    # its row in the error log names the item, the run config and the store.
    record, errors = await _run_eval_job(client, split="train")
    assert record["status"] == "succeeded"
    assert record["progress"]["total"] == 3
    assert record["progress"]["success"] == 2
    assert record["progress"]["error"] == 1
    assert record["result"] == {"total": 3, "success": 2, "error": 1}
    assert len(errors) == 1
    assert "judge failed" in errors[0]["error_message"]
    assert errors[0]["dataset_id"] == failing_id
    assert errors[0]["run_config_id"] == "rc_split"
    assert errors[0]["item_source"] == "task_run"

    # The failed item stored no EvalRun, so the next job runs it and only it.
    # The total still covers the split, and the scored items count as success.
    scripted_run_job.failing = set()
    scripted_run_job.seen.clear()
    record, errors = await _run_eval_job(client, split="train")
    assert scripted_run_job.seen == [failing_id]
    assert record["status"] == "succeeded"
    assert record["progress"]["total"] == 3
    assert record["progress"]["success"] == 3
    assert record["progress"]["error"] == 0
    assert errors == []

    # A combination that is fully measured runs no item at all. The registry sees
    # it complete on disk before run() starts, so the job has progress but no result.
    scripted_run_job.seen.clear()
    record, _ = await _run_eval_job(client, split="train")
    assert scripted_run_job.seen == []
    assert record["status"] == "succeeded"
    assert record["progress"]["total"] == 3
    assert record["progress"]["success"] == 3
    assert record["progress"]["error"] == 0
    assert record["result"] is None


@pytest.mark.asyncio
async def test_eval_job_item_ids_narrow_the_job(
    client, registry, split_eval, scripted_run_job
):
    items = [_make_split_item(split_eval, "train_set") for _ in range(4)]
    named = [str(items[0].id), str(items[2].id)]

    record, _ = await _run_eval_job(client, split="train", item_ids=named)
    assert sorted(scripted_run_job.seen) == sorted(named)
    assert record["status"] == "succeeded"
    assert record["progress"]["total"] == 2
    assert record["progress"]["success"] == 2

    # The rows the subset stored are reused: the full split runs only the rest,
    # and its total covers the whole split.
    scripted_run_job.seen.clear()
    record, _ = await _run_eval_job(client, split="train")
    assert sorted(scripted_run_job.seen) == sorted([str(items[1].id), str(items[3].id)])
    assert record["progress"]["total"] == 4
    assert record["progress"]["success"] == 4


# -- multi-job wait -------------------------------------------------------------


@pytest.mark.asyncio
async def test_wait_many_endpoint_returns_records_in_id_order(client, registry):
    a = await _create_noop(client, steps=3, sleep_per_step_seconds=0.02)
    b = await _create_noop(client, steps=1, sleep_per_step_seconds=0.01)
    got = await client.post(
        "/api/jobs/wait", json={"ids": [a, b, a], "timeout": 10.0}, timeout=10.0
    )
    assert got.status_code == 200, got.text
    body = got.json()
    assert [r["id"] for r in body] == [a, b, a]
    assert all(r["status"] == "succeeded" for r in body)


@pytest.mark.asyncio
async def test_wait_many_endpoint_empty_ids_returns_empty(client):
    got = await client.post("/api/jobs/wait", json={})
    assert got.status_code == 200
    assert got.json() == []


@pytest.mark.asyncio
async def test_wait_many_endpoint_404_unknown(client, registry):
    job_id = await _create_noop(client, steps=2, sleep_per_step_seconds=0.02)
    resp = await client.post("/api/jobs/wait", json={"ids": [job_id, "j_missing"]})
    assert resp.status_code == 404
    await _safe_cancel(registry, job_id)


@pytest.mark.asyncio
async def test_wait_many_endpoint_504_on_timeout(client, registry):
    fast = await _create_noop(client, steps=1, sleep_per_step_seconds=0.01)
    slow = await _create_noop(client, steps=50, sleep_per_step_seconds=0.05)
    await _wait_for_status(registry, slow, BackgroundJobStatus.RUNNING)
    resp = await client.post(
        "/api/jobs/wait", json={"ids": [fast, slow], "timeout": 0.05}
    )
    assert resp.status_code == 504
    await registry.cancel(slow)


@pytest.mark.asyncio
async def test_wait_many_endpoint_rejects_an_unbounded_timeout(client):
    resp = await client.post("/api/jobs/wait", json={"ids": [], "timeout": 3601})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_identical_eval_job_request_returns_the_unfinished_job(
    client, registry, split_eval, monkeypatch
):
    # Two identical requests while the first job is still running get the same job,
    # so the same items are not scored (and paid for) twice. Concurrency is not part
    # of the identity; a different split is a different job.
    release = asyncio.Event()

    async def fake_compute_state(self, params):
        return None

    async def held_run(self, params, ctx):
        await release.wait()
        return EvalJobResult(total=0, success=0, error=0)

    monkeypatch.setattr(EvalJobWorker, "compute_state", fake_compute_state)
    monkeypatch.setattr(EvalJobWorker, "run", held_run)
    try:
        first = await client.post(_EVAL_RUN_PATH, json=_EVAL_PARAMS)
        again = await client.post(_EVAL_RUN_PATH, json=_eval_params(concurrency=5))
        other = await client.post(_EVAL_RUN_PATH, json=_eval_params(split="train"))
    finally:
        release.set()

    assert first.status_code == 201, first.text
    assert again.status_code == 201, again.text
    assert other.status_code == 201, other.text
    assert again.json()["job_id"] == first.json()["job_id"]
    assert other.json()["job_id"] != first.json()["job_id"]
    assert len(registry._jobs) == 2


@pytest.mark.asyncio
async def test_identical_eval_job_request_returns_a_paused_job_as_is(
    client, registry, split_eval, monkeypatch
):
    # A pause that the user set stays in place: an identical request gets the paused
    # job back with status paused, and does not resume it. A wait on it times out
    # until someone resumes it, so the client reads `status` and resumes it itself.
    release = asyncio.Event()

    async def fake_compute_state(self, params):
        return None

    async def held_run(self, params, ctx):
        await release.wait()
        return EvalJobResult(total=0, success=0, error=0)

    monkeypatch.setattr(EvalJobWorker, "compute_state", fake_compute_state)
    monkeypatch.setattr(EvalJobWorker, "run", held_run)
    try:
        first = await client.post(_EVAL_RUN_PATH, json=_EVAL_PARAMS)
        assert first.status_code == 201, first.text
        job_id = first.json()["job_id"]
        await _wait_for_status(registry, job_id, BackgroundJobStatus.RUNNING)
        paused = await client.post(f"/api/jobs/{job_id}/pause")
        assert paused.status_code == 202, paused.text

        again = await client.post(_EVAL_RUN_PATH, json=_EVAL_PARAMS)
        assert again.status_code == 201, again.text
        assert again.json() == {"job_id": job_id, "status": "paused"}
        assert registry._jobs[job_id].status == BackgroundJobStatus.PAUSED
        assert len(registry._jobs) == 1

        waited = await client.post(
            "/api/jobs/wait", json={"ids": [job_id], "timeout": 0.1}
        )
        assert waited.status_code == 504

        resumed = await client.post(f"/api/jobs/{job_id}/resume")
        assert resumed.status_code == 202, resumed.text
        await _wait_for_status(registry, job_id, BackgroundJobStatus.RUNNING)
    finally:
        release.set()
    await _wait_for_status(registry, job_id, BackgroundJobStatus.SUCCEEDED)
