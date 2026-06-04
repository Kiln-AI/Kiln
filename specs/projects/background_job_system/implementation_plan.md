---
status: complete
---

# Implementation Plan: Background Job System

Derived from the "Quick start" section of the original spec, lightly re-split so each phase is one CR-sized chunk.

## Phases

- [x] Phase 1: Core layer + NoopJob (no HTTP yet) — `models.py` (incl. `JobDerivedState`, `JobProgress` with success/error counts), `registry.py` (in-memory index, semaphore, supervising tasks, lifecycle, per-run `run_id`, `compute_state` reconciliation at transitions/status reads), `events.py`, `error_log.py` (append/read/delete by `run_id` in the OS temp dir, all best-effort), `workers/noop.py`. No persistence layer for state. Verify the full lifecycle (`create / pause / resume / cancel / delete`) via Python tests against `NoopJobWorker`, including pause = task-cancel → `paused`, resume = fresh `run()`, reconciliation when `compute_state` returns `None`, and error-log capture (`error_at_steps` non-fatal + `fail_at_step` fatal), including graceful `[]` when the file is missing.
- [x] Phase 2: REST API + SSE — `api.py` (FastAPI router, incl. `GET /api/jobs/{id}/errors`), wired into the local server alongside existing routes. Idempotent-snapshot events (`snapshot` / `job` / `deleted`). Reuse `CancellableStreamingResponse` from `eval_api.py`, but scope its cancellation to the subscription generator only. Verify via curl + the SSE stream against `NoopJob` — **including the decoupling test: start a long `NoopJob`, connect then disconnect the SSE stream, and confirm the job keeps running to completion (only explicit cancel/pause stops it).**
- [x] Phase 3: `EvalJobWorker` — wraps existing `EvalRunner` unchanged, plus `compute_state` that counts `EvalRun`s with matching `task_run_config_id` (idempotency confirmed → `supports_pause = True`; see architecture open item #1). Wire `report_error` to per-item failures if `EvalRunner` surfaces them (open item #10; otherwise the `/errors` endpoint stays empty for evals in v1). `POST /api/jobs/eval` returns a job_id and runs in the background, alongside the legacy blocking eval-run SSE endpoint. Confirm progress (success/error counts) flows correctly.
- [ ] Phase 4: Frontend — `jobs_store.ts` (subscribes to `/api/jobs/events`, upserts by id), `api.ts`, jobs panel at `/jobs`, sidebar badge component.
