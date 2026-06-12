---
status: complete
---

# Functional Spec: Background Job System

This doc captures the externally observable behavior of the job system: the job record shape, the worker contract, the state machine, the REST API, and the SSE stream. Internal mechanics (concurrency primitives, code layout) live in `architecture.md`.

**Core principle.** A job record is ephemeral, in-memory bookkeeping — for visibility and control only. It is **never** a source of truth and is never persisted to disk. The authoritative state of whatever the job is doing lives in the Kiln project entities it reads/writes (eval runs, task runs, etc.). Workers must be idempotent (see §2).

The believed status/progress in the record is **recomputed from source of truth**, not accumulated from deltas. Each worker exposes a `compute_state(params)` method (§2) that reads the relevant Kiln entities and returns the operation's true progress and whether it's complete. The registry calls it at every lifecycle transition (start, pause, resume) and on status reads, then reconciles the in-memory snapshot against the result and emits an updated event if anything changed. Live `report_progress` calls during a run are just a smoothing layer on top for the UI between recomputations — they never override the derived truth. A snapshot may still briefly lag the true state, and the worker remains responsible for its own consistency.

## 1. Job record (base shape)

Lives in the registry's in-memory index; serialized to JSON only for HTTP/SSE responses (not to disk).

```jsonc
{
  "id": "j_a1b2c3d4e5f6",
  "type": "eval",
  "status": "running",
  "run_id": "8f3c1e0a-...-uuid",   /* UUID of the current/most-recent run() invocation */
  "progress": {
    "total":   50,
    "success": 11,                 /* items completed without error */
    "error":   1,                  /* items that errored (count only; messages in the error log) */
    "message": "scoring item 12",
    "updated_at": "2026-05-28T12:34:56Z"
  },
  "params":   { /* type-specific opaque JSON, validated against the type's params_model */ },
  "result":   null,                /* small summary populated on success; detail lives in Kiln entities */
  "error":    null,                /* populated on failure; short string + optional structured detail */
  "metadata": {},                  /* free-form pass-through from caller; this layer never interprets it */
  "project_id":      "p_abc",
  "supports_pause":  true,         /* stamped at creation from the worker class */
  "created_at":      "2026-05-28T12:30:00Z",
  "updated_at":      "2026-05-28T12:34:56Z",
  "started_at":      "2026-05-28T12:30:01Z",
  "ended_at":        null
}
```

- `type` is the discriminator. Each registered type declares typed `params_model` and `result_model` (pydantic). The base record stores them as plain JSON.
- `progress` reports counts, not a single cursor: `total`, `success` (completed without error), `error` (errored count), and a free-text `message`. Processed = `success + error`; remaining = `total − success − error`. The `error` field is just a count — the actual error *messages* live in the per-run error log (see §1.1 below).
- `run_id` is a fresh UUID assigned on each `run()` invocation (first run and every resume/re-trigger). It keys the per-run error log so messages from different runs of the same job don't collide. `null` before the first run.
- `metadata` is a free-form pass-through: callers may attach arbitrary attribution (any JSON object). This layer never reads, writes, or interprets it — it just stores and returns it verbatim.
- `result` is a **small summary** (counts, status, references to the Kiln entities that hold the detail). It is not a place to stash large blobs — the real output already lives in the project entities the worker wrote. There is no sibling result file and no size threshold.
- No `schema_version`, no checkpoint file, no persisted *state* of any kind — records exist only while the process is alive. (The error log in §1.1 is diagnostic spillover, not state.)

### 1.1 Per-run error log

Error *counts* live in `progress`; error *messages* would bloat the in-memory record if kept forever, so they spill to an ephemeral file instead — never to a Kiln entity (they aren't source of truth).

- **Location.** A file in the OS temp dir, keyed by `run_id` — e.g. `{tempdir}/kiln_jobs/{run_id}.json` (`tempdir` = `tempfile.gettempdir()`, so `/tmp/kiln_jobs/…` on macOS/Linux; portable to Windows). Temp storage is deliberately non-authoritative: the OS may clear it, and that's fine.
- **Shape.** An array of objects, each at minimum `{ "error_message": "..." }`. Objects (not bare strings) so we can add fields later (`item_id`, `timestamp`, `traceback_ref`, …) without a format break.
- **Writing.** Workers append via `ctx.report_error(...)` (§2) for non-fatal per-item errors; the registry also appends the final exception when a `run()` raises. Append-only, so it survives a crash mid-run.
- **Reading.** `GET /api/jobs/{id}/errors` (§5) returns the array for the job's current `run_id`. **If the file is gone, return `[]` with `200` — never an error.** This keeps the feature best-effort: logs are a debugging convenience, not a guarantee.

## 2. Worker contract

A worker is two methods: `compute_state()` — a pure read that derives true state from source of truth — and `run()` — the idempotent do-the-work method. There is no `resume()` and no checkpoint: pause is task cancellation, and resume is just a fresh `run()` (see §4) that re-orients itself via `compute_state()`.

```python
class JobDerivedState(BaseModel):
    """A worker's view of the operation's true state, read from source-of-truth entities."""
    total: int | None = None
    success: int = 0          # completed without error
    error: int = 0            # errored count
    is_complete: bool = False
    message: str | None = None


class JobContext:
    """Provided to the worker by JobRegistry during run()."""
    job_id: str

    async def report_progress(
        self,
        success: int,
        error: int = 0,
        total: int | None = None,
        message: str | None = None,
    ) -> None:
        """Update the registry's in-memory progress snapshot and emit an SSE event.
        Cheap to call often; a UI-smoothing signal only — the authoritative progress
        comes from compute_state(). The registry may coalesce rapid calls before emitting."""

    async def report_error(self, error_message: str, **extra) -> None:
        """Append one structured error entry — {"error_message": ..., **extra} — to this
        run's error log (a JSON file in the OS temp dir, keyed by run_id; see §1.1).
        For non-fatal per-item errors that don't stop the run. Best-effort: a failed
        write is swallowed, never propagated to the worker. Does not itself bump the
        progress `error` count — report that via report_progress."""

    # Cancellation is just asyncio.CancelledError on the supervising task —
    # workers may catch it for cleanup, but the transition is unconditional. A worker
    # must leave any in-flight atomic unit of work consistent before returning.


class JobWorker(Generic[TParams, TResult]):
    type_name: ClassVar[str]                  # discriminator value
    params_model: ClassVar[type[BaseModel]]   # pydantic model for params
    result_model: ClassVar[type[BaseModel]]   # pydantic model for result
    supports_pause: ClassVar[bool] = False    # worker is idempotent & safe to cancel-and-re-run

    async def compute_state(self, params: TParams) -> JobDerivedState | None:
        """Read source-of-truth Kiln entities and return the operation's true progress
        and whether it's already complete. MUST be a pure read — no side effects,
        idempotent, safe to call any time (before start, while paused, on a status read).
        This is the authority; the in-memory snapshot is reconciled against it.

        Return None only when the worker has no backing entity to consult (e.g. the
        NoopJob fixture); the registry then keeps the last believed snapshot. Real
        workers must override this."""
        return None

    async def run(self, params: TParams, ctx: JobContext) -> TResult:
        """MUST be idempotent. Should call compute_state() to learn what's already done,
        then perform only the remaining work, reporting progress as it goes. This single
        method covers both first run and resume — the registry calls run() again to resume
        a paused job; the worker re-orients via compute_state(), not a handed-in checkpoint."""
```

**The idempotency contract is the load-bearing invariant of this system.** Because nothing is persisted and resume is just a re-run, every worker author must guarantee that calling `run()` twice (or after an interruption) does not double-write, duplicate rows, or otherwise corrupt the project. `compute_state()` is how a worker stays honest: it derives status from the project rather than trusting in-memory deltas, so the system self-corrects after interruptions, restarts, or concurrent edits. `supports_pause` advertises that a worker meets this bar *and* is safe to cancel mid-flight and re-run; default `False` is conservative.

## 3. State machine

```
                    ┌─────────────┐
                    │   pending   │
                    └─────┬───────┘
                          ▼
                    ┌─────────────┐
   ┌───────────────►│   running   │
   │ resume         └──┬───┬───┬──┘
   │ (re-run)          │   │   │
   │                   ▼   ▼   ▼
┌──┴───────┐      terminal states
│  paused  │   ┌──────────┬─────────┬──────────┐
└────▲─────┘   │succeeded │ failed  │cancelled │
     │         └──────────┴─────────┴──────────┘
     │  pause
     └─ (cancel task,
        keep resumable)
```

There is no `interrupted` state. Records are in-memory only, so a process restart simply drops every record — there are no orphans to recover and nothing to flip.

Transitions:

| From → To | Trigger |
|---|---|
| `pending → running` | semaphore slot frees, worker task started |
| `pending → cancelled` | cancel before run started |
| `running → succeeded` | worker returns normally |
| `running → failed` | worker raises (other than `CancelledError`) |
| `running → cancelled` | `cancel` issued; `asyncio.Task.cancel()`, `CancelledError` reaches worker |
| `running → paused` | `pause` issued; same task cancellation, but marked resumable |
| `paused → running` | `resume` called; a fresh `run()` task is started |
| `paused → cancelled` | cancel from paused state |
| `succeeded / failed / cancelled → (deleted)` | explicit DELETE |

`pending → paused` is not allowed (pausing a not-yet-started job = cancel + recreate). `pause` and `cancel` both cancel the supervising task; they differ only in the resulting state and whether resume is permitted.

## 4. Pause / resume semantics

Non-cooperative and checkpoint-free. Pause is task cancellation; resume is a fresh `run()`. The worker's idempotency is what makes this safe — on resume it reads source-of-truth Kiln entities and continues from wherever the project state left off.

**Pause flow.**
1. Client calls `POST /api/jobs/{id}/pause`. Registry returns `202`.
2. Registry calls `asyncio.Task.cancel()` on the supervising task. The worker receives `CancelledError` at its next `await`; it should finish or unwind its current atomic unit so the project is left consistent.
3. Once the task has settled, the registry calls `compute_state(params)` to record the true progress as of the pause (rather than the last reported delta), transitions `running → paused`, and emits an event. (Distinguished from `cancel` only by the target state.)

**Resume flow.**
1. Client calls `POST /api/jobs/{id}/resume`. Registry returns `202`.
2. Registry calls `compute_state(params)` to re-seed the progress snapshot. If it reports `is_complete`, the job goes straight to `succeeded` without re-running. Otherwise the registry schedules a new task.
3. The registry calls `run(params, ctx)` again — there is no separate `resume()` method and no checkpoint is handed in.
4. The worker calls `compute_state()` itself to determine what is already done and continues. A re-run must not duplicate completed work (idempotency contract, §2).

Workers that don't support pause: `supports_pause = False`. Pause endpoint returns `409 Conflict`. Cancel still works (it's terminal and doesn't require re-runnability).

## 5. REST API

All endpoints live under `/api/jobs`. Authentication piggybacks on whatever the local server uses today (don't introduce a new scheme).

| Method | Path | Body | Response | Notes |
|---|---|---|---|---|
| `POST` | `/api/jobs/{type}` | `{ params: <type-specific> }` | `201 { job_id, status }` | `type` must be registered. `params` validated against `params_model`. Job starts as `pending`, runs as soon as semaphore allows. |
| `GET` | `/api/jobs` | — | `200 [ <record>, ... ]` | Filters: `?status=`, `?type=`, `?project_id=`, `?since=<iso8601>`, `?limit=`. Default sort: `created_at desc`. |
| `GET` | `/api/jobs/{id}` | — | `200 <record>` | 404 if unknown. Recomputes status via the worker's `compute_state` (source of truth), reconciles the in-memory snapshot, and emits a `job` event if it changed before returning. |
| `GET` | `/api/jobs/{id}/result` | — | `200 <result summary>` | 404 if not terminal or no result. Returns the small in-memory summary; detail lives in the Kiln entities the job wrote. |
| `GET` | `/api/jobs/{id}/errors` | — | `200 [ { "error_message": "...", ... }, ... ]` | Error log for the job's current `run_id` (§1.1). Optional `?run_id=<uuid>` for a specific past run. **Always `200`; returns `[]` if the file is missing/unreadable** — never errors. |
| `POST` | `/api/jobs/{id}/pause` | — | `202` / `409` | 409 if not running, or worker doesn't support pause. |
| `POST` | `/api/jobs/{id}/resume` | — | `202` / `409` | 409 if not paused. |
| `POST` | `/api/jobs/{id}/cancel` | — | `202` / `409` | 409 if already terminal. Idempotent for `pending`. |
| `DELETE` | `/api/jobs/{id}` | — | `204` / `409` | 409 if still in-flight. Drops the in-memory record and best-effort removes the run's error log file(s). |
| `GET` | `/api/jobs/events` | — | `200 text/event-stream` | SSE; see §6. |

All state-changing endpoints (pause/resume/cancel) return `202 Accepted` once the transition has settled. For pause and cancel this means the handler awaits the supervising task's cancellation/cleanup before responding, so the slot is reclaimed and the terminal result is recorded deterministically (no lost cancellation, no double-release). For our current workers cleanup lands at the next `await`, so this is effectively instant; a future worker with slow cancel-cleanup would hold the connection for that cleanup. The resulting state is also published via the SSE stream for any observers.

Error envelopes follow the existing local-server convention (`{ "detail": "..." }`).

## 6. SSE stream

`GET /api/jobs/events?job_id=&type=&project_id=` — all filters optional, combinable.

**The stream is a pure observer — jobs run independently of it.** This is the critical difference from today's eval flow. The existing blocking `run_comparison` SSE endpoint runs the eval *inside the request*, so `CancellableStreamingResponse` cancelling on client disconnect also cancels the eval. Here, the job is a supervising task owned by the registry; the SSE endpoint only subscribes to the event bus and forwards snapshots. A client disconnecting (closing the tab, even quitting the whole web UI) must tear down **only** the subscription — never the job. Jobs keep running, and a later reconnect resyncs via the `snapshot` event. The *only* things that stop a job are explicit `POST /api/jobs/{id}/cancel` or `/pause`.

Implementation: reuse the `CancellableStreamingResponse` pattern from `Kiln/app/desktop/studio_server/eval_api.py`, but scope its cancellation to the **subscription generator** (unsubscribe from the bus, stop the keepalive) — do not let it reach into any job task. Don't create the supervising task inside the request handler; it lives in the registry, created at `create`/`resume`, with a lifetime decoupled from any HTTP connection.

Events are **idempotent snapshots, not deltas.** Every per-job event carries the full current record; the client keeps a map keyed by `id` and upserts. There is no `from`/`to` transition payload to apply in order — a client that drops or reorders events still converges as long as it processes the latest snapshot per id. A snapshot reflects the registry's *believed* state at emit time and may briefly lag the worker's true state (e.g. under concurrent edits); the worker owns its own consistency.

Event types:

```
event: snapshot
data: { "jobs": [ <record>, ... ] }
```
Sent once on connect with the full current set of jobs matching the filter. Lets the UI sync without a parallel GET.

```
event: job
data: <record>
```
Emitted on every change to a single job — creation, status transition, and progress update all use this one event, each carrying the complete record (including the latest `status` and `progress` with its `success`/`error` counts). The registry may coalesce rapid progress updates before emitting so a 500-item eval doesn't flood subscribers. Error *messages* are not streamed — the snapshot carries only the `error` count; clients fetch messages on demand via `GET /api/jobs/{id}/errors`.

```
event: deleted
data: { "id": "j_..." }
```
A tombstone — the only non-snapshot event, since a deleted record has no state to send.

One stream serves the sidebar badge, jobs panel, and any future in-chat widget. Clients reconnect on disconnect; the fresh `snapshot` event resyncs them. No need for `Last-Event-ID` replay in v1 — snapshots are self-healing.

Why SSE over Socket.IO: matches every other streaming endpoint in the codebase (chat, eval, calibration); no new dependency; no client-to-server streaming need.

## 7. Worker implementations

### Reference: `NoopJob` (validation / smoke test)

```python
class NoopJobParams(BaseModel):
    steps: int = 10
    sleep_per_step_seconds: float = 0.5
    fail_at_step: int | None = None         # fatal: raises (tests the failed path)
    error_at_steps: list[int] = []          # non-fatal: logs an error, keeps going

class NoopJobResult(BaseModel):
    completed_steps: int

class NoopJobWorker(JobWorker[NoopJobParams, NoopJobResult]):
    type_name = "noop"
    params_model = NoopJobParams
    result_model = NoopJobResult
    supports_pause = True

    async def compute_state(self, params):
        return None  # no backing entity — registry keeps the believed snapshot

    async def run(self, params, ctx):
        success = error = 0
        for i in range(params.steps):
            await asyncio.sleep(params.sleep_per_step_seconds)
            if params.fail_at_step == i:
                raise RuntimeError(f"intentional fail at step {i}")
            if i in params.error_at_steps:
                error += 1
                await ctx.report_error(f"intentional error at step {i}", step=i)
            else:
                success += 1
            await ctx.report_progress(
                success=success,
                error=error,
                total=params.steps,
                message=f"step {i+1}/{params.steps}",
            )
        return NoopJobResult(completed_steps=success + error)
```

`NoopJob` is the canary: end-to-end-tests pause / resume / cancel / error-log capture without needing real LLM calls or `EvalRunner`. `error_at_steps` exercises the non-fatal `report_error` path (errors accumulate in the log and the `error` count without stopping the run); `fail_at_step` exercises the fatal path. It has **no** backing Kiln entity, so `compute_state` returns `None` and its `run()` simply restarts from step 0 on resume. That's an honest limitation of a source-of-truth-free fixture and is fine: the canary's purpose is to exercise lifecycle transitions and the error log, not work-skipping. Real workers derive their state instead of restarting.

### `EvalJob` (first real consumer)

```python
class EvalJobParams(BaseModel):
    project_id: str
    task_id: str
    eval_id: str
    eval_config_id: str
    run_config_id: str

class EvalJobResult(BaseModel):
    total: int
    success: int
    error: int
    # just a summary — per-row results live in the eval run entity (source of truth)

class EvalJobWorker(JobWorker[EvalJobParams, EvalJobResult]):
    type_name = "eval"
    params_model = EvalJobParams
    result_model = EvalJobResult
    supports_pause = True   # EvalRunner is confirmed idempotent: collect_tasks excludes
                            # already-run (eval_config, run_config, dataset_id) triples,
                            # so pause (cancel) + resume (re-run) skips completed items
                            # and writes no duplicates. See architecture.md open item #1.

    async def compute_state(self, params):
        # Source of truth: EvalRun entities, intersected with the eval-set filter so we
        # count exactly the candidate set EvalRunner.collect_tasks would (open item #1).
        in_filter_ids = dataset_ids_passing_eval_filter(params)          # task runs in the eval set
        scored_ids    = scored_dataset_ids(params, params.run_config_id) # existing EvalRuns
        success = len(scored_ids & in_filter_ids)
        total   = len(in_filter_ids)
        # Runtime errors aren't persisted as entities (a failed item simply isn't saved),
        # so derived error is 0; the live error count comes from Progress.errors during run().
        return JobDerivedState(total=total, success=success, error=0,
                               is_complete=(success >= total))

    async def run(self, params, ctx):
        # EvalRunner.collect_tasks excludes already-scored items, so Progress counts only the
        # REMAINING work (Progress.total = full − already_done, Progress.complete starts at 0).
        # Add the already-done baseline so progress/result are on the full-set scale.
        baseline = (await self.compute_state(params)).success
        eval_runner = build_eval_runner(params)  # same construction as eval_api.py uses today
        progress = None
        async for progress in eval_runner.run():
            await ctx.report_progress(
                success=baseline + progress.complete,
                error=progress.errors,
                total=baseline + progress.total,   # baseline + remaining = full eval-set size
            )
        return EvalJobResult(
            total=baseline + (progress.total if progress else 0),
            success=baseline + (progress.complete if progress else 0),
            error=(progress.errors if progress else 0),
        )
```

`EvalRunner` is unchanged. Internally it still uses `AsyncJobRunner` for per-item parallelism. The translation is `Progress → JobContext.report_progress()` for counts. Capturing individual eval error *messages* via `report_error` depends on whether `EvalRunner` surfaces per-item failures (see open item #1); if it only exposes an error count, the messages endpoint stays empty for evals until that's wired up.

The idempotency contract bears directly on this worker: a paused-then-resumed (or re-triggered) eval re-invokes `run()`, which re-invokes `EvalRunner.run()`. This is confirmed safe — `EvalRunner.collect_tasks` excludes already-run `(eval_config, run_config, dataset_id)` triples, so completed items are skipped and no duplicate `EvalRun` entities are written (architecture.md open item #1). Hence `supports_pause = True`.

## 8. What's NOT in this spec

- Full per-job log capture / streaming. Error *messages* are collected per run (§1.1) and fetched via `GET /api/jobs/{id}/errors`, but general stdout/stderr/log streaming is out — workers still use the standard logger for that.
- Job dependencies / DAGs. One job, one task.
- Retries at the job level. `AsyncJobRunner` already retries individual sub-tasks for workers that use it; whole-job retry is the caller's problem (or a future feature).
- Cross-project listings. Records carry `project_id`; the SSE/list endpoints can filter by it, but there's no global "all jobs everywhere" view.
- Multi-machine / remote execution. All jobs are local asyncio tasks. Cloud Run is GEPA's path and isn't generalized here.
- Pre-run approval / authorization gates. The endpoints follow whatever auth the local server has; no new approval scheme.
