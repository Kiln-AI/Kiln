---
status: draft
---

# Functional Spec: Git Auto Sync

## Overview

Git Auto Sync provides automatic, transparent git-based synchronization for Kiln projects. Users in "auto" mode get cloud sync and collaboration without needing to understand git. The system handles pull, commit, push, conflict resolution, and error recovery automatically — all through the existing FastAPI API layer.

## Modes

### Manual Mode (existing behavior)

The user manages git themselves. No sync middleware, no background pulls. This is the current default and remains available.

### Auto Mode

Git operations are fully managed. Every API write is committed and pushed. The repo is kept fresh via background polling. Users never interact with git directly.

**Toggle:** Per-project setting stored in project configuration. Default: manual. Can be switched at any time (takes effect on the next request). When switching to auto, the system verifies the repo is in a clean state (no uncommitted changes, no conflicts) before enabling.

## Isolated Repo Per Project

Each Kiln project using auto-sync gets its own full clone of the repository. Even if the user has a local repo, Kiln manages its own isolated copy. This ensures:

- No interference from the user's editor, IDE, or other tools
- No conflicts with other Kiln projects in the same repo
- Clean, predictable repo state for the sync system

**Location:** `.git-projects/[ID] - [projectname][N]` inside the existing default Kiln projects directory (`~/Kiln Projects`, use existing constant/path). The `.git-projects` folder is hidden by convention — the user doesn't need to know where it is. `[N]` is a counter suffix (2, 3, ...) added only if the name collides with an existing entry.

**Why full clone, not worktree:** Worktrees share `.git` internals (reflog, stash, gc, index locks). A full clone is truly isolated — operations on one project can never affect another. Shallow clone keeps disk usage minimal.

**Phased implementation:**
- **Phase 1:** Assume the configured repo is single-purpose. No clone setup needed. Configuration is manual.
- **Phase 2:** UI-driven setup flow creates the isolated clone automatically. See Setup Flow section.

## Core Design: HTTP-Method Middleware Lock

The git sync system works at the HTTP middleware level. No changes to `KilnBaseModel` or `libs/core/` are needed — filesystem writes happen exactly as they do today.

### How It Works

1. **Middleware inspects HTTP method.** For mutating requests (POST, PATCH, PUT, DELETE), acquire the write lock. For GET/HEAD, pass through without locking.
2. **On lock acquisition:** Verify the repo is clean via `git status`. If dirty, run crash recovery (see Recovery section). If still dirty after recovery, error.
3. **Ensure fresh:** Pull/rebase to ensure the repo is up-to-date with remote. If offline, fail (503).
4. **Handler runs normally.** Any filesystem operation works — no special writer or tracking needed. The handler reads and writes `.kiln` files exactly as it does today.
5. **On request exit (success):** Use `git status` to find all changed files. Stage everything, commit with auto-generated message, push to remote. Release lock.
6. **On request exit (failure):** Rollback all changes to the clean state verified at lock acquisition. Release lock.
7. **On request exit (no changes):** No-op. Release lock.

### Why This Works

The write lock + clean-state verification + isolated repo guarantees that any dirty files at commit time were created by the current request. Git is the single source of truth for what changed — no internal file tracking list that can get out of sync.

### Annotations

Two annotations modify the default middleware behavior:

- **`@write_lock`** — For GET endpoints that perform mutations (e.g., browser limitations requiring GET for a mutating action). Middleware acquires the write lock as if it were a POST.
- **`@no_write_lock`** — For long-running endpoints (SSE eval batch jobs) that manage their own commit cycle. Middleware skips the lock. See Long-Running Requests.

### Dev-Mode Safety Nets

- **Dirty state detection:** In development mode, check `git status` at the start and end of any request that did NOT hold the write lock. Dirty state at either point indicates a serious bug (likely a mutation in a GET endpoint). Raise a loud error.
- **Long lock hold warning:** In development mode, warn if the write lock is held for more than 5 seconds. Flags endpoints that should use `@no_write_lock` with explicit commit management instead.

## Request Lifecycle (Auto Mode)

### Standard Requests (reads)

GET/HEAD requests pass through middleware without locking. Served from local state. Background sync keeps the repo fresh.

### Standard Requests (writes)

POST/PATCH/PUT/DELETE requests:

1. **Acquire write lock.** Blocks if another write is in progress (waits in queue).
2. **Verify clean state.** `git status` — if dirty, run recovery routine.
3. **Ensure fresh.** Pull/rebase from remote. If offline → 503.
4. **Handler executes.** Reads and writes files normally.
5. **Exit (writes occurred):** `git status` finds changes → `git add` all → commit → push. If push fails, retry once (see Conflict Handling). If retry fails, rollback → error.
6. **Exit (no writes):** No-op.
7. **Exit (exception):** Rollback all changes (see Rollback). Return error.
8. **Release write lock.**

### Long-Running Write Requests

Endpoints annotated `@no_write_lock` (e.g., SSE eval batch jobs) manage their own commit cycle:

1. Middleware passes through without acquiring the lock.
2. The handler performs work in iterations. Between iterations, it calls a helper:

```python
await manager.commit_and_push()  # commits all dirty files, pushes
```

3. This helper acquires the write lock, commits everything dirty, pushes, and releases the lock. Between calls, the lock is free — other requests can proceed.

This is simpler than nested contexts — no context tracking, no lock handoff. Just "commit what's dirty and push."

**Parallel writes within a single request handler are not supported.** This is not a new limitation — concurrent filesystem writes within a single handler are already unsafe regardless of git sync. Use sequential iteration.

## Background Sync

A background async task keeps the local repo fresh by polling for remote changes.

- Runs only when auto mode is enabled for at least one project in the repo.
- **Two-phase approach:**
  1. **Fetch (no lock):** `git fetch` updates remote tracking refs only — doesn't touch the working tree. Safe to run concurrently with anything.
  2. **Check:** Compare local HEAD against fetched remote tracking ref. If no new commits, done.
  3. **Fast-forward (with lock):** Acquire the write lock (blocking — waits behind in-flight requests). Update the working tree to match fetched state. Release lock.
- Poll interval: 10 seconds (internal constant).
- **Idle pause:** Stops polling after 5 minutes with no API requests. Resumes on next request.
- On pull failure (network): logs warning, retries on next poll.

## Conflict Handling

### Strategy: Rebase-Only

All pulls use rebase. No merge commits. This keeps history linear and is simpler to reason about.

### Conflict During Push

When push fails because remote has diverged:

1. Fetch remote.
2. Rebase the local commit directly onto the fetched remote HEAD (commit stays intact — no revert needed).
3. If rebase succeeds cleanly → push again (once). If second push also fails → rollback to pre-request state → return error.
4. If rebase conflicts → `git rebase --abort` → rollback to pre-request state → return error.

The client receives a 409 error. The user's action: retry the operation (which will now be based on fresh data).

### Why Conflicts Are Rare

- Data model is append-only and immutable for most operations (new runs, new documents, etc.)
- Files use unique IDs in paths — two users creating items won't touch the same files
- The background poller keeps local state within seconds of remote
- Isolated repo eliminates local interference

## Rollback

On error (exception during handler, or push failure after retry exhausted):

1. `git stash -u -m "[Kiln] Rollback: <error description>"` — captures all dirty state (modified + untracked files) into a recoverable stash.
2. If a commit was made but not pushed: reset branch to pre-request HEAD (captured at lock acquisition time). Orphaned commit remains in reflog.
3. Release write lock.
4. Re-raise exception / return error.

Using `git stash` preserves dirty state recoverably — a technical user can inspect with `git stash list` and recover with `git stash pop` if needed. Nothing is silently destroyed.

## Recovery (Crash Recovery)

If the process crashes mid-operation (OOM, power loss, kill), the repo may be left in a dirty state. A recovery routine runs at the start of every write request (after lock acquisition, before ensure-fresh):

1. **Detect:** Check repo state — `git status` clean, no in-progress rebase/merge.
2. **Wait and recheck:** If dirty, sleep 0.5s then recheck. Another process or manager instance may be mid-operation and about to clean up.
3. **Still dirty → recover:**
   - Abort rebase/merge if in progress (`git rebase --abort`).
   - `git stash -u -m "[Kiln] Auto-recovery stash — dirty state from prior session"` to capture all dirty state into a recoverable stash.
   - If local branch has unpushed commits ahead of remote tracking branch: reset branch to remote tracking ref. Orphaned commits remain reachable via reflog.
4. **Log warnings** for every recovery action taken.

This ensures the system self-heals from crashes without requiring manual intervention from non-technical users.

## Commit Messages

Auto-generated from `git status` / `git diff` at commit time plus the API request path:

```
[Kiln] Auto-sync: 3 files changed

API: POST /api/projects/abc123/tasks
```

The first line summarizes file-level changes (new/modified/deleted, count, inferred model types from file paths). The body includes the API path for traceability in git history.

The commit message generator is purely programmatic — it uses `git diff` to determine change types and parses file paths and `.kiln` JSON content for model type and name fields. For deletions, the file list comes from `git status` since the files are already removed from the working tree.

## Configuration

### Per-Project Settings

- **sync_mode:** `"manual"` | `"auto"` (default: `"manual"`)
- **remote_name:** Git remote to sync with (default: `"origin"`)
- **branch:** Branch to sync (default: current branch at setup time)
- **clone_path:** Path to the isolated repo clone (set by setup flow)
- **credentials:** PAT token (per-project, stored securely)

### Where Configuration Lives

Stored in the existing Kiln config system. Not in git-tracked files (sync settings are per-machine, not shared).

### Internal Constants (not user-configurable)

- Poll interval: 10 seconds
- Idle pause: 5 minutes
- Sync freshness threshold: 15 seconds
- Git executor timeout: 20 seconds
- Long lock hold warning: 5 seconds (dev mode only)

## Error Handling

| Scenario | Behavior | User-Facing Error |
|----------|----------|-------------------|
| Remote unreachable on write | Rollback, fail request | 503: "Cannot sync with remote. Check your connection." |
| Remote unreachable on read | Fail request | 503: "Cannot sync with remote. Check your connection." |
| Push conflict | Rollback, fetch, rebase, retry once | 409: "Conflict detected. Please retry." |
| Rebase conflict (unresolvable) | Abort rebase, rollback | 500: "Sync conflict could not be auto-resolved. Disable auto-sync and resolve manually." |
| Write lock timeout (HTTP) | Fail request | 503: "Server busy. Please retry." |
| Dirty repo on write request | Auto-recovery via stash | Transparent — recovered automatically. Error only if recovery fails. |
| Corrupt repo state (unrecoverable) | Refuse to operate, surface error | 500: "Git repository is in an unexpected state. Disable auto-sync and check manually." |

## Setup Flow

### Phase 1 (Initial)

Manual configuration only. User provides repo path via config. Assumes the repo is already cloned, credentials configured, and single-purpose.

### Phase 2: UI-Driven Setup

Accessed via the Import Project UI with a new "Sync from Git" option. Wizard steps:

**Step 1: Provide Git URL**
- User enters repo URL (HTTPS or SSH).
- We attempt to access the repo via git API call (list branches — needed for next step).
- If access fails due to credentials → show credentials screen.

**Step 2: Credentials (shown on demand)**
- PAT token entry.
- For GitHub URLs, show a deeplink: [Get Token from GitHub](https://github.com/settings/tokens/new?scopes=repo&description=Kiln+AI&default_expires_at=none)
- For non-GitHub URLs, show a brief explainer of what a PAT is and where to find it.
- On save: test access with the provided token. Don't leave this screen unless the test succeeds.
- Token saved in memory during wizard, persisted to project-specific git config on final step.

**Credentials can be needed at multiple points:** It's possible to list branches successfully but fail on clone or push (different permission levels). The wizard supports jumping into the credentials flow at any failure point, adding/updating the PAT, and retrying the failed operation.

**Step 3: Branch Selection**
- List branches from the remote. Default selection: default branch > main > master.
- On confirm:
  1. Shallow clone of the selected branch into the hidden `.git-projects/` directory.
  2. Test write access: empty commit + push. Message: `"Empty commit: checking write access for Kiln AI Git Auto Sync setup"`
  3. If clone or push fails due to permissions → jump to credentials screen, retry.

**Step 4: Project Selection**
- Scan the cloned repo for all `project.kiln` files.
- If exactly one in repo root: auto-select, skip this step.
- If multiple: show a picker with paths + project names/descriptions loaded from the files.
- If none: show error ("No Kiln project found in this repository").

**Step 5: Complete**
- Save the project's git sync config (token, repo URL, clone path, branch, project path).
- Auto-sync is now enabled for this project.

### Phase 3 (Future, Not Part of This Project)

Create new project in git from UI. Rough sketch: select existing repo or "new repo" (git init + add remote), select subfolder or root, standard project creation wizard. Design TBD.

## Credentials

pygit2 will use a user's SSH keys if available.

- **Phase 1:** Manual config only. User handles credentials themselves.
- **Phase 2:** PAT token-based auth in the setup wizard. Per-project token storage (different projects may use different hosts/tokens).

## Out of Scope (V1 / Phase 1)

- **Setup wizard:** Phase 1 uses manual config. Phase 2 adds UI-driven setup.
- **Non-GitHub remotes:** Should work (pygit2 is provider-agnostic) but not explicitly tested in Phase 1.
- **Multi-remote sync:** Single remote only.
- **Branch management:** Syncs configured branch only. No branch creation/switching.
- **UI for conflict resolution:** If auto-resolve fails, user must resolve manually in git.
- **Offline mode:** No offline support. All writes require successful push. Reads also require freshness check.
- **Dirty repo resolution UX:** When enabling auto mode on a repo with uncommitted changes, Phase 1 requires the user to resolve this manually.

## Technical Constraints

- **Library:** pygit2 (libgit2 Python bindings). No shelling out to git CLI — users are non-technical.
- **Code location:** All git sync code lives in `app/desktop/` as a new sub-project. No changes to `libs/core/`.
- **Async compatibility:** The library must work with asyncio (FastAPI is async). Blocking git operations should run in a thread executor to avoid blocking the event loop.
- **Thread safety:** `GitSyncManager` must be thread-safe. The write lock must work across async tasks and threads.
- **pygit2 thread safety:** pygit2 objects (Repository, Index, etc.) are C extension objects backed by libgit2 and are not thread-safe. The `GitSyncManager` should funnel ALL pygit2 operations through a single-threaded executor to prevent concurrent libgit2 calls, which can cause segfaults.
- **Async runtime required:** Auto-sync requires the FastAPI middleware (async). Standalone sync callers outside the FastAPI server cannot use auto-sync mode.

## Integration with Existing Code

### No Changes to libs/core/

Design B requires zero modifications to `KilnBaseModel` or any code in `libs/core/`. The middleware handles git operations at the HTTP layer. File I/O happens exactly as it does today — the git sync system observes changes via `git status` after the fact.

### FastAPI Middleware

New middleware wraps mutating requests with the write lock, clean-state verification, ensure-fresh, and commit-on-exit. Added to the server stack in `app/desktop/`. Uses `BaseHTTPMiddleware` with response body buffering (allows commit/push failures to return error responses instead of silently failing after a 200). Raw ASGI middleware is the documented fallback if integration testing reveals issues with `BaseHTTPMiddleware`.

**Early integration test (blocking gate):** Before other git sync work proceeds, verify that `BaseHTTPMiddleware` correctly holds the lock across the request lifecycle and that response buffering works for error detection.

### Config System

Extended to store sync mode, credentials, and clone path per project.

## Documentation

A README must be created describing the feature. It should cover:

- How to configure a project for auto sync (Phase 1: manual config)
- How the middleware works and what it does automatically
- The `@write_lock` and `@no_write_lock` annotations
- Long-running request patterns with `commit_and_push()`
- Error handling and what each error means
- Dev-mode safety nets
