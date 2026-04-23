---
status: complete
---

# Phase 4: Dev-Mode Dirty State Detection

## Overview

Adds a dev-only safety net that catches missing write locks immediately on the
request that caused them. Two pieces:

1. A new `get_dirty_file_paths()` accessor on `GitSyncManager` for diagnostic
   logging.
2. Middleware enhancement: after every regular read-path request (i.e. not
   write-locked, not `@no_write_lock`) on a project with active git sync, in
   dev mode (`KILN_DEV_MODE=true`):
   - If the response is SSE, log a loud error pointing the developer at the
     missing `@no_write_lock` decorator. Do not modify the response body --
     SSE streams are already in flight and the body cannot be replaced.
   - If the repo is dirty, log a loud error with method/path/dirty files and
     return a 500 JSON error (the request claimed not to write but did).

Production behavior is unchanged -- `ensure_clean()` continues to recover on
the next write request when the env var is not set.

## Steps

### 1. Add `get_dirty_file_paths()` to `GitSyncManager`

In `app/desktop/git_sync/git_sync_manager.py`, add a new public async method
beside `has_dirty_files()`:

```python
async def get_dirty_file_paths(self) -> list[str]:
    return await self._run_git(self._get_dirty_file_paths_sync)
```

And the synchronous helper alongside `_has_dirty_files_sync`:

```python
def _get_dirty_file_paths_sync(self) -> list[str]:
    repo = self._get_repo()
    status = repo.status()
    paths: list[str] = []
    for path, flags in status.items():
        if flags == pygit2.enums.FileStatus.IGNORED:
            continue
        if flags == pygit2.enums.FileStatus.CURRENT:
            continue
        paths.append(path)
    return paths
```

This mirrors the existing `_has_dirty_files_sync` filter exactly so the two
stay in sync.

### 2. Add `_is_dev_mode()` helper in middleware

In `app/desktop/git_sync/middleware.py`, add a module-level helper:

```python
import os

def _is_dev_mode() -> bool:
    return os.environ.get("KILN_DEV_MODE", "false") == "true"
```

(Keep it module-level rather than a method so tests can patch
`os.environ` and re-import the module behavior cleanly. The function is
trivial; we use a function rather than a constant so changes to the env var at
test time are picked up.)

### 3. Add post-request dirty check in middleware read path

Update the `if not needs_lock:` branch in
`app/desktop/git_sync/middleware.py` to perform the dev-mode dirty check
**only** for regular read-path requests -- i.e., not for `@no_write_lock`
self-managed endpoints.

Before:

```python
if not needs_lock:
    request.state.git_sync_manager = manager
    try:
        await manager.ensure_fresh_for_read()
    except GitSyncError as e:
        ...
    self._notify_background_sync(manager)
    return await call_next(request)
```

After:

```python
if not needs_lock:
    request.state.git_sync_manager = manager
    try:
        await manager.ensure_fresh_for_read()
    except GitSyncError as e:
        ...
    self._notify_background_sync(manager)

    is_self_managed = getattr(endpoint, "_git_sync_no_write_lock", False)
    if is_self_managed:
        return await call_next(request)

    response = await call_next(request)

    if _is_dev_mode():
        return await self._dev_mode_dirty_check(request, response, manager)

    return response
```

Add `_dev_mode_dirty_check` as a method on `GitSyncMiddleware`:

```python
async def _dev_mode_dirty_check(
    self,
    request: Request,
    response: Response,
    manager: GitSyncManager,
) -> Response:
    content_type = response.headers.get("content-type", "")
    if "text/event-stream" in content_type:
        logger.error(
            "DEV MODE: SSE endpoint missing @no_write_lock: %s %s",
            request.method,
            request.url.path,
        )
        return response

    if await manager.has_dirty_files():
        dirty = await manager.get_dirty_file_paths()
        logger.error(
            "DEV MODE: Request left repo dirty without write lock!\n"
            "  API: %s %s\n  Project: %s\n  Dirty files: %s",
            request.method,
            request.url.path,
            manager.repo_path,
            dirty,
        )
        return Response(
            content=json.dumps(
                {
                    "detail": "Dev mode: this endpoint wrote files without "
                    "holding a write lock. See server logs for details."
                },
                ensure_ascii=False,
            ),
            status_code=500,
            media_type="application/json",
        )

    return response
```

Notes:
- The dirty check only runs in the regular read path, never for write-lock or
  `@no_write_lock` requests, per the functional spec ("Scope of the Check").
- For SSE responses we don't try to swap the body -- the headers are already
  on the wire by the time we'd inspect them. Logging is enough for dev-mode
  diagnostics; the developer sees the error in the server logs and adds the
  decorator.
- `has_dirty_files()` is a fast no-op when clean, so the production-disabled
  check has no observable cost in dev mode either.

## Tests

All in `app/desktop/git_sync/test_middleware.py`, plus one new test in
`app/desktop/git_sync/test_git_sync_manager.py`.

### `test_git_sync_manager.py`

- `test_get_dirty_file_paths_clean_repo`: empty list when no dirty files.
- `test_get_dirty_file_paths_modified_file`: returns the modified file path.
- `test_get_dirty_file_paths_untracked_file`: returns the new file path.
- `test_get_dirty_file_paths_multiple_files`: returns all dirty paths
  (modified + untracked + deleted) -- sort or compare as sets to avoid
  ordering flakiness.

### `test_middleware.py`

Use `monkeypatch` to set/unset `KILN_DEV_MODE` per test. Add a fixture-scoped
helper `dev_mode_on` and `dev_mode_off` (or just `monkeypatch.setenv` inline).

- `test_dev_mode_dirty_read_returns_500`: dev mode on; GET endpoint that
  writes a file but no `@no_write_lock`; assert 500 with the expected
  detail string and that the dirty file is rolled back / surfaced.
  (Don't assert rollback -- this phase doesn't add rollback to the read
  path; just that the endpoint surfaced as 500. Cleanup is left to the
  next write request's `ensure_clean()`, as the spec specifies.)
- `test_dev_mode_clean_read_passes`: dev mode on; GET endpoint that does
  not write; assert 200 and the original response body.
- `test_dev_mode_off_dirty_read_passes`: dev mode off; GET endpoint that
  writes; assert the original 200 response (no 500). Confirms no
  production-mode behavior change.
- `test_dev_mode_no_write_lock_skips_dirty_check`: dev mode on; GET
  endpoint decorated with `@no_write_lock` that writes a file; assert
  200 (no 500) -- the spec says self-managed endpoints are skipped.
  Clean up the dirty file after the test (call `manager.rollback`) so
  fixture teardown isn't tripped.
- `test_dev_mode_sse_without_no_write_lock_logs_error`: dev mode on; GET
  endpoint that returns a `StreamingResponse` with `media_type=
  "text/event-stream"` but no `@no_write_lock` decorator; assert 200 and
  that the error log contains "DEV MODE: SSE endpoint missing
  @no_write_lock". Use `caplog.at_level(logging.ERROR)` to assert.
- `test_dev_mode_dirty_check_skipped_for_write_lock_path`: dev mode on;
  POST endpoint (already wrapped by middleware write lock); assert 200
  and that the dirty check did not log -- the write path commits
  through `atomic_write`, so the dirty check is unnecessary.

### Existing tests that must keep passing

- All existing middleware tests (none change behavior; dev mode defaults
  to off so the new branch is inert).
- All existing `git_sync_manager` tests (the new method is additive).
