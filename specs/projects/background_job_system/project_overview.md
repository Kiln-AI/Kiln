---
status: complete
---

# Background Job System

A generic background-job layer for the local Kiln app (FastAPI on `:8757`). Provides tracked, controllable jobs that run as asyncio tasks in-process; exposes lifecycle (list / get / pause / resume / cancel / delete) and progress (SSE) over HTTP.

Job records are **in-memory only** — they are ephemeral bookkeeping for visibility and control, never a source of truth. The authoritative state of any operation lives in the Kiln project entities it touches (eval runs, task runs, etc.). Every worker must be **idempotent**: it derives "what's already done" by reading those entities, so a re-run converges to the same end state without duplicating side effects. Because of this, nothing is persisted and there is nothing to recover at startup — re-triggering a job after a crash or restart is always safe.

A standalone, general-purpose layer. It is intentionally generic (typed workers, opaque params/result, free-form `metadata`) so other features can build on it later, but this spec designs no integration with any specific consumer — future consumers adapt to this system, not the reverse.

## Goal & scope

**In scope.**
- A generic `Job` shape: base record + per-type opaque payloads (params / result).
- A `JobRegistry` that supervises asyncio tasks, tracks state in-memory, and emits events.
- REST API for `create / list / get / result / errors / pause / resume / cancel / delete`.
- SSE stream for live state and progress — success/error counts, idempotent snapshots, not deltas.
- An idempotency contract on workers: each derives its true state from source-of-truth reads on Kiln entities, so re-runs (including pause→resume) converge without duplicating side effects.
- Per-run error-message capture: errors spool to an ephemeral, best-effort JSON file in the OS temp dir, keyed by a per-run UUID, retrievable on demand and gracefully empty if gone.
- A reference `NoopJob` worker for end-to-end validation.
- An `EvalJob` worker that wraps the existing `EvalRunner` (which internally uses `AsyncJobRunner`). No changes to `EvalRunner` or `AsyncJobRunner`.

**Out of scope (deferred).**
- Any assistant / orchestration layer that consumes this system — separate, future work, not designed for here.
- Cloud Run remoting / surviving the desktop-app process.
- Full per-job log capture / streaming / replay (beyond the per-run error-message capture above).
- Job dependencies / DAGs.
- Plan-style multi-job approval.

## Positioning vs. `AsyncJobRunner`

`AsyncJobRunner` (`Kiln/libs/core/kiln_ai/utils/async_job_runner.py`) is a low-level worker pool that parallelizes "do N similar things" inside a single domain operation. It is in-memory, has no lifecycle beyond `.run()` returning, and is consumed by `EvalRunner`, `ExtractorRunner`, RAG runners, etc.

This new layer sits **above** `AsyncJobRunner`. It does not replace it. The composition is:

```
JobRegistry              (new — tracked lifecycle, in-memory, HTTP, SSE)
  └─ EvalJobWorker       (new — one tracked job per eval invocation)
       └─ EvalRunner     (existing — unchanged)
            └─ AsyncJobRunner   (existing — unchanged)
                 └─ N parallel eval calls
```

Existing adapters keep using `AsyncJobRunner` internally. What changes for evals is the *HTTP entry point and tracking*: a new `POST /api/jobs/eval` returns a job_id and runs in the background, alongside the existing blocking SSE `GET /api/.../run_comparison` which stays for the legacy browser flow.

A defining difference: the legacy blocking endpoint runs the eval *inside the HTTP request*, so closing the browser cancels it. A job in the new system runs independently of any connection — the user can close the web UI entirely and the job keeps running; the SSE stream only *observes* it (see functional spec §6).
