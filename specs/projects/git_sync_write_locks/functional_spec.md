---
status: complete
---

# Functional Spec: Git Sync Write Locks

## Goal

Ensure every file write in the project happens inside a git sync write lock, so auto-sync reliably commits and pushes all changes. Today, 5 SSE endpoints write files outside any lock — their changes are silently lost on the next sync. Additionally, improve dev-mode detection so missing locks are caught during development, not production.

## Part 1: Add Write Locks to SSE Endpoints

### Endpoints That Need `@no_write_lock`

All 5 SSE endpoints write files but currently have no write lock. Each should use the `@no_write_lock` decorator and manage its own lock cycle per the pattern established in the git_auto_sync spec.

Note: endpoint #2 (`extract`) is POST, so the middleware would normally acquire the write lock for it. However, it still needs `@no_write_lock` because the middleware's write-lock path buffers the entire response body before committing — incompatible with SSE streaming. The middleware already detects this case and returns a 500 ("streaming endpoint missing @no_write_lock decorator"). All SSE endpoints need `@no_write_lock` regardless of HTTP method.

| # | Endpoint | File | HTTP | Writes |
|---|----------|------|------|--------|
| 1 | `/api/projects/{id}/extractor_configs/{id}/run_extractor_config` | `libs/server/kiln_server/document_api.py` | GET | Extractions |
| 2 | `/api/projects/{id}/documents/{id}/extract` | `libs/server/kiln_server/document_api.py` | POST | Extractions |
| 3 | `/api/projects/{id}/rag_configs/{id}/run` | `libs/server/kiln_server/document_api.py` | GET | Extractions, chunks, embeddings |
| 4 | `/api/projects/{id}/tasks/{id}/evals/{id}/eval_config/{id}/run_comparison` | `app/desktop/studio_server/eval_api.py` | GET | Eval runs |
| 5 | `/api/projects/{id}/tasks/{id}/evals/{id}/run_calibration` | `app/desktop/studio_server/eval_api.py` | GET | Eval runs |

### Lock Cycle Pattern

Each endpoint follows the batch pattern from the git_auto_sync functional spec:

```
for each unit of work (e.g., each document, each eval item):
    result = await expensive_computation()    # NO lock held
    async with manager.write_lock():
        await manager.ensure_clean()
        await manager.ensure_fresh()
        pre_head = await manager.get_head()
        save_result_to_file(result)           # write under lock
        if await manager.has_dirty_files():
            await manager.commit_and_push(api_path, pre_head)
```

On error within the lock scope, call `manager.rollback(pre_head)` before re-raising.

### Obtaining the Manager

SSE endpoints in `libs/server/` don't have direct access to the `GitSyncRegistry` (which lives in `app/desktop/`). The endpoint needs to obtain a `GitSyncManager` for its project.

The middleware already resolves the manager for each request via `_get_manager_for_request()`. For `@no_write_lock` endpoints, the middleware should attach the resolved manager (or `None` if git sync is not active for this project) to `request.state` so the endpoint can use it without importing desktop-layer code.

Endpoints should check if the manager is `None` (git sync not active) and skip the lock cycle entirely — just do the writes directly as they do today. This keeps the endpoints functional both with and without git sync.

### What Doesn't Need Changes

- **Finetune download** (`finetune_api.py`): Writes to a temp directory outside the repo. URL doesn't match the `/api/projects/{id}/` pattern so middleware ignores it. No action needed.
- **Background sync**: Already acquires write locks correctly.
- **Filesystem cache**: Writes to a temp directory, not the project repo. No action needed.
- **All POST/PATCH/PUT/DELETE non-SSE endpoints**: Already get write locks via middleware. No action needed.

## Part 2: Dev-Mode Dirty State Detection

### Problem

The current `ensure_clean()` crash recovery logs a minimal warning (`"Repo dirty on write request -- running crash recovery"`) that doesn't identify which request caused the dirty state. It only triggers on the *next* write request, which may be much later. This makes it hard to catch missing write locks during development.

### Dev-Mode Flag

Add a new `KILN_DEV_MODE` environment variable, set in `dev_server.py`. This is a dedicated flag for dev-mode safety nets, separate from the asyncio debug flag (`DEBUG_EVENT_LOOP`).

### Behavior: Post-Request Dirty Check

After every non-write-locked request completes (the read path in middleware), if dev mode is active:

1. Check `manager.has_dirty_files()`
2. If dirty, log a loud error:
   ```
   DEV MODE: Request left repo dirty without write lock!
     API: GET /api/projects/123/rag_configs/456/run
     Project: /path/to/project
     Dirty files: [list of dirty file paths]
   ```
3. Return a **500 error** instead of the normal response, with body:
   ```json
   {"detail": "Dev mode: this endpoint wrote files without holding a write lock. See server logs for details."}
   ```

This catches the problem immediately on the request that caused it, rather than silently recovering later.

### Why 500 (Not Breaking JSON)

A 500 is impossible to miss — it shows up in the browser network tab, the UI shows an error, and the developer sees it immediately. Breaking JSON output would only surface if the frontend happens to parse the response, and would produce confusing parse errors rather than a clear diagnostic message.

### Non-Dev Behavior

In production (non-dev mode), the existing `ensure_clean()` crash recovery continues to work as-is. No changes to production behavior.

### Scope of the Check

The dirty check only runs for requests that go through the middleware's read path (non-write-locked requests on projects with active git sync). Write-locked requests already commit their changes, so they don't need this check.

## Out of Scope

- Changing SSE endpoints from GET to POST (or vice versa) — the `@no_write_lock` pattern handles both correctly
- Modifying the `ensure_clean()` crash recovery behavior — it remains as a production safety net
- Adding dev-mode gating to the existing long-lock-hold warning (the TODO at middleware.py:122) — orthogonal improvement, not blocking
