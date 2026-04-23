---
status: draft
---

# Phase 1: Core GitSyncManager

## Overview

This phase implements the foundational git sync engine: error types, config model, commit message generation, and the `GitSyncManager` class. The manager encapsulates all pygit2 operations behind a single-threaded executor for thread safety, provides an async write lock, and implements the core operations needed by the middleware in Phase 2: ensure_clean, ensure_fresh, get_head, has_dirty_files, commit_and_push (with push-retry on conflict), rollback, fetch, can_fast_forward, fast_forward, and close.

## Steps

### 1. Create `app/desktop/git_sync/__init__.py`

Empty init file to make git_sync a package.

### 2. Create `app/desktop/git_sync/errors.py`

Error hierarchy:
- `GitSyncError(Exception)` -- base
- `SyncConflictError(GitSyncError)` -- rebase conflict
- `RemoteUnreachableError(GitSyncError)` -- network failure
- `WriteLockTimeoutError(GitSyncError)` -- lock timeout
- `CorruptRepoError(GitSyncError)` -- unrecoverable state

### 3. Create `app/desktop/git_sync/config.py`

- `GitSyncProjectConfig` TypedDict with fields: `sync_mode`, `remote_name`, `branch`, `clone_path`
- `get_git_sync_config(project_id: str) -> GitSyncProjectConfig | None` helper reading from Config
- Add `git_sync_projects` ConfigProperty to the Config class (dict, default_lambda=lambda: {})

### 4. Create `app/desktop/git_sync/commit_message.py`

- `generate_commit_message(file_count: int, api_path: str) -> str`
- Format: `[Kiln] Auto-sync: N files changed\n\nAPI: POST /api/projects/...`

### 5. Create `app/desktop/git_sync/git_sync_manager.py`

Core class with:
- `__init__(repo_path, remote_name)`: sets up ThreadPoolExecutor(max_workers=1), threading.Lock for write lock
- `_run_git(fn, *args)`: runs fn in executor with timeout
- `write_lock()`: async context manager, acquires threading.Lock via asyncio.to_thread
- `ensure_clean()`: checks status + repo state, runs crash recovery (stash, abort rebase, reset unpushed)
- `ensure_fresh()`: fetch + fast-forward if behind (skip if recently synced within threshold)
- `get_head()`: returns HEAD oid as hex string
- `has_dirty_files()`: checks repo.status() for any non-CURRENT, non-IGNORED entries
- `commit_and_push(api_path, pre_request_head)`: stage all, commit, push; on push failure: fetch, rebase, retry once; on second failure or rebase conflict: raise
- `rollback(pre_request_head)`: stash dirty, reset to pre_request_head if HEAD changed
- `fetch()`: fetch from remote
- `has_new_remote_commits()`: compare local HEAD vs remote tracking ref
- `can_fast_forward()`: check if local can FF to remote
- `fast_forward()`: update local branch + working tree to remote tracking ref
- `close()`: shutdown executor

### 6. Add pygit2 dependency to `app/desktop/pyproject.toml`

### 7. Write unit tests in `app/desktop/git_sync/test_git_sync_manager.py`

Tests using temporary bare+cloned repos via pygit2:
- `test_has_dirty_files_clean` / `test_has_dirty_files_dirty`
- `test_get_head`
- `test_commit_and_push_success`
- `test_commit_and_push_conflict_retry_success`
- `test_commit_and_push_conflict_retry_fails`
- `test_rollback_dirty_files`
- `test_rollback_committed_not_pushed`
- `test_ensure_clean_when_clean`
- `test_ensure_clean_dirty_recovery`
- `test_ensure_clean_unpushed_commits`
- `test_ensure_fresh_fetches_and_forwards`
- `test_fetch`
- `test_can_fast_forward`
- `test_fast_forward`
- `test_write_lock_timeout`
- `test_write_lock_serialization`
- `test_close`

### 8. Write unit tests for config and commit_message

- `app/desktop/git_sync/test_config.py`
- `app/desktop/git_sync/test_commit_message.py`

## Tests

- test_has_dirty_files_clean: clean repo returns False
- test_has_dirty_files_dirty: modified file returns True
- test_has_dirty_files_untracked: new untracked file returns True
- test_get_head: returns current HEAD oid hex
- test_commit_and_push_success: stages, commits, pushes; remote has new commit
- test_commit_and_push_conflict_retry_success: push fails, fetch+rebase+push succeeds
- test_commit_and_push_conflict_retry_fails: both pushes fail, raises SyncConflictError
- test_rollback_dirty_files: stashes dirty state, working tree clean
- test_rollback_committed_not_pushed: resets HEAD to pre-request state
- test_ensure_clean_when_clean: no-op when repo is clean
- test_ensure_clean_dirty_recovery: stashes dirty state from prior crash
- test_ensure_clean_unpushed_commits: resets unpushed commits to match remote
- test_ensure_fresh_fetches_and_forwards: pulls remote changes into local
- test_fetch: updates remote tracking refs without changing working tree
- test_can_fast_forward_true: returns True when local is behind
- test_can_fast_forward_false: returns False when local has diverged
- test_fast_forward: updates local to match remote
- test_write_lock_timeout: raises WriteLockTimeoutError after timeout
- test_write_lock_serialization: second lock waits for first
- test_close: executor shuts down cleanly
- test_generate_commit_message: correct format
- test_get_git_sync_config: reads config correctly
- test_get_git_sync_config_missing: returns None for unknown project
