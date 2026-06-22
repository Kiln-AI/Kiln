---
status: complete
---

# Phase 3: Recovery UI (Frontend)

## Overview

Adds the frontend recovery affordances for git auth errors and duplicate-project
conflicts. Three coordinated changes: (1) a subtle "Re-import project?" link in
the task picker's error state, (2) typed error handling in the git sync API
client, and (3) a "Remove existing and re-sync" destructive button in the import
wizard's final step when a duplicate-project conflict (409) is detected.

## Steps

### 1. Regenerate OpenAPI bindings

Phase 2 added `remove_conflicting_id` to `SaveConfigRequest`, so the TS bindings
are stale. Run `generate_schema` and verify `check_schema` passes.

### 2. Add `GitSyncRequestError` class and helpers to `api.ts`

File: `app/web_ui/src/lib/git_sync/api.ts`

- Add `GitSyncRequestError extends Error` with a `status: number` field.
- Add `is_duplicate_project_error(e: unknown): boolean` (checks `e instanceof
  GitSyncRequestError && e.status === 409`).
- In the `request()` helper, throw `GitSyncRequestError(msg, resp.status)` instead
  of `Error(msg)`. Existing callers read `.message`, so they are unaffected.
- Add `remove_conflicting_id?: boolean` to the `saveConfig` config parameter type.

### 3. Add `import_project_url` prop and recovery link to `select_tasks_menu.svelte`

File: `app/web_ui/src/routes/(app)/select_tasks_menu.svelte`

- Add `export let import_project_url = "/settings/import_project"`.
- In the error state block (the `{:else if tasks_loading_error}` branch), beneath
  the error message text, add:
  ```svelte
  <a href={import_project_url} class="text-xs text-base-content/40 hover:underline mt-1">
    Re-import project?
  </a>
  ```
  Small, grey, low-emphasis. Dispatches `dismiss` on click (for the dialog context).

### 4. Wire `import_project_url` in the setup context

File: `app/web_ui/src/routes/(fullscreen)/setup/(setup)/select_task/+page.svelte`

- Pass `import_project_url="/setup/import_project"` to `SelectTasksMenu`.

### 5. Refactor `step_complete.svelte` for conflict recovery

File: `app/web_ui/src/lib/components/import/step_complete.svelte`

- Import `is_duplicate_project_error` from the api module.
- Add `let is_conflict = false` state.
- Extract the save call into `async function run_save(remove_conflicting_id = false)`.
  `onMount` calls `renameClone` once, then `run_save(false)`. The rename must not
  re-run on retry.
- In the catch block: check `is_stale_clone_error` first, then set
  `is_conflict = is_duplicate_project_error(e)` and `error = createKilnError(e)`.
- In the error view, when `is_conflict`, show a red "Remove existing and re-sync"
  button that calls `run_save(true)` (resetting `saving`, `error`, `is_conflict`).
  "Back" remains available.

## Tests

- **api.test.ts — GitSyncRequestError**: verify `request()` throws
  `GitSyncRequestError` with correct status on non-ok response.
- **api.test.ts — is_duplicate_project_error**: true for 409
  `GitSyncRequestError`, false for other statuses, false for plain `Error`.
- **api.test.ts — saveConfig with remove_conflicting_id**: verify the field is
  sent in the POST body when provided.
- **select_tasks_menu.svelte — error state link**: render with a mock error, verify
  the "Re-import project?" link is present with the correct href, and that the
  custom `import_project_url` prop overrides the default.
- **step_complete.svelte — conflict button**: mock `saveConfig` to reject with a
  409 `GitSyncRequestError`, verify the "Remove existing and re-sync" button
  appears, click it, verify `saveConfig` is retried with
  `remove_conflicting_id: true`.
