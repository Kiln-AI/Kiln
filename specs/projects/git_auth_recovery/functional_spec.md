---
status: complete
---

# Functional Spec: Git Creds Error Recovery

## Problem

A user with a single Git-synced project hit an unrecoverable state when their Git
credentials expired:

1. **Misleading error**: The expired-token failure was reported as
   "Cannot sync with remote. Check your connection." — a connectivity message for
   an auth problem.
2. **Broken error display**: The task picker rendered `Tasks failed to load:
   [Object object]` (or "Unknown error") instead of the API's message string.
3. **No recovery path**: With one project the app redirects to `/setup/select_task`,
   which has no way to remove/re-import/re-auth a project, so the user was stuck.

This project delivers three coordinated fixes: correct the error shape, classify
auth failures distinctly, and add a re-import recovery path that works even from
the locked-out single-project state.

---

## Part A — Fix the task-picker error display

### Root cause

Kiln's app-wide error convention is `{"message": ...}`. The server's
`connect_custom_errors` handler (`libs/server/kiln_server/custom_errors.py`)
reshapes every `HTTPException` into `{"message": exc.detail}`, and the frontend
helper `createKilnError` (`app/web_ui/src/lib/utils/error_handlers.ts`) only reads
`message`.

`GitSyncMiddleware` runs **outside** the exception-handler chain (it returns a
`Response` directly), so its error bodies use FastAPI's raw `{"detail": ...}`
shape (`app/desktop/git_sync/middleware.py`). `createKilnError` can't read
`detail`, so it falls through to "Unknown error" (rendered as `[Object object]`
where the raw object is interpolated). The API string is correct; only the
**envelope shape** is wrong for this one code path.

### Behavior

- **All** JSON error responses emitted by `GitSyncMiddleware` use the
  `{"message": ...}` envelope (matching the app convention), not `{"detail": ...}`.
  This covers every error-return site in the middleware: the read-path sync error
  (both the `dispatch` read branch and the `_no_write_lock_asgi` branch), the
  write-path `GitSyncError` branch, the `_StreamingUnderWriteLock` branch, and the
  dev-mode dirty-check branches.
- After this change, `createKilnError` extracts the real message and the task
  picker shows e.g. "Tasks failed to load: Git authentication failed or expired…".
- **No frontend change** is required for the display fix. `createKilnError` is
  left as-is (we are not adding `detail` parsing); the fix is server-side only.

### Out of scope for Part A

- Hardening `createKilnError` to also parse FastAPI's native `{detail}` shape was
  considered and explicitly deferred. The middleware is the only path that emitted
  `{detail}`; fixing it at the source is sufficient.

---

## Part B — Distinguish auth failures from connectivity failures

### Root cause

`GitSyncManager.fetch()` wraps every `pygit2.GitError` — including HTTP 401/403
auth failures — as `RemoteUnreachableError`
(`app/desktop/git_sync/git_sync_manager.py`), which the middleware's `ERROR_MAP`
maps to "Cannot sync with remote. Check your connection." There is no auth-specific
error type today.

### Behavior

- Add a new error type `GitAuthError(GitSyncError)` in
  `app/desktop/git_sync/errors.py`.
- In `GitSyncManager.fetch()` (the read-sync path that produced the reported bug),
  when a `pygit2.GitError` is caught, **classify** it:
  - If the error indicates an authentication/authorization failure, raise
    `GitAuthError`.
  - Otherwise raise `RemoteUnreachableError` (unchanged behavior).
- Classification is **best-effort** by inspecting the pygit2 error (e.g. message
  containing any of: `401`, `403`, `authentication`, `authorization`,
  `unauthorized`, `credentials`, `too many redirects`/auth-replay). pygit2's error
  text is not a stable API, so when in doubt we fall back to
  `RemoteUnreachableError` (today's behavior) — we never make messaging *worse*.
- Add `GitAuthError` to the middleware `ERROR_MAP`:
  - Status: `401`.
  - Message: "Git authentication failed or expired. Re-import the project to
    reconnect with fresh credentials." (final wording may be tuned during
    implementation/UX review).
- Scope: only `fetch()` is required for this project (it is the read path behind
  the reported `/tasks` failure). The push path already has its own
  rebase/conflict handling; auth classification there is **out of scope** for now.

---

## Part C — Recovery via re-import (`remove_conflicting_id`)

The chosen recovery mechanism is **re-import only**: the user re-runs the import
flow (which collects fresh credentials), and when the duplicate-project-ID conflict
appears, a "Remove existing and re-sync" action removes the old project
registration and completes the import.

### C.1 Entry point — make the locked-out state recoverable

- `/setup/select_task` renders `SelectTasksMenu`
  (`app/web_ui/src/routes/(app)/select_tasks_menu.svelte`), which today offers only
  "+ New Project" and "+ New Task" — no import, remove, or settings access.
- When task loading fails, the picker's **error state** shows:
  - The corrected, accurate error message (from Parts A/B).
  - Directly **under** the error, a subtle recovery link — small, grey, low
    emphasis — reading "Re-import project?". It navigates to the **import flow**,
    landing on the **generic import method picker** (where the user chooses "Local
    Folder" vs "Git Auto Sync").
- The link is shown for **any** task-load error (it is the escape hatch from the
  lock-out point); we do not try to detect git-vs-local errors in the picker.
- `SelectTasksMenu` is used in two contexts with different chrome, so the import
  destination is passed in as a prop (mirroring the existing `new_project_url` /
  `new_task_url` props):
  - Setup (fullscreen) context → `/setup/import_project`.
  - In-app (sidebar dialog) context → `/settings/import_project`.
- The link appears only in the task-load **error state**. It is not added to the
  normal/healthy picker.

### C.2 Re-import flow (existing wizard, fresh creds)

- The recovery navigation lands on the import method picker. For a Git-synced
  broken project the user chooses **Git Auto Sync** and proceeds through the
  existing wizard: URL → credentials (**fresh PAT or OAuth here**) → branch →
  clone → project → complete.
- The wizard clones to a **new** directory; the old clone is untouched.
- Because the project ID is stored in `project.kiln` inside the repo, the
  re-imported project has the **same ID** as the broken one. Two consequences:
  1. The final `save_config` step hits the duplicate-ID conflict (see C.3).
  2. After successful recovery, the user's persisted selection
     (`ui_state.current_project_id`) still resolves — no dangling selection.

### C.3 Backend — `remove_conflicting_id` on save_config

Endpoint: `POST /api/git_sync/save_config`
(`app/desktop/git_sync/git_sync_api.py`).

- Add an optional field `remove_conflicting_id: bool = False` to
  `SaveConfigRequest`.
- Current behavior: `check_duplicate_project_id(...)` raises `DuplicateProjectError`
  → `HTTPException(409, detail=str(e))`.
- New behavior when `remove_conflicting_id` is `True` and a duplicate is detected:
  1. Remove the **existing** project that owns the conflicting ID
     (`request.project_id`), using the **same removal logic** as the Settings
     "Remove project" flow — i.e. the body of `delete_project` factored into a
     shared helper. Removal:
     - removes the project path from `Config.shared().projects`,
     - removes its `git_sync_projects` entry,
     - unregisters its `GitSyncManager` from `GitSyncRegistry`,
     - **does not delete any files from disk** (the old clone is left on disk).
  2. Proceed with the normal `save_config` (register the new clone, save config).
- Net effect: equivalent to two existing API calls (delete project + save config)
  performed atomically in one request. No new removal semantics are invented; the
  recovery path reuses the de-register-only behavior of `delete_project`.
- When `remove_conflicting_id` is `False` (default), behavior is unchanged
  (raises 409).
- The shared helper is also called by the existing `delete_project` endpoint so
  both paths share one implementation.

### C.4 Frontend — "Remove existing and re-sync" button

- The duplicate conflict surfaces in the wizard's final step
  (`app/web_ui/src/lib/components/import/step_complete.svelte`), currently shown as
  a "Setup Error" with only a "Back" button.
- When `saveConfig` fails with the duplicate-ID conflict (HTTP 409), the error view
  additionally shows a destructive-styled (red) **"Remove existing and re-sync"**
  button.
  - The red, explicitly-labeled button is itself the confirmation; no separate
    confirm dialog is required.
  - Clicking it re-invokes `saveConfig` with the same payload plus
    `remove_conflicting_id: true`.
  - On success, the flow proceeds to the normal "done" state and `on_complete`.
- "Back" remains available as a non-destructive alternative.
- The `saveConfig` API wrapper (`app/web_ui/src/lib/git_sync/api.ts`) and generated
  OpenAPI bindings are updated to carry the new optional field.

### C.5 Local-folder import parity (separate phase)

The recovery navigation lands on the generic method picker, so a user may choose
"Local Folder" instead of "Git Auto Sync". Local import must therefore support the
same recovery, built as a **separate implementation phase** after the Git path.

- Endpoint: `POST /api/import_project`
  (`libs/server/kiln_server/project_api.py`). Add an optional
  `remove_conflicting_id: bool = False` query parameter. When true and
  `check_duplicate_project_id` finds a same-ID duplicate, remove the conflicting
  project via the **same shared helper** used by the Git path (de-register only,
  files left on disk), then add the project. Default false → unchanged 409.
- Frontend: the local-file step in
  `app/web_ui/src/lib/components/import/import_project.svelte` (the
  `current_step === "local_file"` branch / `import_project` function) shows the same
  red **"Remove existing and re-sync"** action on a 409 duplicate, retrying the
  POST with `remove_conflicting_id=true`.
- Same edge-case handling as C.3 (`same_path` benign re-register; flag is a no-op
  when there's no conflict).

---

## API contract changes

| Endpoint | Change |
|---|---|
| `POST /api/git_sync/save_config` | `SaveConfigRequest` gains optional `remove_conflicting_id: bool = False`. When true and a same-ID-different-path duplicate exists, the conflicting project is de-registered (files left on disk) before saving. |
| `POST /api/import_project` | Gains optional `remove_conflicting_id: bool = False` query param with the same semantics (local-folder parity; separate phase). |
| `GitSyncMiddleware` error responses | Envelope changes from `{"detail": ...}` to `{"message": ...}` for all error bodies. Status codes unchanged except the new auth case. |
| Git sync read errors (via middleware) | New `GitAuthError` → HTTP **401** with an auth-specific message. Existing `RemoteUnreachableError` (503), `SyncConflictError` (409), `WriteLockTimeoutError` (503), `CorruptRepoError` (500) unchanged. |

No change to `DELETE /api/delete_project/{project_id}`'s external contract; its
implementation is refactored to share a helper with the recovery path.

---

## Edge cases & error handling

- **Auth classification false negative**: if a real auth failure isn't recognized,
  it falls back to `RemoteUnreachableError` (today's behavior). No regression.
- **Auth classification false positive**: a connectivity error mis-tagged as auth
  would point the user at re-import; re-import re-runs credential entry and a fresh
  clone, which still recovers most states, so the downside is limited.
- **`remove_conflicting_id` with no actual conflict**: the duplicate check simply
  doesn't fire; the flag is a no-op and save proceeds normally.
- **`same_path` duplicate** ("This project is already imported"): does not occur in
  the recovery flow because re-import always clones to a fresh path. If it somehow
  occurs, removing the existing same-path registration and re-adding the same path
  is a benign re-register.
- **Stale selection after recovery**: preserved, because the re-imported project
  keeps its original ID (see C.2).
- **Orphaned old clone on disk**: intentional — consistent with `delete_project`'s
  "does not delete files" guarantee; avoids any risk of discarding unpushed local
  commits.

---

## Out of scope

- **Re-authenticate in place** from the task picker (reusing the existing "Update
  Auth" UI in `git_sync_status.svelte`). Considered; the chosen recovery is
  re-import only.
- **Auth-error classification on the push path.** Only the read/`fetch` path is in
  scope.
- **General settings/manage-projects navigation** from the fullscreen setup flow.
  Recovery is handled by the inline error-state affordance instead.
- **Hardening `createKilnError`** to parse FastAPI `{detail}`.

---

## Testing considerations

- **Backend**
  - Middleware error bodies use `{"message": ...}` for each error branch.
  - `fetch()` classifies representative auth-failure pygit2 errors as
    `GitAuthError` and non-auth errors as `RemoteUnreachableError`; `ERROR_MAP`
    maps `GitAuthError` → 401 + message.
  - `save_config` with `remove_conflicting_id=true` removes the conflicting
    project (via the shared helper) and succeeds; with the flag false it still
    returns 409. Verify the old project is de-registered and files remain on disk.
  - `import_project` (local) with `remove_conflicting_id=true` behaves the same via
    the shared helper (separate phase).
  - `delete_project` still works through the shared helper (no behavior change).
- **Frontend**
  - Task-picker error state shows the real message and the subtle "Re-import
    project?" link, with the correct destination per context (setup vs app).
  - `step_complete.svelte` shows "Remove existing and re-sync" on a 409 and retries
    with `remove_conflicting_id: true`, reaching the done state on success.
  - Local-file import step shows the same "Remove existing and re-sync" action on a
    409 and retries with `remove_conflicting_id=true` (separate phase).
- **Checks**: OpenAPI bindings regenerated; lint/format/typecheck/tests pass for
  both Python and web.
