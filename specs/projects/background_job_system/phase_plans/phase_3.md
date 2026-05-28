---
status: draft
---

# Phase 3: EvalJobWorker (first real consumer)

## Overview

Add the first real background worker, `EvalJobWorker`, that wraps the existing
`EvalRunner` unchanged and plugs it into the Phase 1/2 job system. The worker:

- Derives true progress from source-of-truth `EvalRun` entities via
  `compute_state` (a pure read), so resume/re-trigger reconciles honestly.
- Runs the eval in the background by streaming `EvalRunner.run()`'s `Progress`
  yields into `ctx.report_progress`, returning a small `EvalJobResult` summary.
- Advertises `supports_pause = True` because `EvalRunner.collect_tasks_for_task_run_eval`
  excludes already-run `(eval_config, run_config, dataset)` triples — cancel +
  re-run skips completed items and writes no duplicate `EvalRun`s (architecture
  open item #1, CONFIRMED).

No new endpoint is needed: the generic `POST /api/jobs/{type}` from Phase 2
dispatches to it once `EvalJobWorker` is registered alongside `NoopJobWorker`.

## Key design decisions (verified against current code)

- **`save_context = None` (KNOWN OPEN ITEM — not equivalent to the request path
  for git-sync-enabled projects).** `build_save_context(request)` reads
  `request.state.git_sync_manager` and returns `None` only when git sync isn't
  active; when it IS active it returns a context that wraps each save in
  `manager.atomic_write(...)` (commit + push). A background worker has no request
  and passes `save_context=None`, so `EvalRunner` falls back to
  `default_save_context` (a no-op). This is identical to the request path ONLY
  for projects that do NOT have git sync in `auto` mode. For a git-sync-enabled
  project, background-eval `EvalRun` writes do NOT participate in request-scoped
  git-sync: they are written to disk but are NOT committed or pushed by the job,
  unlike the legacy SSE eval endpoint under `/api/projects/...` (which goes
  through `GitSyncMiddleware` + `build_save_context`). The uncommitted writes sit
  dirty in the working tree until the next write-locked request triggers
  `GitSyncManager.ensure_clean()`, whose crash-recovery path stashes dirty files
  (and hard-resets unpushed commits) — so the background-eval results can be
  swept out of the working tree into a stash with no UI to recover them, and are
  never backed up to the remote. We are keeping `save_context=None` for v1; this
  is a known open item pending a design decision (do not treat it as safe/
  equivalent for git-sync projects).
- **Entity loading.** Reuse `eval_config_from_id` / `task_run_config_from_id`
  from `eval_api.py`. They take only string IDs (resolve the project via
  `project_from_id` → `task_from_id`), need no `Request`, and raise
  `HTTPException(404)` on missing entities. In `run()` that surfaces as a normal
  exception → the registry marks the job `failed` (acceptable). `compute_state`
  loads the same way; a missing entity there propagates out of reconciliation
  (the registry only swallows `None`, not exceptions) so the failure is visible
  rather than silently treated as "no progress".
- **`compute_state` counts.** `total` = task runs matching
  `dataset_filter_from_id(eval.eval_set_filter_id)`. `success` = `EvalRun`
  children of the eval_config whose `task_run_config_id == run_config_id`.
  `error = 0` — failed items aren't persisted as entities; the live error count
  comes from `Progress.errors` during the run only. `is_complete = success >= total`.
- **Errors (open item #10).** `Progress` exposes only an error *count*, not
  per-item messages, so `report_progress(error=...)` carries the count and the
  `/errors` endpoint stays empty for evals in v1. No `report_error` wiring and
  no change to `EvalRunner`.

## Steps

1. Add `app/desktop/studio_server/jobs/workers/eval.py`:

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

   class EvalJobWorker(JobWorker[EvalJobParams, EvalJobResult]):
       type_name = "eval"
       params_model = EvalJobParams
       result_model = EvalJobResult
       supports_pause = True

       async def compute_state(self, params) -> JobDerivedState: ...
       async def run(self, params, ctx) -> EvalJobResult: ...
   ```

   - A private `_build_eval_runner(params) -> EvalRunner` helper that loads the
     eval_config + run_config and constructs
     `EvalRunner(eval_configs=[eval_config], run_configs=[run_config],
     eval_run_type="task_run_eval", save_context=None)` — mirroring
     `run_eval_config` in `eval_api.py`.
   - `compute_state` loads the eval_config (and its parent eval), counts
     filtered task runs for `total`, counts matching `EvalRun`s for `success`,
     returns `JobDerivedState(total, success, error=0, is_complete=success>=total)`.
   - `run` builds the runner, iterates `async for progress in eval_runner.run():`
     calling `await ctx.report_progress(success=progress.complete,
     error=progress.errors, total=progress.total)`, and returns
     `EvalJobResult(total, success, error)` from the last `progress`.
     `EvalRunner.run()` always yields at least an initial `Progress`, so a
     `last_progress` is guaranteed; default to a zero summary defensively.

2. Register the worker in `connect_jobs_api` (`api.py`) next to
   `NoopJobWorker`: `job_registry.register_type(EvalJobWorker)`.

3. Verify the OpenAPI schema is unchanged (no new route — the generic create
   route already exists) via `check_schema.sh`.

## Tests

`app/desktop/studio_server/jobs/workers/test_eval.py`, mirroring the entity
fixtures from `test_eval_api.py` / `test_eval_runner.py` (Project/Task/Eval/
EvalConfig/TaskRunConfig/TaskRun in `tmp_path`, pre-seeded `EvalRun`s), patching
`project_from_id` so the on-disk project resolves.

- `compute_state` with no `EvalRun`s: `total` = number of filtered task runs,
  `success = 0`, `error = 0`, `is_complete = False`.
- `compute_state` counts already-scored items: seed `EvalRun`s with matching
  `task_run_config_id`; `success` equals the seeded count; `is_complete` flips
  true only when `success >= total`.
- `compute_state` ignores `EvalRun`s with a different `task_run_config_id`
  (doesn't over-count).
- `run` maps `Progress` → `report_progress` and returns the right
  `EvalJobResult`: patch/stub `EvalRunner.run` to yield canned `Progress`
  objects, assert the recorded `report_progress` calls and the returned result.
- Idempotent re-run: seed some `EvalRun`s, run a real `EvalRunner` whose
  `run_job` is stubbed to write an `EvalRun` per remaining item, assert only the
  not-yet-scored items are processed and no duplicate `EvalRun`s are written.
- End-to-end via the registry: `registry.register_type(EvalJobWorker)`,
  `registry.create("eval", params)` with `EvalRunner.run` stubbed, drive to
  `succeeded`, assert the final `result` summary and progress counts.
