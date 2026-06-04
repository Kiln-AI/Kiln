from __future__ import annotations

import asyncio
import json
import uuid

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
from app.desktop.studio_server.jobs.workers.noop import NoopJobWorker
from fastapi import FastAPI
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
def fast_keepalive(monkeypatch):
    # httpx's ASGITransport batches the SSE generator's output and only surfaces
    # buffered lines once the next chunk (here, the keepalive ping) forces a
    # flush. Shortening the keepalive makes that flush — and stream teardown —
    # prompt in tests. Production keeps the 15s default.
    monkeypatch.setattr(jobs_api, "KEEPALIVE_SECONDS", 0.1)


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
    ReconcileCompleteWorker.done = False
    resp = await client.post("/api/jobs/reconcile_complete", json={"params": {}})
    job_id = resp.json()["job_id"]
    await _wait_for_status(registry, job_id, BackgroundJobStatus.RUNNING)
    ReconcileCompleteWorker.done = True
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


async def _read_until_event(line_iter, target: str, timeout: float = 3.0) -> dict:
    """Read SSE blocks from a shared line iterator until one matches the target
    event name; return its data. httpx allows streaming the body only once, so a
    single iterator must be threaded through all reads on a response."""
    buffer = ""
    while True:
        line = await asyncio.wait_for(line_iter.__anext__(), timeout=timeout)
        if line == "":
            event_name, data = _parse_sse_block(buffer)
            buffer = ""
            if event_name == target and data is not None:
                return data
        else:
            buffer += line + "\n"


@pytest.mark.asyncio
async def test_sse_empty_snapshot(app, fast_keepalive):
    # Connecting with no jobs yields an empty snapshot. (httpx's ASGITransport
    # sends http.disconnect right after the GET body, so we only assert the
    # initial snapshot here; live-event delivery is covered below with a job
    # that is already running before we connect.)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as http_client:
        async with http_client.stream("GET", "/api/jobs/events") as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            snapshot = await _read_until_event(response.aiter_lines(), "snapshot")
            assert snapshot == {"jobs": []}


@pytest.mark.asyncio
async def test_sse_snapshot_then_job_event(app, registry, fast_keepalive):
    # Start a long-running job first, so it appears in the snapshot and keeps
    # emitting live `job` progress events while we observe the stream.
    job = await registry.create("noop", {"steps": 40, "sleep_per_step_seconds": 0.05})

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as http_client:
        async with http_client.stream("GET", "/api/jobs/events") as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            lines = response.aiter_lines()

            snapshot = await _read_until_event(lines, "snapshot")
            assert [j["id"] for j in snapshot["jobs"]] == [job.id]

            data = await _read_until_event(lines, "job")
            assert data["id"] == job.id
            assert data["type"] == "noop"

    await _safe_cancel(registry, job.id)


@pytest.mark.asyncio
async def test_sse_filters_by_job_id(app, registry, fast_keepalive):
    # Both jobs run; only `target`'s events should reach a job_id-filtered stream.
    other = await registry.create("noop", {"steps": 40, "sleep_per_step_seconds": 0.05})
    target = await registry.create(
        "noop", {"steps": 40, "sleep_per_step_seconds": 0.05}
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as http_client:
        async with http_client.stream(
            "GET", "/api/jobs/events", params={"job_id": target.id}
        ) as response:
            lines = response.aiter_lines()
            snapshot = await _read_until_event(lines, "snapshot")
            snapshot_ids = {j["id"] for j in snapshot["jobs"]}
            assert target.id in snapshot_ids
            assert other.id not in snapshot_ids

            # The progress event that arrives is for the target, never `other`.
            data = await _read_until_event(lines, "job")
            assert data["id"] == target.id

    await _safe_cancel(registry, other.id)
    await _safe_cancel(registry, target.id)


@pytest.mark.asyncio
async def test_sse_disconnect_leaves_job_running(app, registry, fast_keepalive):
    """The decoupling guarantee: dropping the SSE stream mid-run must NOT stop
    the job. Only explicit cancel/pause stops a job."""
    job = await registry.create("noop", {"steps": 6, "sleep_per_step_seconds": 0.05})

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as http_client:
        async with http_client.stream("GET", "/api/jobs/events") as response:
            lines = response.aiter_lines()
            await _read_until_event(lines, "snapshot")
            # Observe at least one live job event so we know the run is underway.
            await _read_until_event(lines, "job")
        # Exiting the `stream` context drops the client connection, which cancels
        # the SSE subscription generator (CancellableStreamingResponse). The job
        # task lives in the registry and must keep running.

    assert registry._jobs[job.id].status in (
        BackgroundJobStatus.RUNNING,
        BackgroundJobStatus.SUCCEEDED,
    )
    await _wait_for_status(registry, job.id, BackgroundJobStatus.SUCCEEDED)
    assert registry._jobs[job.id].result == {"completed_steps": 6}
