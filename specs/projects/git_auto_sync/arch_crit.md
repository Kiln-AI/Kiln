# Architecture Critique — Git Auto Sync

Design review of `architecture.md` by a fresh-context CR agent. Findings below with severity, analysis, and suggested fixes.

## Critical (must fix)

### 1. ASGI middleware can't change response after it's sent

The middleware wraps `await self.app(scope, receive, send)` in `write_context`. But ASGI sends the response incrementally — `http.response.start` (status code + headers) first, then `http.response.body`. If the inner app sends a 200, then commit/push fails in `__aexit__`, the client already has a 200. Can't change it to a 409 or 503.

Worse: if the commit/push happens in `__aexit__`, any error there is invisible to the client — they already got a success response.

**Suggested fix:** Use a FastAPI dependency that yields a write_context instead of raw ASGI middleware. Commit/push happens before the response is serialized. This is also cleaner architecturally — dependencies integrate better with FastAPI's error handling.

### 2. Parent releasing lock for nested context lets background sync sneak in

From the architecture:
```python
if parent_ctx is not None and parent_ctx.holds_lock:
    self._write_lock.release()
    parent_ctx.holds_lock = False
```

Between the parent releasing the lock and the nested context's first write (which lazily acquires it), the lock is free. The background poller could grab the lock and do a `pull --rebase`, rewriting the working tree while the parent handler is mid-execution. The parent may have already READ data that is now different after the rebase.

The functional spec says "Between nested contexts, the lock is free — other API requests can proceed." But it doesn't account for background sync also proceeding and invalidating the parent's read state.

**Suggested fix:** Background sync should check for any active `write_context` (not just the lock) before polling. Or use a separate read/write lock mechanism where the presence of any active context blocks background sync.

### 3. Rollback of `delete_tree` is not addressed

`WriteContext` tracks `original_contents: dict[Path, bytes | None]` for rollback. For `write_file`, this captures the original file bytes. But `delete_tree` (called by `KilnBaseModel.delete()`) uses `shutil.rmtree()` which recursively deletes an entire directory tree. The per-file rollback strategy can't undo this — the deleted files aren't individually tracked.

**Suggested fix:** Use `git checkout` to restore deleted files on rollback (cleanest given we have git). Alternative: move directory to a temp location instead of deleting, restore on rollback. The git approach is simpler and doesn't require pre-deletion enumeration.

### 4. Sync callers can't enter `write_context` (it's async-only)

`write_context` is `@asynccontextmanager`. Third-party sync-only callers can't use `with manager.write_context():` — it requires `async with`. The architecture describes this as a "general-purpose library" but sync callers are locked out of context entry entirely.

The middleware (async) handles all API paths, so this doesn't affect our code. But if the library is truly general-purpose, sync callers need a way in.

**Suggested fix:** For V1, document that `write_context` is async-only and the middleware handles all API paths. This is acceptable — no sync callers exist today. A sync variant can be added later if needed.

## Moderate (should fix)

### 5. Registry `get_or_create_for_project` has TOCTOU race

```python
if repo_path not in cls._managers:
    manager = GitSyncManager(repo_path=repo_path)
    cls.register(repo_path, manager)
return cls._managers[repo_path]
```

No lock protects check-then-create. Two simultaneous requests for different projects in the same repo could create two `GitSyncManager` instances — each with its own write lock. Two managers for the same repo means no mutual exclusion, which means corrupt git state.

**Suggested fix:** Add a `threading.Lock` to the registry, or use `dict.setdefault` pattern.

### 6. `find_project_id_for_path` is hand-waved

The `resolve_writer` function calls `find_project_id_for_path(path)` — a load-bearing function that is completely unspecified. How does the system go from a file path like `/data/my_project/tasks/task_123/task.kiln` to a project_id? The data model doesn't embed project IDs in file paths (it uses names). This mapping is non-trivial and critical — if wrong, files get the wrong writer or silently bypass git sync.

Similarly, the middleware's `_extract_project_id(scope["path"])` extracts project_id from the URL. The exact mechanism is unspecified.

**Suggested fix:** Specify the exact mechanism. For URL extraction, it's straightforward (parse `/api/projects/{project_id}/...`). For path-to-project, likely walk up the directory tree looking for `project.kiln`, then read its ID. Both should be defined in the architecture, not left to the coding agent.

### 7. Push retry in nested scenarios doesn't track unpushed commits

The architecture says on parent exit: push all commits, and on failure, `git reset` to "the last pushed state." But some nested contexts may have already called `manager.push()` mid-loop (the periodic push pattern). The system needs to distinguish between already-pushed commits (safe) and unpushed commits (need rollback). The architecture doesn't specify how to track this.

**Suggested fix:** Record the remote HEAD SHA before the parent context's final push. On failure, reset to that SHA. This cleanly separates pushed vs. unpushed commits.

### 8. Out-of-band detection doesn't handle leftover staged files

If a previous request's `git add` succeeded but `git commit` failed, those files remain staged. Subsequent requests would see them as dirty files not in the tracked set, triggering `OutOfBandChangesError` and blocking all API calls until manually resolved.

**Suggested fix:** Specify that rollback also unstages any files that were staged during the failed context. Or make `_commit_context` stage-and-commit atomically (single `_run_git` call so failure leaves nothing staged).

### 9. `check_in_sync=True` on reads is overly strict

The middleware wraps ALL requests (including GETs) in `write_context(check_in_sync=True)`. Every read blocks if the repo is stale. If the remote is temporarily unreachable, ALL API calls fail with 503 — not just writes. A network blip makes the entire app unusable even for local-only reads.

**Suggested fix:** Use `check_in_sync=False` for read-only requests (GETs). Only enforce freshness on writes. The background poller keeps things reasonably fresh for reads. Slightly stale data is much better than a completely broken app.

### 10. `delete_tree` tracking needs pre-deletion enumeration

`GitSyncStorageWriter.delete_tree()` receives a directory path, but the manager needs to know which files were deleted for `git add` (to stage the deletions). The manager must enumerate directory contents BEFORE deleting. The architecture only shows the simple `write_file` tracking pattern and doesn't address this.

**Suggested fix:** Specify the `delete_tree` implementation with explicit pre-deletion enumeration and content capture. (May be partially resolved by #3's git-checkout approach to rollback, but staging still needs the file list.)

## Mild (consider fixing)

### 11. Naming deviation from functional spec not noted

The functional spec calls it `StorageBackend`, the architecture calls it `StorageWriter`. This is a valid refinement (write-only scope), but the architecture should explicitly note the deviation and why the name changed. A reader going from functional spec to architecture will be confused.

### 12. `notify_request()` may be called from wrong thread

`notify_request()` calls `asyncio.create_task()` which requires a running event loop on the current thread. If called from within `asyncio.to_thread`, this will fail. The middleware is async so it's fine, but the constraint should be documented.

**Suggested fix:** Document that `notify_request()` must be called from the event loop thread, or use `loop.call_soon_threadsafe`.

### 13. Commit messages for deletions need `original_contents`

The architecture says the commit message generator "reads the `.kiln` JSON files being committed." For deletions, those files are already gone. The `original_contents` dict has the bytes, which could be parsed for model type and name, but this isn't mentioned.

### 14. Config is an unvalidated dict

The git sync config is `ConfigProperty(dict)` — no schema validation. A typo like `sync_mode: "atuo"` silently falls back to manual mode (since it's not `"auto"`).

**Suggested fix:** Use a pydantic model for per-project git sync config, validated on read.

### 15. `_git_executor` ThreadPoolExecutor never shut down

The `GitSyncManager` creates a `ThreadPoolExecutor(max_workers=1)` but shows no shutdown logic. The executor thread leaks on app shutdown (not a daemon thread by default).

**Suggested fix:** Add executor shutdown to manager cleanup, called during FastAPI lifespan shutdown.

### 16. `manager.push()` doesn't enforce "not while write lock held"

The functional spec's error table says: "`manager.push()` while write lock is held → Immediate error." The architecture lists `push()` but doesn't show this enforcement. Needs to be explicit.

## Prioritization Notes

From the parent conversation:
- **#1** is a showstopper — the middleware approach as written can't work. FastAPI dependency is the right fix.
- **#9** is important for UX — network blip shouldn't break reads.
- **#2** is real but the window is tiny. Worth fixing.
- **#3/#10** — using git checkout for rollback is elegant and solves both.
- **#4** — fine to document as async-only for V1.
- **#6** — should spec this, it's non-trivial.
