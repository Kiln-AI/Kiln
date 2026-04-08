# Refinement: Mild Issue Fixes

## #11: Naming deviation — update functional spec

Update `functional_spec.md` to use `StorageWriter` instead of `StorageBackend`. The architecture narrowed scope to write-only, so `StorageWriter` is the correct name. Add a brief note in the functional spec explaining the rename.

## #13: Commit messages for deletions — use git status

Commit message generation is programmatic (no LLM). For deletions, use `git status` (or `repo.diff('HEAD')`) to get the list of removed files. Parse file paths to determine model type and name from the path structure (e.g. `tasks/my_task/task.kiln` → "task 'my_task'").

Do NOT use `original_contents` (deleted in refinement 01). Do NOT use an LLM — these are simple structured messages generated from git status output.

Format remains: `[Kiln] Delete <model_type> '<name>'`

## #14: Config validation — use pydantic model

Replace `ConfigProperty(dict)` with a pydantic model for per-project git sync config:

```python
class GitSyncProjectConfig(BaseModel):
    sync_mode: Literal["auto", "manual"] = "manual"
    remote_name: str = "origin"
```

**Note:** Verify that the existing `Config` class supports pydantic models as property types when updating the architecture spec. If not, may need a small adapter.

## #15: Executor shutdown

Add `_git_executor` shutdown to `GitSyncManager.close()`, called during FastAPI lifespan shutdown:

```python
async def close(self):
    self._git_executor.shutdown(wait=True)
```

Register cleanup via FastAPI lifespan or `atexit`.

## #16: push() enforces "not while write lock held"

`push()` should check that no write lock is held before proceeding. Simplest: attempt a non-blocking `acquire()` + immediate `release()` to verify the lock is free. Or check `ctx.holds_lock` on the active context:

```python
async def push(self):
    ctx = self._active_context.get()
    if ctx is not None and ctx.holds_lock:
        raise GitSyncError("Cannot push while write lock is held")
    ...
```
