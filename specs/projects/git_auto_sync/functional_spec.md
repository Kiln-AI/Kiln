---
status: complete
---

# Functional Spec: Git Auto Sync

## Overview

Git Auto Sync provides automatic, transparent git-based synchronization for Kiln projects. Users in "auto" mode get cloud sync and collaboration without needing to understand git. The system handles pull, commit, push, conflict resolution, and error recovery automatically — all through the existing FastAPI API layer.

## Modes

### Manual Mode (existing behavior)

The user manages git themselves. No sync middleware, no background pulls. This is the current default and remains available.

### Auto Mode

Git operations are fully managed. Every API write is committed and pushed. The repo is kept fresh via background polling. Users never interact with git directly.

**Toggle:** Per-project setting stored in project configuration. Default: manual. Can be switched at any time. When switching to auto, the system verifies the repo is in a clean state (no uncommitted changes, no conflicts) before enabling.

## Core Architecture: write_context API

The git sync system is a general-purpose library (not tied to FastAPI). It enforces correct usage through a single context manager — writes are impossible outside the proper context, so misuse is an immediate, obvious error rather than a subtle runtime bug.

### Design Goals

1. **Zero change for 99% of APIs.** The middleware wraps every request in a `write_context()`. Normal API handlers just call `save_to_file()` as usual — the context handles pull, commit, push, and locking transparently.
2. **Only special APIs think about contexts.** Long-running or batched operations (e.g., evals) opt into nested contexts for finer-grained commit/push control.
3. **Hard to misuse.** Writing outside a context is an immediate error. Mixing patterns (writing in parent context then nesting) is an immediate error. The library enforces correct usage rather than relying on callers to get the order right.
4. **Single concept.** One context manager (`write_context`) with configurable behavior via parameters, not multiple context types with different semantics.

### StorageWriter Abstraction

> **Note:** Originally called `StorageBackend` — renamed to `StorageWriter` because the scope was narrowed to write-only operations (3 methods). Reads are untouched.

An abstract `StorageWriter` base class defines the interface for model persistence. Two implementations:

- **`FileStorageWriter`** — Current behavior. Reads/writes `.kiln` files directly to disk. No git awareness.
- **`GitSyncStorageWriter`** — Wraps file I/O with git sync. All writes must occur within a `write_context`. Tracks written files automatically. Delegates actual file I/O to the same underlying logic.

`KilnBaseModel` loads the appropriate storage backend based on the project's configuration (auto mode → git sync backend, manual mode → file backend). The base model code doesn't know or care which backend is active — it calls the same interface.

**Key property:** The storage backend is how file writes are automatically tracked. When `save_to_file()` goes through `GitSyncStorageWriter`, the backend records the written file path in the active context. No explicit file tracking by the caller.

### GitSyncManager

A singleton per git repository path (not per project — a repo may contain multiple projects). Constructed with:

- **`repo_path`** — Path to the git repository root.
- **`project_path`** — Path to the project directory within the repo (may equal `repo_path`).
- **Configuration** — Remote name, branch, poll interval.

**Singleton scope:** One instance per repo path. If two projects share a repo, they share a manager. Created on first access, cached by repo path.

**State queries:** `is_fresh()`, `is_clean()`, `has_conflicts()`, etc.

**Standalone helper:** `manager.push()` — pushes all unpushed local commits to remote. Can only be called when the write lock is NOT held (i.e., between write contexts, not inside one). Useful for periodic push in long-running tasks.

### write_context

```python
with manager.write_context(push=True, check_in_sync=True) as ctx:
    # Entry: if check_in_sync, pull/rebase to ensure fresh (fail if offline)
    # During: writes via storage backend are tracked automatically
    # First write: acquires exclusive write lock (blocks with timeout if held)
    # Exit: commit tracked files, optionally push to remote, release lock
```

**Parameters:**
- **`push`** (default `True`) — Whether to push to remote after committing on exit.
- **`check_in_sync`** (default `True`) — Whether to pull/rebase on entry to ensure the repo is up-to-date. Fails if remote is unreachable (online-only).

**Lazy lock acquisition:** The write lock is NOT acquired on context entry. It is acquired on the first write within the context. This means read-only API calls wrapped in a `write_context` by the middleware never acquire the lock and never block. Only requests that actually write pay the locking cost.

**Writes go through the manager:** The `GitSyncStorageWriter` delegates all file I/O to the manager:

- **`manager.write_file(file_path, data)`** — In a single call: acquires the write lock if not already held (errors if no active `write_context`), writes the file to disk, and tracks it in the active context. Impossible to forget a step.
- **`manager.read_file(file_path)`** — Reads a file. No lock, no context required.

This is the only way the storage backend does I/O. The manager knows its own active context internally — no context objects are passed around.

**Enforced constraint:** `manager.write_file()` raises an error if called outside any `write_context`. This makes "forgot to wrap in context" an immediate, obvious failure.

**On exit behavior:**
- Files written, no exception: commit + push (if `push=True`). If push fails, revert commit and raise. Release lock.
- Files written, exception occurred (non-nested): **rollback** — revert written files to their pre-write state, do not commit. Release lock. Re-raise.
- Files written, exception occurred (nested): any already-committed nested contexts are preserved (they already committed on their own exit). Push those commits if `push=True`. Rollback any uncommitted writes from the failed context. Re-raise.
- No files written: no-op, no lock to release.

**Auto-generated commit message** based on tracked files and the nature of changes (see Commit Messages section).

### Nesting Behavior

`write_context` supports nesting with clear rules designed to prevent misuse:

**How nesting works:**
- When a nested `write_context` opens, the **parent releases its write lock** (if held). The parent becomes a lifecycle boundary (responsible for its `check_in_sync` on entry and `push` on exit) but no longer holds the lock.
- The **nested context acquires the lock lazily** (on first write). On its exit, it commits its tracked files and releases the lock.
- Between nested contexts, the lock is free — other API requests can proceed.
- On parent exit, it pushes all unpushed commits if `push=True`.

**Parent push failure (nested case):** If the parent context's final push fails (remote diverged since the nested contexts committed), the recovery is: pull/rebase (which replays the nested commits on top of the new remote state), then re-push. If rebase conflicts, revert the local commits that haven't been pushed (via `git rebase --abort` + `git reset` to the last pushed state) and surface an error. The already-pushed commits from earlier `manager.push()` calls within the loop are safe.

**The mixing error:** If the parent context has already tracked writes (files were saved directly in it) and a nested context opens, this is an **immediate error**. You must pick one pattern: either write directly in the context (no nesting), or delegate all writes to nested contexts. This prevents confusing scenarios where some writes land in the parent's commit and others in nested commits.

**Examples:**

```python
# Normal API call — middleware wraps, handler just writes (99% of APIs)
with manager.write_context():  # push=True, check_in_sync=True
    task = Task(name="My Task")
    task.save_to_file()  # tracked automatically
# Exit: commit, push, done. No API code changes needed.

# Long-running eval — nested contexts for incremental commits
with manager.write_context():  # outer: pulls on entry, pushes on exit
    for item in eval_items:
        with manager.write_context(push=False, check_in_sync=False):  # inner: commit only
            result = run_eval(item)
            result.save_to_file()
        # Inner exit: commit, release lock. App remains usable.
        if should_push_now():
            manager.push()  # periodic push between contexts
    # Outer exit: final push of any unpushed commits

# Async dispatch — each task gets its own write context
with manager.write_context():  # outer: pulls, pushes on exit
    async def process(item):
        with manager.write_context(push=False, check_in_sync=False):
            result = run_eval(item)
            result.save_to_file()
    await asyncio.gather(*[process(i) for i in eval_items])
    # Inner contexts serialize via the write lock
    # Outer exit: pushes all commits

# ERROR — mixing patterns
with manager.write_context():
    task.save_to_file()  # write tracked in outer context
    with manager.write_context(push=False):  # ERROR: outer already has writes
        something.save_to_file()
```

### Error Summary

| Situation | Behavior |
|-----------|----------|
| Write outside any write_context (git backend) | Immediate error |
| Nested context opens after parent already has writes | Immediate error |
| `manager.push()` while write lock is held | Immediate error |
| `manager.push()` with nothing to push | No-op |
| Write lock acquisition times out | Error (503 to client) |

## Request Lifecycle (Auto Mode)

### Standard Requests (reads and writes)

The middleware wraps every request in a `write_context()` with defaults (`push=True, check_in_sync=True`):

1. **Entry:** Pull/rebase to ensure fresh. If offline → 503. Lock is NOT acquired yet.
2. **Execution:** API handler runs. If it writes, the first `save_to_file()` call acquires the write lock and tracks files. Read-only requests never acquire the lock.
3. **Exit (writes occurred):** Check for out-of-band changes → commit tracked files → push. On push failure: revert, re-pull, retry once, else 409. Release lock.
4. **Exit (no writes):** No-op. No lock was acquired, nothing to release.
5. **Exit (exception, non-nested):** Rollback written files, do not commit. Release lock. Return error.

### Long-Running Write Requests

The middleware still wraps these in a `write_context()`. The API handler opens nested `write_context(push=False, check_in_sync=False)` blocks for each atomic unit:

1. **Outer context (middleware):** Ensures fresh on entry. Does not write directly — delegates to nested contexts. Pushes all unpushed commits on exit.
2. **Each nested context:** Acquires lock, tracks writes, commits on exit, releases lock.
3. **Between nested contexts:** Lock is released — other API requests can proceed. `manager.push()` can be called for periodic push.
4. **On error mid-loop:** Previously committed iterations are preserved. Outer context pushes them on exit. The failed iteration's writes are rolled back.

## Background Sync

A background async task polls remote for changes every few seconds (configurable, default: 5s). This keeps the local repo fresh so that `ensure_fresh()` in the middleware rarely needs to block.

- Runs only when auto mode is enabled for at least one project in the repo.
- Uses the same `GitSyncManager` — respects the write lock (waits if a write is in progress).
- On pull failure (network): logs warning, retries on next poll. Does not block API calls (the middleware's `ensure_fresh()` will catch staleness).

## Conflict Handling

### Strategy: Rebase-Only

All pulls use `git pull --rebase`. No merge commits. This keeps history linear and is simpler to reason about.

### Conflict During Push

When `commit_and_push()` fails because remote has diverged:

1. Revert the local commit (preserving the working tree changes).
2. Pull + rebase from remote.
3. If rebase succeeds cleanly: re-commit and re-push. *(Note: this retry happens once — if it fails again, abort.)*
4. If rebase has conflicts: abort rebase, restore pre-request state, return error to client.

The client receives a 409 error. The user's action is: retry the operation (which will now be based on fresh data).

### Why Conflicts Are Rare

- Data model is append-only and immutable for most operations (new runs, new documents, etc.)
- Files use unique IDs in paths — two users creating items won't touch the same files
- The background poller keeps local state within seconds of remote
- Write lock prevents local interleaving

## Out-of-Band File Edits

**Problem:** If a user manually edits `.kiln` files outside the API, `git status` will show unexpected dirty files. This could interfere with the commit logic.

**Approach: Detect and Reject**

- Before committing, compare the set of dirty files (from `git status`) against the set of files tracked by the write context (recorded by `save_to_file()` calls).
- If any dirty files are NOT in the tracked set, **fail the API call** with a clear error (400: "Unexpected file changes detected outside of API. Please resolve before continuing.").
- This comparison is specific: only files outside the tracked set are flagged. Files that are dirty because of a background pull (which modifies the working tree) are not a concern because the background poller respects the write lock — it cannot run while a write context holds the lock, so the working tree is stable during the detection window.
- Provides a `manager.is_clean()` check for use in health checks or pre-request validation.

This is the strictest approach — it ensures git state is always predictable and prevents accidental commits of garbage. The tradeoff is that a user manually editing files will break API calls until the changes are reverted or committed manually. This is acceptable for V1; a more lenient approach (auto-committing or ignoring out-of-band changes) can be added later.

## Commit Messages

Auto-generate descriptive commit messages based on the changes made:

- Include the API action that triggered the commit (e.g., "Create task 'Summarize articles'", "Update prompt for task 'Translation'", "Run eval on task 'QA'")
- For multi-file commits, summarize the batch (e.g., "Eval run: 15 results for task 'QA'")
- Keep messages concise but informative — they should be meaningful when browsing git history
- Format: `[Kiln] <action description>` prefix for easy identification in shared repos

## Configuration

### Per-Project Settings

- **sync_mode:** `"manual"` | `"auto"` (default: `"manual"`)

### Per-Repo Settings (managed by GitSyncManager)

- **poll_interval_seconds:** Background sync interval (default: 5)
- **remote_name:** Git remote to sync with (default: `"origin"`)
- **branch:** Branch to sync (default: current branch)

### Where Configuration Lives

Stored in the existing Kiln config system. Not in git-tracked files (sync settings are per-machine, not shared).

## Error Handling

| Scenario | Behavior | User-Facing Error |
|----------|----------|-------------------|
| Remote unreachable on write | Rollback, fail request | 503: "Cannot sync with remote. Check your connection." |
| Remote unreachable on read | Fail request | 503: "Cannot sync with remote. Check your connection." |
| Push conflict | Rollback, re-pull, retry once | 409: "Conflict detected. Please retry." |
| Rebase conflict (unresolvable) | Abort rebase, restore state | 500: "Sync conflict could not be auto-resolved. Disable auto-sync and resolve manually." |
| Write lock timeout | Fail request | 503: "Server busy. Please retry." |
| Out-of-band file changes | Reject API call, do not commit | 400: "Unexpected file changes detected outside of API. Resolve before continuing." |
| Corrupt repo state | Refuse to operate, surface error | 500: "Git repository is in an unexpected state. Disable auto-sync and check manually." |

## Out of Scope (V1)

- **Login/auth UX:** V1 assumes the repo is already cloned and credentials are configured.
- **Clone/setup flow:** User must set up the repo manually. Setup wizard is a future feature.
- **Non-GitHub remotes:** Should work (pygit2 is provider-agnostic) but not explicitly tested in V1.
- **Multi-remote sync:** Single remote only.
- **Branch management:** Syncs current branch only. No branch creation/switching.
- **UI for conflict resolution:** If auto-resolve fails, user must resolve manually in git.
- **Offline mode:** No offline support. All writes require successful push.
- **Dirty repo resolution UX:** When enabling auto mode on a repo with uncommitted changes, V1 requires the user to resolve this manually. A future enhancement should provide a UI flow to help non-technical users clean up (e.g., "commit all and enable" or "discard and enable").

## Technical Constraints

- **Library:** pygit2 (libgit2 Python bindings). No shelling out to git CLI — users are non-technical.
- **Code location:** All git sync code lives in `app/desktop/` as a new sub-project. Middleware and settings integration also in `app/`.
- **Async compatibility:** The library must work with asyncio (FastAPI is async). Blocking git operations should run in a thread executor to avoid blocking the event loop.
- **Thread safety:** `GitSyncManager` must be thread-safe. The write lock must work across async tasks and threads.
- **pygit2 thread safety:** pygit2 objects (Repository, Index, etc.) are C extension objects backed by libgit2 and are not thread-safe. The `GitSyncManager` should funnel ALL pygit2 operations (including background sync, status checks, and read operations) through a single-threaded executor to prevent concurrent libgit2 calls, which can cause segfaults.

## Integration with Existing Code

### Storage Backend in BaseModel

`KilnBaseModel` is refactored to use a `StorageWriter` abstraction:

- An abstract `StorageWriter` defines `save()` and `load()` methods.
- `FileStorageWriter` implements current behavior (direct file I/O).
- `GitSyncStorageWriter` wraps file I/O with context tracking and enforces writes only within a `write_context`.
- The backend is selected based on the project's sync mode configuration. `KilnBaseModel` resolves the backend for the relevant project and delegates to it.

This is the only change to `libs/core` — the storage backend abstraction. All git sync logic lives in `app/desktop/`.

### FastAPI Middleware

New middleware wraps each request in a `write_context()` with defaults (`push=True, check_in_sync=True`). Added to the server stack in `app/desktop/`.

### Config System

Extended to store sync mode per project.

## Documentation

A README must be created describing library usage. It should cover:

- How to configure a project for auto sync
- The `write_context` API with parameter explanations
- Usage patterns: simple (middleware default), long-running (nested), async (dispatch)
- Error handling and what each error means
- The nesting rules and the mixing error
