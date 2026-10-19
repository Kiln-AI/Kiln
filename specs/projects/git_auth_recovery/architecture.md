---
status: complete
---

# Architecture: Git Creds Error Recovery

Single architecture doc (no separate component designs). The change is localized to
a handful of files across the git-sync middleware/manager, two API endpoints, and
two small frontend affordances.

## Layering note (important)

Three layers are involved, and dependencies only flow downward:

- `libs/core` (`kiln_ai`) — persistent config (`Config`: `projects` list,
  `git_sync_projects` dict) and project utils. Knows nothing about runtime managers.
- `libs/server` (`kiln_server`) — core REST API, including
  `POST /api/import_project` and the `custom_errors` handlers.
- `app/desktop` (`git_sync`) — the git-sync middleware, `GitSyncManager`,
  `GitSyncRegistry` (in-memory managers + background sync), and the git-sync API
  (`save_config`, `delete_project`).

Consequence: the **persistent-config** part of "remove a project" lives in
`libs/core` so both `libs/server` (local import) and `app/desktop` (git save_config,
delete_project) can call it. The **runtime-registry teardown** part is an
`app/desktop` wrapper layered on top. See "Shared removal helper" below.

---

## Part A — Middleware error envelope

**File:** `app/desktop/git_sync/middleware.py`

Every JSON error `Response` the middleware constructs currently uses
`{"detail": message}`. Change all of them to `{"message": message}` to match the
app-wide convention enforced by `libs/server/kiln_server/custom_errors.py`
(`http_exception_handler` emits `{"message": exc.detail}`). The middleware bypasses
that handler (it returns `Response` objects directly), which is why it must self-apply
the convention.

Sites to change (all `json.dumps({"detail": ...})` → `{"message": ...}`):

1. `_no_write_lock_asgi` read-sync error (~L112-116)
2. `dispatch` read-path sync error (~L158-162)
3. `_StreamingUnderWriteLock` branch (~L217-226)
4. write-path `GitSyncError` branch (~L228-233)
5. dev-mode dirty-check 500 (~L268-279)
6. `_unmatched_dispatch` dev-mode 500 (~L318-329)

No status codes change here. No frontend change: `createKilnError`
(`error_handlers.ts`) already reads `message`.

---

## Part B — Distinct auth error (`GitAuthError`)

### B.1 New error type

**File:** `app/desktop/git_sync/errors.py`

```python
class GitAuthError(GitSyncError):
    """Git authentication failed or expired (bad/expired token, 401/403)."""
```

### B.2 Classify in `fetch()`

**File:** `app/desktop/git_sync/git_sync_manager.py`

Add a module-level best-effort classifier and use it in `fetch()`:

```python
_AUTH_ERROR_MARKERS = (
    "authentication",
    "authoriz",          # authorization / unauthorized
    "credential",
    "401",
    "403",
    "too many redirects",
    "invalid username or password",
    "password authentication",
)

def _is_auth_error(e: Exception) -> bool:
    msg = str(e).lower()
    return any(marker in msg for marker in _AUTH_ERROR_MARKERS)
```

```python
async def fetch(self) -> None:
    try:
        await self._run_git(self._fetch_sync)
    except pygit2.GitError as e:
        if _is_auth_error(e):
            raise GitAuthError(f"Git authentication failed: {e}") from e
        raise RemoteUnreachableError(f"Cannot sync with remote: {e}") from e
```

pygit2's error text is not a stable API; when markers don't match we fall back to
`RemoteUnreachableError` (today's behavior) — classification never makes messaging
worse. The `asyncio.TimeoutError` path in `_run_git` continues to raise
`RemoteUnreachableError` (a genuine timeout, not auth).

### B.3 Let `GitAuthError` propagate (critical)

`ensure_fresh()` and `ensure_fresh_for_read()` currently wrap any non-
`RemoteUnreachableError` exception from `fetch()` back into `RemoteUnreachableError`:

```python
try:
    await self.fetch()
except RemoteUnreachableError:
    raise
except Exception as e:
    raise RemoteUnreachableError(f"Cannot sync with remote: {e}") from e
```

Since `GitAuthError` is a `GitSyncError` (not a `RemoteUnreachableError`), it would be
silently re-wrapped and the classification lost. Change both methods' first `except`
to the base class so any `GitSyncError` propagates unchanged:

```python
except GitSyncError:
    raise
```

Update the imports in `git_sync_manager.py` to include `GitAuthError` and
`GitSyncError`.

### B.4 Map in middleware

**File:** `app/desktop/git_sync/middleware.py` — add to `ERROR_MAP`:

```python
GitAuthError: (
    401,
    "Git authentication failed or expired. Re-import the project to "
    "reconnect with fresh credentials.",
),
```

`GitAuthError` is a sibling of the other mapped types (no subclass ordering issue in
`_map_error`'s `isinstance` scan). Import `GitAuthError` in the middleware.

Effect: a git-synced read (`GET /api/projects/{id}/tasks`) with expired creds now
returns `401 {"message": "Git authentication failed or expired. …"}`, which the task
picker renders verbatim. Mutating requests through `atomic_write` also surface it via
the existing write-path `except GitSyncError` branch — a free, consistent bonus.
(Push-failure auth classification inside `commit_and_push` remains out of scope.)

---

## Part C — Re-import recovery

### C.1 Shared removal helper (config layer + registry layer)

**Core (config) — `libs/core/kiln_ai/utils/project_utils.py`:**

```python
def remove_project_from_config(project_path: str) -> str | None:
    """Remove a project from Kiln config. Does NOT delete files from disk.

    Returns the git-sync clone_path if the project was git-synced, else None.
    """
    projects = Config.shared().projects or []
    Config.shared().save_setting(
        "projects", [p for p in projects if p != project_path]
    )

    git_sync = Config.shared().git_sync_projects or {}
    clone_path = None
    if project_path in git_sync:
        clone_path = git_sync[project_path].get("clone_path")
        git_sync.pop(project_path)
        Config.shared().save_setting("git_sync_projects", git_sync)
    return clone_path
```

This is exactly the persistent-config portion of today's `delete_project`.

**App (registry) — `app/desktop/git_sync/git_sync_api.py`:**

```python
async def _deregister_project(project_path: str) -> None:
    clone_path = remove_project_from_config(project_path)
    if clone_path is not None:
        await GitSyncRegistry.unregister(Path(clone_path))
```

Refactor `delete_project` to use it:

```python
project = project_from_id(project_id)
# (existing not-found handling preserved)
await _deregister_project(str(project.path))
return {"message": f"Project removed. ID: {project_id}"}
```

### C.2 `remove_conflicting_id` on git `save_config`

**File:** `app/desktop/git_sync/git_sync_api.py`

- Add `remove_conflicting_id: bool = False` to `SaveConfigRequest`.
- In `api_save_config`, change the duplicate handling:

```python
try:
    check_duplicate_project_id(request.project_id, full_project_path)
except DuplicateProjectError as e:
    if not request.remove_conflicting_id:
        raise HTTPException(status_code=409, detail=str(e))
    conflicting = project_from_id(request.project_id)
    if conflicting is not None:
        await _deregister_project(str(conflicting.path))
    # fall through to save the new clone
```

The conflicting project shares `request.project_id` (that's why it conflicts), so
`project_from_id(request.project_id)` resolves it. After de-registration the
subsequent `save_git_sync_config` + `add_project_to_config` register the new clone.
Files for the old clone remain on disk (intentional). Behavior with the flag `False`
is unchanged (409).

Import `project_from_id` and `remove_project_from_config` as needed.

### C.3 Local `import_project` parity (Phase 4)

**File:** `libs/server/kiln_server/project_api.py`

- Add `remove_conflicting_id: bool = False` query parameter to the
  `POST /api/import_project` endpoint.
- On `DuplicateProjectError` with the flag set, call the **core** helper
  `remove_project_from_config(str(conflicting.path))` (resolved via
  `project_from_id(project.id)`), then proceed with `add_project_to_config`.

Layering caveat: `libs/server` cannot call `GitSyncRegistry.unregister` (app layer).
If the removed conflicting project happened to be git-synced *and* had a live manager
this session, its in-memory manager/background-sync lingers until restart. This is a
rare edge for local-folder import and is acceptable; document it in a code comment.
(The git path in C.2 does full registry teardown.)

### C.4 Frontend — task-picker recovery link

**File:** `app/web_ui/src/routes/(app)/select_tasks_menu.svelte`

- Add an export prop `import_project_url: string` (default e.g.
  `/settings/import_project`), alongside the existing `new_project_url` /
  `new_task_url`.
- In the task-load **error state** block (currently the "Error" panel), render the
  accurate `tasks_loading_error` message and, directly beneath it, a subtle link:

```svelte
<a href={import_project_url} class="text-xs text-base-content/40 hover:underline mt-1">
  Re-import project?
</a>
```

  Small, grey, low-emphasis. Shown for any task-load error.

**File:** `app/web_ui/src/routes/(fullscreen)/setup/(setup)/select_task/+page.svelte`

- Pass `import_project_url="/setup/import_project"` to `SelectTasksMenu` (the
  fullscreen setup context). The in-app sidebar usage keeps the default
  `/settings/import_project`.

The recovery link lands the user on the generic import method picker, where they pick
"Git Auto Sync" (fresh creds) or "Local Folder". `handle_complete` in
`/setup/import_project/+page.svelte` already routes back to `select_task` afterward;
with fresh creds the task load now succeeds.

### C.5 Frontend — git wizard "Remove existing and re-sync"

**File:** `app/web_ui/src/lib/git_sync/api.ts`

The hand-rolled `request()` helper throws a bare `Error` with no status. Give it a
typed error so callers can detect the 409 conflict (mirroring `is_stale_clone_error`):

```ts
export class GitSyncRequestError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = "GitSyncRequestError"
    this.status = status
  }
}

export function is_duplicate_project_error(e: unknown): boolean {
  return e instanceof GitSyncRequestError && e.status === 409
}
```

In `request()`, throw `new GitSyncRequestError(msg, resp.status)` instead of
`new Error(msg)`. Existing callers (which read `.message`) are unaffected — it's an
`Error` subclass. Add `remove_conflicting_id?: boolean` to `saveConfig`'s config
type so it passes through in the POST body.

**File:** `app/web_ui/src/lib/components/import/step_complete.svelte`

- Extract the save call into `async function run_save(remove_conflicting_id = false)`
  that calls `saveConfig({ ...payload, remove_conflicting_id })` using the
  already-renamed `clone_path`. `onMount` runs `renameClone` once, then
  `run_save(false)`. (Rename must not re-run on retry.)
- Track `let is_conflict = false`. In the catch: keep the existing
  `is_stale_clone_error` branch; then set
  `is_conflict = is_duplicate_project_error(e)` and `error = createKilnError(e)`.
- In the error view, when `is_conflict`, additionally show a destructive (red) button
  "Remove existing and re-sync" that calls `run_save(true)` (resetting `saving`,
  `error`, `is_conflict`). The red, explicitly-labeled button is the confirmation; no
  dialog. "Back" remains.

### C.6 Frontend — local import "Remove existing and re-import" (Phase 4)

**File:** `app/web_ui/src/lib/components/import/import_project.svelte`

The local-file path uses the openapi-fetch `client.POST`, which exposes `response`:

```ts
const { data, error: post_error, response } = await client.POST(
  "/api/import_project",
  { params: { query: { project_path: import_project_path, ...(retry && { remove_conflicting_id: true }) } } },
)
```

- Track `let import_conflict = false`; set it from `response?.status === 409` on error.
- When `import_conflict`, show a red "Remove existing and re-import" button that
  re-issues the POST with `remove_conflicting_id: true`.

---

## Error handling strategy

- Auth misclassification: false negative → falls back to today's
  `RemoteUnreachableError` (no regression); false positive → user is routed to
  re-import, which still recovers most states.
- `remove_conflicting_id` is a no-op when no duplicate exists; idempotent (removing an
  already-absent path is harmless).
- `same_path` duplicates don't arise in re-import (fresh clone path); if they did,
  de-register + re-add the same path is benign.
- Recovery preserves the project ID (stored in `project.kiln`), so
  `ui_state.current_project_id` still resolves post-recovery.

## Testing strategy

Frameworks: pytest (Python), vitest/`@testing-library/svelte` (web).

**Python**
- `middleware`: each error branch returns `{"message": ...}` (update existing
  assertions that check `detail`); `GitAuthError` → 401 + message via `ERROR_MAP`.
- `git_sync_manager`: `fetch()` raises `GitAuthError` for auth-marker `pygit2.GitError`
  and `RemoteUnreachableError` otherwise; `ensure_fresh_for_read` propagates
  `GitAuthError` unchanged (regression guard for the re-wrap bug).
- `project_utils`: `remove_project_from_config` removes the path and git_sync entry,
  returns `clone_path`, idempotent on a missing path.
- `git_sync_api`: `save_config` with `remove_conflicting_id=true` de-registers the
  conflict (files remain on disk) and succeeds; `false` still 409; `delete_project`
  unchanged via the shared helper.
- `project_api`: `import_project` with `remove_conflicting_id=true` (Phase 4).

**Web**
- `select_tasks_menu`: error state renders the message + the "Re-import project?" link
  with the correct `import_project_url` per context.
- `api.ts`: `is_duplicate_project_error` true only for status-409 `GitSyncRequestError`.
- `step_complete`: 409 shows "Remove existing and re-sync"; retry calls `saveConfig`
  with the flag and reaches `done`.
- `import_project` local step: 409 shows "Remove existing and re-import" and retries
  with the flag (Phase 4).

**Checks:** regenerate OpenAPI bindings (`generate_schema.sh`) after the request-model
changes; run full Python + web lint/format/typecheck/test/build.
