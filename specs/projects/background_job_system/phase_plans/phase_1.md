---
status: complete
---

# Phase 1: Core layer + NoopJob (no HTTP)

## Overview

Build the in-memory core of the background job system inside a new package
`app/desktop/studio_server/jobs/`. This phase delivers the data models, the
worker contract, the in-process event bus, the per-run error log, and the
`JobRegistry` singleton that owns the full job lifecycle. No FastAPI router and
no SSE endpoint — those land in Phase 2. The only consumer wired up here is the
`NoopJobWorker` fixture, which is exercised end-to-end by Python tests.

The design follows `functional_spec.md` and `architecture.md` exactly:

- Job records are ephemeral, in-memory only. No disk persistence of state.
- Status/progress is reconciled against `worker.compute_state(params)` at every
  lifecycle transition (start, pause, resume) and on `get`. `None` means keep
  the believed snapshot.
- The supervising `asyncio.Task` per running job is owned by the registry and
  decoupled from any HTTP connection.
- A fresh `run_id` (uuid4) is minted per `run()` invocation. Error messages
  (`report_error` + the fatal exception of a failed run) spill to a best-effort
  per-`run_id` JSON file in the OS temp dir.
- Pause = `task.cancel()` -> `paused`; resume = a fresh `run()`. No
  `interrupted` state, no checkpoints, no `resume()` method.

## Steps

1. `jobs/__init__.py` — empty package marker.

2. `jobs/models.py` — pydantic v2 models and the worker contract.
   - `JobStatus(str, Enum)`: `PENDING="pending"`, `RUNNING="running"`,
     `PAUSED="paused"`, `SUCCEEDED="succeeded"`, `FAILED="failed"`,
     `CANCELLED="cancelled"`. Add a `terminal` helper / set
     `{SUCCEEDED, FAILED, CANCELLED}`.
   - `JobProgress(BaseModel)`: `total: int | None = None`, `success: int = 0`,
     `error: int = 0`, `message: str | None = None`,
     `updated_at: datetime` (default factory utc now).
   - `JobDerivedState(BaseModel)`: `total: int | None = None`, `success: int = 0`,
     `error: int = 0`, `is_complete: bool = False`, `message: str | None = None`.
   - `JobError(BaseModel)`: `error: str | None = None`,
     `detail: dict | None = None` — small failure summary on the record.
   - `JobRecord(BaseModel)`: fields per functional_spec §1 — `id`, `type`,
     `status: JobStatus`, `run_id: str | None`, `progress: JobProgress`,
     `params: dict`, `result: dict | None`, `error: JobError | None`,
     `metadata: dict`, `project_id: str | None`, `supports_pause: bool`,
     `created_at`, `updated_at`, `started_at: datetime | None`,
     `ended_at: datetime | None`.
   - `JobContext`: holds `job_id`, `run_id`, and references to the registry's
     progress-reporting + error-logging callbacks. Async methods:
     `report_progress(success, error=0, total=None, message=None)` and
     `report_error(error_message, **extra)`. Implemented as a small class taking
     two async callables so the registry can inject behavior without a circular
     import.
   - `JobWorker(Generic[TParams, TResult])`: classvars `type_name`,
     `params_model`, `result_model`, `supports_pause: bool = False`. Methods
     `async def compute_state(self, params) -> JobDerivedState | None` (default
     returns `None`) and `async def run(self, params, ctx) -> TResult` (raises
     `NotImplementedError`).

3. `jobs/events.py` — in-process async pub/sub bus.
   - `JobEvent` union shape: emit dataclass/pydantic events of kind
     `snapshot` / `job` / `deleted`. Keep it simple: a small `JobEvent` model
     with `event: Literal["snapshot","job","deleted"]` and a `data` payload.
   - `JobEventBus`: holds a set of subscriber `asyncio.Queue`s. `subscribe()`
     is an async generator / context that registers a queue, immediately yields
     a `snapshot` event (built from a snapshot provider callback) filtered by
     `job_id` / `type` / `project_id`, then yields subsequent matching events.
   - `publish_job(record)` / `publish_deleted(job_id, project_id, type_name)`
     fan out to all subscriber queues, applying each subscriber's filter.
   - Filtering helper that matches a record against optional `job_id`, `type`,
     `project_id`.
   - Unsubscribe removes the queue (used by Phase 2's SSE teardown). For Phase 1
     this is tested directly without HTTP.

4. `jobs/error_log.py` — per-`run_id` best-effort error log.
   - Dir: `{tempfile.gettempdir()}/kiln_jobs`. Path helper
     `error_log_path(run_id)`.
   - `append_error(run_id, entry: dict)` — JSON-lines append; create dir lazily;
     swallow all exceptions.
   - `read_errors(run_id) -> list[dict]` — read JSON-lines, skip unparsable
     lines; missing/unreadable file -> `[]`. Never raises.
   - `delete_errors(run_id)` — best-effort unlink; swallow exceptions.

5. `jobs/registry.py` — `JobRegistry`.
   - `__init__(max_concurrent: int | None = None)`: semaphore sized from arg or
     env `KILN_JOBS_MAX_CONCURRENT` (default 10); in-memory
     `dict[str, JobRecord]`; `dict[str, JobWorker]` type map;
     `dict[str, asyncio.Task]` supervising tasks; FIFO `pending` queue of job
     ids; a `JobEventBus`.
   - `register_type(worker_cls)`: instantiate and index by `type_name`.
   - `_new_job_id()`: `j_` + 12 lowercase base32 chars (from `secrets`/`uuid4`
     bytes, mapped to `abcdefghijklmnopqrstuvwxyz234567`).
   - `create(type_name, params, project_id=None, metadata=None) -> JobRecord`:
     validate params against `params_model`, build a `pending` record stamped
     with `supports_pause`, enqueue, emit a `job` event, then try to start
     pending jobs (respecting the semaphore). Returns the record.
   - `_try_start_pending()`: while semaphore slots available and FIFO queue
     non-empty, pop next still-`pending` job and launch its supervising task.
   - `_launch(job)`: mint `run_id`, set `running` + `started_at`, reconcile via
     `compute_state` (if `is_complete` -> straight to `succeeded`), emit, then
     create the supervising `asyncio.Task` running `_supervise`.
   - `_supervise(job_id, params)`: acquire semaphore inside the task; build a
     `JobContext`; call `worker.run`; on normal return set `succeeded` + store
     result summary; on `CancelledError` honor the pending intent (pause ->
     `paused` after `compute_state` reconcile, else `cancelled`); on other
     exception set `failed`, append the exception to the error log, store a
     `JobError`. Always release the slot and kick `_try_start_pending`.
   - Progress callback: `report_progress` updates the record's `JobProgress`
     and emits a `job` event (coalescing is a Phase-2 SSE concern; Phase 1 emits
     per call). `report_error` callback writes to the error log via
     `error_log.append_error(run_id, {...})`.
   - `pause(job_id)`: only valid for `running` + `supports_pause`; flag intent
     `paused`, cancel the task. (Not-running or not-pausable raises a clear
     error -> Phase 2 maps to 409.)
   - `resume(job_id)`: only valid for `paused`; reconcile via `compute_state`
     (if `is_complete` -> `succeeded`), else set back to `pending`/enqueue and
     `_try_start_pending` (fresh `run()` / fresh `run_id`).
   - `cancel(job_id)`: `pending` -> `cancelled` immediately (dequeue);
     `running`/`paused` -> flag intent `cancelled`, cancel task; terminal ->
     raise.
   - `delete(job_id)`: terminal only (else raise); drop record, best-effort
     delete error-log file for its `run_id`, emit a `deleted` event.
   - `get(job_id) -> JobRecord | None`: reconcile via `compute_state` and emit
     `job` if changed, then return the record.
   - `list(status=None, type=None, project_id=None, since=None, limit=None)`:
     filter + sort `created_at desc`.
   - `_reconcile(job, derived)`: when `derived` is not `None`, update progress
     counts/total/message and, if `is_complete` on a non-terminal job, mark
     `succeeded`. Returns whether anything changed.
   - Reconciliation correctly keeps the believed snapshot when `compute_state`
     returns `None` (the Noop case).
   - Provide a module-level `job_registry` singleton plus the class so tests can
     instantiate fresh isolated registries.

6. `jobs/workers/__init__.py` — package marker.

7. `jobs/workers/noop.py` — `NoopJobParams`, `NoopJobResult`, `NoopJobWorker`
   exactly per functional_spec §7 (`steps`, `sleep_per_step_seconds`,
   `fail_at_step`, `error_at_steps`; `compute_state` -> `None`; `run` reports
   success/error counts and calls `report_error` for `error_at_steps`).

## Tests

Tests live in `app/desktop/studio_server/jobs/` as `test_*.py`, async style
(`@pytest.mark.asyncio`), using fresh `JobRegistry` instances and a short
`sleep_per_step_seconds` for speed. Helper to poll until a job reaches a target
status with a timeout.

- `test_error_log.py`
  - append + read round-trips a list of entries; entries preserve `**extra`.
  - missing file -> `[]`; unreadable/garbage lines skipped -> partial list.
  - delete removes the file; delete of missing file is a no-op.
- `test_events.py`
  - subscribe yields an initial `snapshot` containing current jobs.
  - a subsequent `publish_job` is delivered as a `job` event.
  - `publish_deleted` delivers a `deleted` tombstone with the id.
  - filtering by `project_id` / `type` / `job_id` excludes non-matching events
    and scopes the snapshot.
- `test_registry.py`
  - full lifecycle: create -> running -> succeeded; `result.completed_steps`
    equals `steps`; `started_at`/`ended_at` populated.
  - failure path: `fail_at_step` -> `failed`; `error` summary set; the fatal
    exception is captured in the error log for the run.
  - cancel from pending (job never started) -> `cancelled`, no task.
  - cancel from running -> `cancelled`.
  - pause running -> `paused`; resume -> running -> succeeded; a fresh `run_id`
    is minted on resume (differs from the first run).
  - pause rejected when `supports_pause = False` (use a tiny non-pausable test
    worker) and when not running.
  - delete on terminal succeeds and emits `deleted`; delete while running/pending
    raises.
  - error-log capture: `error_at_steps` entries are readable via the run's
    `run_id` and the progress `error` count matches; missing file -> `[]`.
  - `compute_state` returning `None` keeps the believed snapshot (Noop never
    flips to complete early; progress comes from `report_progress`).
  - `compute_state` returning `is_complete=True` (test worker) reconciles a job
    to `succeeded` without running real work.
  - semaphore caps concurrency: with `max_concurrent=2` and 4 long jobs, exactly
    2 run while the other 2 stay `pending` (FIFO); as the first finish, pending
    ones start.
  - registry emits bus events: subscribing then creating/finishing a job yields
    `snapshot` + `job` events; deleting yields `deleted`.
