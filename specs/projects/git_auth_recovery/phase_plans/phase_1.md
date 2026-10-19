---
status: complete
---

# Phase 1: Error envelope + auth classification (backend)

## Overview

Fix the middleware error envelope shape and add auth-specific error classification.
Today, `GitSyncMiddleware` emits `{"detail": ...}` while the rest of the app uses
`{"message": ...}`, causing the frontend to show "Unknown error". Additionally, all
git fetch failures are reported as connectivity errors even when the real cause is
expired credentials. This phase fixes both issues server-side.

## Steps

1. **Add `GitAuthError` to `app/desktop/git_sync/errors.py`**
   ```python
   class GitAuthError(GitSyncError):
       """Git authentication failed or expired (bad/expired token, 401/403)."""
   ```

2. **Classify auth errors in `GitSyncManager.fetch()` (`git_sync_manager.py`)**
   - Add `_AUTH_ERROR_MARKERS` tuple and `_is_auth_error(e)` helper at module level.
   - In `fetch()`, catch `pygit2.GitError` and branch on `_is_auth_error`:
     raise `GitAuthError` for auth failures, `RemoteUnreachableError` otherwise.

3. **Widen `except` in `ensure_fresh` / `ensure_fresh_for_read`**
   - Change `except RemoteUnreachableError: raise` to `except GitSyncError: raise`
     so `GitAuthError` propagates instead of being re-wrapped as
     `RemoteUnreachableError`.

4. **Add `GitAuthError` to `ERROR_MAP` in `middleware.py`**
   ```python
   GitAuthError: (
       401,
       "Git authentication failed or expired. Re-import the project to "
       "reconnect with fresh credentials.",
   ),
   ```

5. **Change all `{"detail": ...}` to `{"message": ...}` in `middleware.py`**
   Six sites: `_no_write_lock_asgi` read error, `dispatch` read error,
   `_StreamingUnderWriteLock` catch, write-path `GitSyncError` catch,
   `_dev_mode_dirty_check` 500, `_unmatched_dispatch` dev-mode 500.

6. **Update existing tests in `test_middleware.py`**
   - Change all `body["detail"]` assertions to `body["message"]`.

## Tests

- `test_error_mapping` parametrized: add `GitAuthError` -> 401 case; update all
  expected keys from `detail` to `message`.
- `test_fetch_raises_git_auth_error_for_auth_failure`: `fetch()` raises `GitAuthError`
  when pygit2 error contains auth markers.
- `test_fetch_raises_remote_unreachable_for_non_auth_failure`: `fetch()` raises
  `RemoteUnreachableError` for generic network errors.
- `test_ensure_fresh_for_read_propagates_git_auth_error`: verifies `GitAuthError`
  from `fetch()` propagates through `ensure_fresh_for_read` unchanged.
- `test_ensure_fresh_propagates_git_auth_error`: same for `ensure_fresh`.
- `test_is_auth_error_markers`: parametrized test for `_is_auth_error` with
  representative auth and non-auth messages.
