---
status: complete
---

# Phase 2: REST API + SSE

## Overview

Phase 1 built the in-memory `JobRegistry` (lifecycle, semaphore, supervising
tasks, reconciliation, per-run error log) plus the `NoopJobWorker`. Phase 2
exposes that registry over HTTP without changing it: a FastAPI router
(`api.py`) covering create / list / get / result / errors / pause / resume /
cancel / delete, plus an SSE stream (`/api/jobs/events`).

The load-bearing requirement is SSE decoupling: the stream is a pure observer
of the Phase 1 event bus. A client disconnect tears down only the subscription
(unsubscribe + stop keepalive); it must never cancel, pause, or otherwise touch
a job's supervising task. Jobs keep running; only explicit `cancel`/`pause`
stops them.

Follows functional_spec §5 (REST) and §6 (SSE) exactly. Paths are `/api/jobs/...`
(not project-scoped). Auth mirrors the studio convention (`openapi_extra`
policy constants, no FastAPI auth dependency). Error envelope is the existing
convention (`HTTPException(detail=...)`).

## Steps

1. **`app/desktop/studio_server/jobs/api.py`** — new module exposing the
   process-singleton `job_registry` over HTTP via `connect_jobs_api(app: FastAPI)`.

   - Request/response models:
     - `CreateJobRequest(BaseModel)`: `params: dict[str, Any]`,
       `metadata: dict[str, Any] | None = None`. (`project_id` is derived from
       params when the params model carries one, not from the request body.)
     - `CreateJobResponse(BaseModel)`: `job_id: str`, `status: JobStatus`.
   - Helper `_project_id_from_params(worker, validated_params) -> str | None`:
     returns `getattr(validated, "project_id", None)` so eval jobs get a
     `project_id` and noop jobs get `null`. (Open item #2/#3: plain optional
     filter, no server-side active project.)
   - Helper `_record_json(record: JobRecord) -> dict`: `record.model_dump(mode="json")`.

   Route ordering (declared before the `{id}`/`{type}` catch-alls so they are
   not shadowed):
   - `GET /api/jobs/events` — SSE (declared first).
   - `GET /api/jobs` — list with filters.
   - Then the dynamic routes. POST uses `{type}`; GET/DELETE use `{id}`. They do
     not collide because they are different HTTP methods on distinct subpaths
     (`POST /api/jobs/{type}` vs `GET /api/jobs/{id}` etc.), and the sub-action
     routes (`/{id}/result`, `/{id}/errors`, `/{id}/pause|resume|cancel`) have
     an extra path segment.

   Endpoints:
   - `POST /api/jobs/{type}` (`openapi_extra=ALLOW_AGENT`): validate the type is
     registered (404 `JobOperationError` → 404 if unknown type) and `params`
     against `params_model` (pydantic `ValidationError` → 422). Derive
     `project_id`. `await job_registry.create(...)`. Return
     `201 CreateJobResponse`.
     - Unknown type → 404. Implementation: check `type in registry workers`
       before validating; raise `HTTPException(404)`.
     - Invalid params → 422 (raise `RequestValidationError`/`HTTPException(422)`
       from the caught pydantic `ValidationError`).
   - `GET /api/jobs` (`ALLOW_AGENT`): query params `status`, `type`,
     `project_id`, `since` (iso8601 datetime), `limit` (int). Maps to
     `registry.list_jobs(...)`. Returns `200 list[JobRecord]` (serialized),
     default sort `created_at desc` (registry already does this).
   - `GET /api/jobs/{id}` (`ALLOW_AGENT`): `await registry.get(id)` (reconciles +
     emits). 404 if `None`. Returns `200 <record>`.
   - `GET /api/jobs/{id}/result` (`ALLOW_AGENT`): get record (no reconcile
     needed beyond `get`); 404 if unknown, 404 if not terminal or `result is
     None`. Returns `200 <result dict>`.
   - `GET /api/jobs/{id}/errors` (`ALLOW_AGENT`): optional `run_id` query.
     Resolve the run_id (query param if given, else the record's current
     `run_id`). ALWAYS `200`. Returns `error_log.read_errors(run_id)` or `[]`
     (also `[]` when the job is unknown or has no run_id — never errors).
   - `POST /api/jobs/{id}/pause` (mutation policy mirroring eval mutations →
     `agent_policy_require_approval(...)`): `await registry.pause(id)`;
     `JobNotFoundError` → 404, `JobOperationError` → 409. Return `202` (empty
     body, `status_code=202`).
   - `POST /api/jobs/{id}/resume`: same pattern, `registry.resume`. 202 / 404 / 409.
   - `POST /api/jobs/{id}/cancel`: same pattern, `registry.cancel`. 202 / 404 / 409.
   - `DELETE /api/jobs/{id}`: `await registry.delete(id)`; 404 / 409. Return
     `204` (`status_code=204`, no body).
   - `GET /api/jobs/events` (`ALLOW_AGENT`): query `job_id`, `type`, `project_id`.
     Returns `CancellableStreamingResponse(content=_event_stream(...),
     media_type="text/event-stream")`.

   SSE generator `_event_stream(job_id, type_name, project_id)`:
   - `subscription = job_registry.events.subscribe(job_id, type_name, project_id)`.
   - Loop: `event = await asyncio.wait_for(subscription.__anext__(), timeout=KEEPALIVE_SECONDS)`;
     on success `yield _format_sse(event)`; on `asyncio.TimeoutError` `yield ": ping\n\n"`.
   - `finally: await subscription.aclose()` (unsubscribe via the generator's
     `finally`). Cancelling the generator (client disconnect via
     `CancellableStreamingResponse`) only closes the subscription — the registry
     and its supervising tasks are untouched.
   - `_format_sse(event: JobEvent) -> str`: `f"event: {event.event}\n"` +
     `f"data: {json.dumps(event.data)}\n\n"` (matches the `event:`/`data:` wire
     format; snapshot/job/deleted carry their `data` dict as built by the bus).
   - `KEEPALIVE_SECONDS = 15` (open item #9).

2. **Wire into `desktop_server.py`** — add `connect_jobs_api(app)` in
   `make_app()` alongside the other `connect_*_api(app)` calls, before
   `connect_webhost(app)` (which stays last). The `connect_jobs_api` function
   registers `NoopJobWorker` on the singleton `job_registry` (idempotent: guard
   against double-registration of the same type so repeated `make_app()` calls
   in tests don't error). Do NOT register `EvalJobWorker` (Phase 3). The
   registry creates asyncio tasks lazily inside `create`, which runs within a
   request's running loop, so no special lifespan startup is needed (registration
   is pure dict mutation, loop-safe).

3. **Regenerate the OpenAPI client schema** — after the API is in, run
   `app/web_ui/src/lib/generate_schema.sh` so `api_schema.d.ts` reflects the new
   endpoints and `check_schema.sh` passes. Leave the regenerated file in the
   working tree (do not commit).

## Tests

`app/desktop/studio_server/jobs/test_api.py` using FastAPI `TestClient` (sync
endpoints) and `httpx.AsyncClient` + `ASGITransport` for the streaming
decoupling test. A fresh `JobRegistry` is patched in per test (module-level
`job_registry` reference) so tests are isolated; `NoopJobWorker` registered.
`temp_error_log_dir` autouse fixture (monkeypatch tempdir) mirrors
`test_registry.py`.

- `test_create_returns_201_and_pending` — `POST /api/jobs/noop` with valid
  params returns 201, body has `job_id` + `status` in {pending, running}.
- `test_create_unknown_type_404` — `POST /api/jobs/nope` → 404.
- `test_create_invalid_params_422` — `POST /api/jobs/noop` with `steps:"abc"` → 422.
- `test_list_empty` — `GET /api/jobs` → 200 `[]`.
- `test_list_returns_jobs_sorted_desc` — create two jobs, list returns newest first.
- `test_list_filter_by_status_and_type` — filters narrow results.
- `test_list_filter_by_project_id` — only matching project_id returned (uses a
  worker whose params carry project_id, or asserts noop → null filtered out).
- `test_list_since_and_limit` — `since` excludes older, `limit` caps count.
- `test_get_returns_record` — `GET /api/jobs/{id}` → 200 with full record.
- `test_get_unknown_404` — `GET /api/jobs/j_missing` → 404.
- `test_get_reconciles` — a worker whose compute_state flips to complete is
  reconciled to succeeded on GET (mirrors registry reconcile test via a stub
  worker registered on the test registry).
- `test_result_returns_200_when_terminal` — succeeded noop → 200 result dict
  `{"completed_steps": n}`.
- `test_result_404_when_not_terminal` — running job → 404.
- `test_result_404_unknown` — unknown id → 404.
- `test_errors_returns_array` — job with `error_at_steps` → 200 list of error
  objects with `error_message`.
- `test_errors_empty_when_none` — succeeded clean job → 200 `[]`.
- `test_errors_unknown_job_returns_empty_200` — unknown id → 200 `[]` (never 404).
- `test_errors_specific_run_id` — `?run_id=` reads that run's log.
- `test_pause_then_resume` — pause running → 202, status paused; resume → 202.
- `test_pause_409_when_not_running` — pause terminal → 409.
- `test_pause_409_when_unsupported` — non-pausable worker → 409.
- `test_resume_409_when_not_paused` — resume running → 409.
- `test_cancel_202` — cancel running → 202, becomes cancelled.
- `test_cancel_409_when_terminal` — cancel succeeded → 409.
- `test_cancel_unknown_404` — cancel unknown → 404.
- `test_delete_204_when_terminal` — delete succeeded → 204, gone from list.
- `test_delete_409_when_in_flight` — delete running → 409.
- `test_delete_unknown_404` — delete unknown → 404.
- SSE:
  - `test_sse_snapshot_then_job_event` — async client streams `/api/jobs/events`,
    first event is `snapshot` (empty), then create a noop and observe a `job`
    event carrying the record.
  - `test_sse_disconnect_leaves_job_running` (DECOUPLING) — start a long noop,
    connect + read snapshot/a job event, disconnect the stream mid-run, then
    assert via the registry that the job continues and reaches succeeded. Proves
    the stream is a pure observer.
  - `test_sse_filters_by_job_id` — subscribing with `?job_id=` only sees that
    job's events.
- `test_connect_jobs_api_registers_noop_idempotently` — calling
  `connect_jobs_api` twice does not raise (guard) and registers noop.
