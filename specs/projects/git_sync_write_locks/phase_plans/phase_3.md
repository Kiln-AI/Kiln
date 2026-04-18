---
status: complete
---

# Phase 3: SSE Endpoint Wiring

## Overview

Wire up the 5 SSE endpoints with `@no_write_lock` and a `save_context` built
from the per-request `GitSyncManager`, so they manage their own per-job
commit/push cycle instead of silently dropping writes.

Concretely:

1. Move the `write_lock` / `no_write_lock` decorators from
   `app/desktop/git_sync/decorators.py` to
   `libs/server/kiln_server/git_sync_decorators.py`. They have no dependencies
   on desktop-layer code, so `libs/server` endpoints can import them without
   creating a layering violation. Update all existing imports.
2. In the middleware read path, attach the resolved `GitSyncManager` to
   `request.state.git_sync_manager` so endpoints (which can't import
   `GitSyncManager` directly from `libs/server`) can reach it type-safely via
   the `AtomicWriteCapable` Protocol.
3. Add a `build_save_context` helper in `libs/server/kiln_server/` that reads
   `request.state.git_sync_manager` and returns a `SaveContext | None`. Typed
   via `AtomicWriteCapable` so a typo on `atomic_write` is caught by the type
   checker without taking an `app/desktop` dependency.
4. Add `request: Request` to the signatures of the 5 SSE endpoints, apply
   `@no_write_lock`, and pass `save_context = build_save_context(request)` to
   each runner (`ExtractorRunner`, `EvalRunner`, `build_rag_workflow_runner`).
5. Set `KILN_DEV_MODE = "true"` in `dev_server.py` so phase 4's dev-only safety
   nets have a flag to key off of.

No behavior change for callers that already hit these endpoints -- the runners
already accept `save_context` (phase 2), and the default is a no-op, so the
non-git-sync path is unchanged.

## Steps

1. **Create `libs/server/kiln_server/git_sync_decorators.py`** with the
   contents of the existing `app/desktop/git_sync/decorators.py` (just the two
   decorators, unchanged). Keep the same `F = TypeVar("F", bound=Callable)`
   binding.

2. **Delete `app/desktop/git_sync/decorators.py`** and update imports:
   - `app/desktop/git_sync/middleware.py` does not currently import the
     decorators -- it reads the attributes by name via `getattr`. No change
     required there, but confirm.
   - `app/desktop/git_sync/test_decorators.py`: update import to
     `from kiln_server.git_sync_decorators import no_write_lock, write_lock`.
   - `app/desktop/git_sync/test_middleware.py`: same import update.
   - `app/desktop/git_sync/integration_tests/test_decorators.py`: same import
     update.
   - `app/desktop/git_sync/integration_tests/test_no_write_lock_batch.py`: same
     import update.

3. **Attach manager to `request.state` in middleware read path** (in
   `app/desktop/git_sync/middleware.py`): just before calling
   `ensure_fresh_for_read()` in the `if not needs_lock:` branch, set
   `request.state.git_sync_manager = manager`. This makes the manager
   available to `@no_write_lock` endpoints for building save contexts. No
   behavior change for endpoints that don't read the attribute.

4. **Add `build_save_context` helper** in
   `libs/server/kiln_server/git_sync_decorators.py` (colocating the decorators
   and the helper since they are the only git-sync-aware surface in
   `libs/server`):

   ```python
   from starlette.requests import Request

   from kiln_ai.utils.git_sync_protocols import AtomicWriteCapable, SaveContext


   def build_save_context(request: Request) -> SaveContext | None:
       """Return a SaveContext that wraps writes in manager.atomic_write(...),
       or None if git sync is not active for this request.

       The endpoint passes the returned value to its runner; the runner
       defaults to a no-op context when None.
       """
       manager: AtomicWriteCapable | None = getattr(
           request.state, "git_sync_manager", None
       )
       if manager is None:
           return None

       context = f"{request.method} {request.url.path}"

       def factory():
           return manager.atomic_write(context=context)

       return factory
   ```

5. **Apply `@no_write_lock` and wire `save_context` on 5 SSE endpoints.** For
   each, add `request: Request` to the signature and `save_context =
   build_save_context(request)` just before constructing the runner. Pass
   `save_context=save_context` to the runner constructor.

   - `libs/server/kiln_server/document_api.py::run_extractor_config` -- passes
     to `ExtractorRunner(...)`.
   - `libs/server/kiln_server/document_api.py::extract_file` -- passes to
     `ExtractorRunner(...)`.
   - `libs/server/kiln_server/document_api.py::run_rag_config` -- passes to
     `build_rag_workflow_runner(project, rag_config_id,
     save_context=save_context)`.
   - `app/desktop/studio_server/eval_api.py::run_eval_config` (the
     `run_comparison` endpoint) -- passes to `EvalRunner(...)`.
   - `app/desktop/studio_server/eval_api.py::run_eval_config_eval` (the
     `run_calibration` endpoint) -- passes to `EvalRunner(...)`.

   Import `Request` from `starlette.requests` (or `fastapi` -- FastAPI
   re-exports it) in both files. Import `no_write_lock` and
   `build_save_context` from `kiln_server.git_sync_decorators` in both files.

6. **Set `KILN_DEV_MODE` in `dev_server.py`** alongside the existing
   `DEBUG_EVENT_LOOP`:

   ```python
   os.environ["KILN_DEV_MODE"] = "true"
   ```

   Purely wiring for phase 4 -- no middleware change lands this phase.

## Tests

### `libs/server/kiln_server/test_git_sync_decorators.py` (new)

- `test_write_lock_sets_attribute`: `@write_lock` sets
  `_git_sync_write_lock=True`.
- `test_no_write_lock_sets_attribute`: `@no_write_lock` sets
  `_git_sync_no_write_lock=True`.
- `test_write_lock_preserves_function`: decorated fn still callable, same
  return.
- `test_no_write_lock_preserves_function`: same.
- `test_undecorated_has_no_attributes`: no attrs by default.
- `test_build_save_context_returns_none_without_manager`: construct a
  `Request` with an empty `state`; `build_save_context(request)` returns
  `None`.
- `test_build_save_context_returns_factory_with_manager`: attach a fake
  manager (simple class with an `atomic_write` async context manager) to
  `request.state.git_sync_manager`; assert the returned value is callable and
  that entering the context calls `manager.atomic_write(context=...)` with the
  expected string `f"{method} {path}"`.
- `test_build_save_context_wraps_and_exits_on_success`: use a recording
  manager; assert enter and exit both run around an inner `pass`.
- `test_build_save_context_wraps_and_exits_on_exception`: raise inside the
  context; assert the manager's context `__aexit__` saw the exception and the
  exception propagates.

Existing `app/desktop/git_sync/test_decorators.py`, `test_middleware.py`, and
integration `test_decorators.py` / `test_no_write_lock_batch.py` only need
import path updates -- no behavioral assertion changes.

### Middleware tests

Add `test_manager_attached_to_request_state_for_read` in
`app/desktop/git_sync/test_middleware.py`: a GET endpoint that reads
`request.state.git_sync_manager` and returns something derivable from it
(e.g. the repo path). Assert the endpoint sees the manager, proving the
middleware wired it.

### Endpoint tests -- decorator presence + save_context wiring

One test per endpoint in the co-located test file, keeping assertions
mechanical so they don't duplicate existing endpoint behavior tests:

- `libs/server/kiln_server/test_document_api.py`:
  - `test_run_extractor_config_has_no_write_lock`: assert
    `getattr(run_extractor_config, "_git_sync_no_write_lock", False) is True`.
    (Must be done by introspecting the registered route's endpoint
    function, since it's defined inside `connect_document_api`.)
  - `test_extract_file_has_no_write_lock`: same.
  - `test_run_rag_config_has_no_write_lock`: same.
  - `test_run_rag_config_passes_save_context_to_builder`: patch
    `build_rag_workflow_runner`; assert it's called with a non-default
    `save_context` kwarg when `request.state.git_sync_manager` is populated,
    and with `save_context=None` (or omitted) when it's not. Use
    `TestClient` plus a mock middleware that sets `request.state`.
  - `test_run_extractor_config_passes_save_context_to_runner`: patch
    `ExtractorRunner`; assert it's constructed with the expected
    `save_context` kwarg based on `request.state.git_sync_manager` presence.
  - `test_extract_file_passes_save_context_to_runner`: same pattern.

- `app/desktop/studio_server/test_eval_api.py` (or the appropriate
  test file for this module):
  - `test_run_comparison_has_no_write_lock`: introspection test.
  - `test_run_calibration_has_no_write_lock`: introspection test.
  - `test_run_comparison_passes_save_context_to_runner`: patch `EvalRunner`,
    same pattern as above.
  - `test_run_calibration_passes_save_context_to_runner`: same.

(If the `save_context` introspection style tests are hard to do without
building up a full app harness, fall back to a simpler unit test: call
`build_save_context` with a stub `Request` and assert the returned factory
calls `atomic_write(context=...)` with the expected string. Combined with the
endpoint-has-decorator tests, this is enough coverage for phase 3.)

### `dev_server.py` test

No test -- the module-level `os.environ[...] = "true"` runs on import and is
exercised by phase 4's dev-mode tests (which set and unset the env var
directly). Keep phase 3 narrowly scoped to wiring.

### Existing tests that must keep passing

- `app/desktop/git_sync/test_decorators.py` (import path change only).
- `app/desktop/git_sync/test_middleware.py` (import path change only, and the
  new `request.state.git_sync_manager` attachment shouldn't affect existing
  assertions).
- `app/desktop/git_sync/integration_tests/test_decorators.py` and
  `test_no_write_lock_batch.py` (import path change only).
- All existing `document_api` / `eval_api` endpoint behavior tests. Adding
  `Request` to the signature is FastAPI-transparent -- no caller change.
- All existing runner tests.
