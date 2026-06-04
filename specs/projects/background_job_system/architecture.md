---
status: complete
---

# Architecture: Background Job System

Internal mechanics. The externally observable surface (record shape, REST API, SSE events, state machine, pause/resume semantics, worker contract) is in `functional_spec.md`. This doc covers state management, concurrency, the (non-)recovery story, code layout, and open items to verify during implementation.

## 1. JobRegistry

Singleton per process. Responsibilities:

- Type registration (`register_type(WorkerClass)`).
- In-memory index `{job_id → JobRecord}` — the only store. Starts empty on each process boot.
- Supervising asyncio task per running job (`asyncio.Task` tracked in a dict). Its lifetime is owned entirely by the registry and is **decoupled from any HTTP request or SSE connection** — created at `create`/`resume`, ended only by completion or an explicit `cancel`/`pause`. Closing the web UI or dropping the SSE stream has no effect on it.
- Global semaphore for max-concurrent `running` jobs (configurable; default 10).
- Pub/sub bus that feeds the SSE endpoint.
- Progress coalescing: rapid `report_progress` calls update the in-memory record freely but may be throttled before emitting an SSE `job` event (so a 500-item eval doesn't flood subscribers). Status transitions emit immediately.
- **Reconciliation:** at every lifecycle transition (start, pause, resume) and on status reads (`GET /api/jobs/{id}`), call the worker's `compute_state(params)`, reconcile the in-memory snapshot against the derived truth, and emit a `job` event if it changed. This is what keeps the believed state honest without persistence. If `compute_state` returns `None` (fixture with no source of truth), keep the believed snapshot.
- **Per-run identity & error log:** mint a fresh `run_id` (UUID) on each `run()` invocation and stamp it on the record. Route `ctx.report_error(...)` calls (and the final exception on a failed run) to an append-only JSON file keyed by that `run_id` in the OS temp dir. All file IO here is best-effort — a failed write or missing file never propagates.
- Lifecycle methods: `create`, `pause`, `resume`, `cancel`, `delete`.

## 2. State management (no persistence)

There is no disk persistence. The in-memory index is the registry's entire store, and it is never the source of truth — it is a best-effort view of operations whose authoritative state lives in the Kiln project entities they touch (eval runs, task runs, etc.).

```
source of truth   →  Kiln project entities (eval runs, task runs, ...)
                        │  worker.compute_state(params) reads these
                        ▼
registry view      →  in-memory {job_id → JobRecord}, reconciled against
                       compute_state at transitions / status reads; lost on restart
```

**Why no files.** Job records are transient visibility/control data. Persisting them would create a second, drifting copy of state that we'd then have to reconcile against the real entities. Instead we lean on the idempotency contract and `compute_state`: every worker can re-derive "what's done" from the project, so the registry never needs to remember anything across a restart — and the in-memory snapshot self-corrects whenever it's recomputed.

- **Project scope.** The record carries `project_id` purely for filtering (`GET /api/jobs?project_id=`, SSE filter). It does not dictate any storage location, because there is no storage.
- **Result.** The `result` field holds a small in-memory summary; the actual output already lives in the entities the worker wrote. No sibling result file, no size threshold.
- **Coalescing, not flushing.** Any debouncing applies only to SSE emission frequency — there are no disk writes to debounce.

**State vs. diagnostics — the one allowed file.** The "no persistence" rule is about *state*: status/progress must stay derivable, never copied to disk. Error *messages* are not state — they're diagnostic spillover with no representation in the Kiln entities. Keeping them in the long-lived registry forever would leak memory, so they spool to an ephemeral, per-`run_id` JSON file in the OS temp dir (`{tempfile.gettempdir()}/kiln_jobs/{run_id}.json`). This doesn't reintroduce a competing source of truth: the file is non-authoritative, the OS may delete it, and every reader treats "missing" as "empty." It's the single deliberate exception, scoped to bulky diagnostics that can't live in memory.

## 3. Concurrency

- One global asyncio semaphore caps `running` jobs (default 10, configurable via env var, e.g. `KILN_JOBS_MAX_CONCURRENT=10`).
- Excess jobs stay in `pending` until a slot frees. Order: FIFO by `created_at`.
- Per-type caps are not in v1 but the registry should keep the door open (`{type: semaphore}` map ready to grow).
- Cancellation = `asyncio.Task.cancel()` from outside; the registry transitions state in-memory and emits the SSE event. `pause` and `cancel` share the same cancellation mechanism, differing only in the resulting state.

## 4. Restart behavior (no recovery)

There is nothing to recover. On process restart the in-memory index starts empty, so every prior job record is simply gone — including any that were `running` or `paused`. There is no orphan scan, no `interrupted` state, no rehydration step.

This is safe precisely because of the idempotency contract: the operation's true state still lives in the Kiln entities. To "recover," the user just re-triggers the job; on start the registry calls `compute_state` to seed the real progress, and `run()` continues from where the project actually left off, without duplicating completed work.

If cross-restart *visibility* into past jobs is ever wanted, it should be reconstructed by querying the Kiln entities (e.g. "show me recent eval runs"), not by persisting job records — that keeps a single source of truth.

## 5. Code layout (suggested)

```
Kiln/app/desktop/studio_server/jobs/
  __init__.py
  registry.py       # JobRegistry singleton: in-memory index, semaphore, supervising tasks, lifecycle, reconciliation
  models.py         # JobRecord, JobProgress, JobDerivedState, JobStatus, JobContext, JobWorker base
  events.py         # in-process pub/sub bus
  error_log.py      # per-run error log: append / read / delete by run_id, in the OS temp dir
  api.py            # FastAPI router: create/list/get/result/errors/pause/resume/cancel/delete + SSE
  workers/
    __init__.py
    noop.py         # NoopJobWorker
    eval.py         # EvalJobWorker
```

No `persistence.py` — the registry is purely in-memory. `error_log.py` is the one module that touches disk, and only for ephemeral, best-effort diagnostic logs (§2), never for state.

Registration happens once at server startup (alongside the existing route registration), e.g.:

```python
job_registry.register_type(NoopJobWorker)
job_registry.register_type(EvalJobWorker)
```

Frontend (Svelte) — out of strict scope for this spec, but the natural shape:

```
Kiln/app/web_ui/src/lib/jobs/
  jobs_store.ts          # subscribes to /api/jobs/events
  api.ts                 # thin REST client
Kiln/app/web_ui/src/routes/(app)/jobs/+page.svelte    # jobs panel
Kiln/app/web_ui/src/lib/components/SidebarJobsBadge.svelte
```

## 6. Open items — verify during implementation

Sensible defaults are listed; flip them if the code disagrees.

1. **`EvalRunner` idempotency — CONFIRMED.** Verified against the code: `EvalRunner.collect_tasks_for_task_run_eval()` builds an `already_run` set from existing `EvalRun` children (keyed by `(eval_config_id, task_run_config_id, dataset_id)`) and excludes already-run triples (`libs/core/kiln_ai/adapters/eval/eval_runner.py` ~L147–173). So re-running skips completed items and never writes duplicate result entities. EvalJob is therefore idempotent → **`supports_pause = True`**. Pause is a hard task-cancel mid-run; resume re-invokes `run()` and EvalRunner re-collects only the unfinished items. This is the *same* cancellation the legacy `run_comparison` endpoint already performs on client disconnect, so it carries no new corruption risk. `compute_state` counts `EvalRun`s whose `task_run_config_id` matches, against the eval's dataset-filter size for `total`. (Runtime errors aren't persisted as entities — a failed item simply isn't saved — so derived `error` is 0; the live `error` count comes from `Progress.errors` during the run.)
2. **Multi-project scope — RESOLVED.** Nothing is persisted, so there's no startup scan. A single in-session registry tracks every job regardless of project; `project_id` is an optional filter on list/SSE. For eval jobs `project_id` comes from `EvalJobParams.project_id`; for noop it's `null`.
3. **Active-project hook — RESOLVED.** The local server has **no** server-side "active project" to default to (confirmed: `project_id` is always an explicit identifier; the active project is frontend UI state `$ui_state.current_project_id`). Don't invent one. `?project_id=` is a plain optional filter (omitted = all jobs); the frontend passes its current `$ui_state.current_project_id`.
4. **Auth — RESOLVED.** Studio-server routes use no FastAPI auth dependency; they mark agent-callability via `openapi_extra` policy constants (`ALLOW_AGENT`, etc.) as `eval_api.py` does. Mirror that convention; introduce no new scheme.
5. **Max-concurrent default.** Set to 10; expose as env var `KILN_JOBS_MAX_CONCURRENT`. Revisit if mixed job types (e.g. evals + future bandwidth-heavy syncs) starve each other; per-type caps then.
6. **Job ID format.** `j_{12-char-base32-lowercase}` (e.g. `j_a1b2c3d4e5f6`). Compact, grep-friendly, collision space is fine for local-only.
7. **Delete policy.** Allowed only on terminal status (`succeeded`, `failed`, `cancelled`). Paused jobs must be cancelled or resumed-then-terminal first. (No `interrupted` state exists.)
8. **`compute_state` read cost.** Reconciliation calls `compute_state` on every status read, which reads Kiln entities from disk. For a frequently-polled jobs panel this could get expensive. Default: recompute on lifecycle transitions and on explicit `GET /api/jobs/{id}`, but let the SSE stream ride on `report_progress` deltas between recomputations (don't recompute per progress tick). If polling proves hot, add a short TTL cache on the derived state. Confirm `compute_state` for `EvalJob` is cheap enough (a count query, not a full re-score).
9. **SSE keepalive / heartbeat.** Match whatever the existing chat / eval SSE endpoints do. If unclear, send a `: ping\n\n` comment every 15s to keep proxies happy.
10. **Error-message capture for `EvalJob`.** The error *count* is easy (`progress.errors`). Whether we can capture per-item error *messages* via `report_error` depends on whether `EvalRunner` surfaces individual failures (vs. just counting them). If it doesn't, the `/errors` endpoint stays empty for evals until `EvalRunner` exposes them — acceptable for v1; the `NoopJob` fixture still exercises the full error-log path. Tie-in with open item #1.
11. **Error-log file format & cleanup.** Default to append-friendly JSON Lines internally (`{tempdir}/kiln_jobs/{run_id}.json`, one error object per line), parsed into a JSON array on read. `DELETE /api/jobs/{id}` best-effort removes the current run's file; past-run files in `/tmp` are left to the OS to reap. Confirm the temp subdir is created lazily and writes never block the worker (consider a background writer if `report_error` volume is high).
12. **Git-sync for background eval jobs — RESOLVED via option C.** Tension surfaced during Phase 3: the legacy eval-run endpoint lives under `/api/projects/...`, where `GitSyncMiddleware` + `build_save_context(request)` wrap each `EvalRun` save in `manager.atomic_write` (git commit/push). Background jobs are deliberately request-decoupled (a core design goal) and write `EvalRun`s from a registry-owned task, so the original worker passed `save_context=None` and those writes were **not** committed/pushed (and could be stashed away by a later `ensure_clean`). **Resolution:** `app/desktop/git_sync/save_context.py` adds a request-free `save_context_for_project(project_id, context) -> SaveContext | None` (and `get_manager_for_project`) that mirrors the middleware's `_get_manager_for_request` resolution (config keyed by `project_path`, manager by `clone_path`, via the shared `GitSyncRegistry.get_or_create`), returning `None` for every "not auto-sync" branch. `EvalJobWorker._build_eval_runner` passes this through, so each `EvalRun` is committed/pushed per item — converging to the same behavior as the legacy SSE path (which already runs at concurrency 25 through the same non-reentrant per-project lock; contention, not deadlock). For non-auto-sync projects (the default) it stays a no-op, identical to before. The resolution logic is intentionally duplicated from the middleware (a clean delegating refactor would break the middleware's test patches); both copies carry a "keep in sync" note.
