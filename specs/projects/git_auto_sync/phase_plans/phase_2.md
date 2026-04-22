---
status: draft
---

# Phase 2: Middleware, Decorators, and Registry

## Overview

This phase builds the HTTP middleware layer that wraps mutating API requests with git sync operations. It implements the `@write_lock` and `@no_write_lock` decorators for annotating endpoints, a `GitSyncRegistry` for managing per-repo `GitSyncManager` instances, and the `GitSyncMiddleware` (BaseHTTPMiddleware) that acquires the write lock, runs clean/fresh checks, commits on success, and rolls back on failure. It also registers the middleware in `desktop_server.py`.

## Steps

### 1. Create `app/desktop/git_sync/decorators.py`

Two decorators that set function attributes read by the middleware:

```python
def write_lock(fn):
    fn._git_sync_write_lock = True
    return fn

def no_write_lock(fn):
    fn._git_sync_no_write_lock = True
    return fn
```

### 2. Create `app/desktop/git_sync/registry.py`

`GitSyncRegistry` class:
- Class-level `_managers: dict[Path, GitSyncManager]` and `_lock: threading.Lock`
- `get_manager(repo_path) -> GitSyncManager | None`
- `register(repo_path, manager)`
- `get_or_create(repo_path, remote_name) -> GitSyncManager`
- `reset()` -- clears all, shuts down executors (for test teardown)

### 3. Create `app/desktop/git_sync/middleware.py`

`GitSyncMiddleware(BaseHTTPMiddleware)`:
- `dispatch(request, call_next)`:
  - Extract project_id from URL path (`/api/projects/{project_id}/...`)
  - Look up config via `get_git_sync_config(project_id)`
  - If no config or sync_mode != "auto", pass through
  - Resolve manager from registry using clone_path from config
  - Check endpoint annotations for `_git_sync_write_lock` / `_git_sync_no_write_lock`
  - Non-mutating path: pass through (freshness check deferred to Phase 3)
  - Mutating path: acquire write lock, ensure_clean, ensure_fresh, capture pre_request_head, call handler, buffer response body, commit_and_push if dirty, return buffered response
  - On error: rollback, map GitSyncError to HTTP status, re-raise others
- `_get_manager_for_request(request) -> GitSyncManager | None`
- `_map_error(error) -> tuple[int, str]`

Error mapping:
- RemoteUnreachableError -> 503
- SyncConflictError -> 409
- WriteLockTimeoutError -> 503
- CorruptRepoError -> 500

### 4. Register middleware in `desktop_server.py`

Add `app.add_middleware(GitSyncMiddleware)` in `make_app()`, before the CORS middleware (which is added in kiln_server.make_app).

### 5. Create `app/desktop/git_sync/conftest.py`

Shared fixtures:
- `reset_git_sync_registry` (autouse): resets registry after each test
- `git_repos`: bare remote + cloned local repos (reuse pattern from Phase 1 tests)

### 6. Write tests

#### `app/desktop/git_sync/test_decorators.py`
- test_write_lock_sets_attribute
- test_no_write_lock_sets_attribute
- test_decorators_preserve_function

#### `app/desktop/git_sync/test_registry.py`
- test_get_or_create_new
- test_get_or_create_returns_existing
- test_get_manager_returns_none_for_unknown
- test_register_and_get
- test_reset_clears_all
- test_thread_safety (concurrent get_or_create)

#### `app/desktop/git_sync/test_middleware.py`
- test_non_project_route_passes_through
- test_get_request_passes_through
- test_mutating_request_commits_and_pushes (integration: real git repos)
- test_mutating_request_no_changes_no_commit
- test_mutating_request_error_rolls_back
- test_write_lock_decorator_on_get
- test_no_write_lock_decorator_on_post
- test_error_mapping (RemoteUnreachableError->503, SyncConflictError->409, WriteLockTimeoutError->503, CorruptRepoError->500)
- test_sync_disabled_passes_through (sync_mode="manual")
- Early integration test: verify BaseHTTPMiddleware holds lock across request lifecycle

## Tests

- test_write_lock_sets_attribute: decorator sets _git_sync_write_lock=True
- test_no_write_lock_sets_attribute: decorator sets _git_sync_no_write_lock=True
- test_decorators_preserve_function: wrapped function is callable and unchanged
- test_get_or_create_new: creates new manager for unknown path
- test_get_or_create_returns_existing: returns same instance for same path
- test_get_manager_returns_none_for_unknown: returns None when not registered
- test_register_and_get: manual register then get
- test_reset_clears_all: all managers cleared after reset
- test_thread_safety: concurrent get_or_create returns same instance
- test_non_project_route_passes_through: /ping passes without middleware action
- test_get_request_passes_through: GET /api/projects/... passes without lock
- test_mutating_request_commits_and_pushes: POST creates commit in remote
- test_mutating_request_no_changes_no_commit: POST with no file changes skips commit
- test_mutating_request_error_rolls_back: handler error triggers rollback
- test_write_lock_decorator_on_get: GET with @write_lock acquires lock
- test_no_write_lock_decorator_on_post: POST with @no_write_lock skips lock
- test_error_mapping: each error type maps to correct HTTP status
- test_sync_disabled_passes_through: manual mode routes pass through
- test_middleware_holds_lock_across_lifecycle: lock held during entire request
