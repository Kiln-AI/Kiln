---
status: complete
---


# Phase 4: Local-Folder Import Parity

## Overview

Adds `remove_conflicting_id` support to the local-folder import path (`POST /api/import_project`) and a corresponding red recovery button in the `import_project.svelte` UI, so that local-folder re-import works the same as the Git re-import path added in Phases 2-3.

## Steps

1. **Backend: Add `remove_conflicting_id` query param to `POST /api/import_project`** (`libs/server/kiln_server/project_api.py`)
   - Add optional `remove_conflicting_id: bool = False` query parameter to the `import_project` endpoint.
   - Import `remove_project_from_config` from `kiln_ai.utils.project_utils` and `project_from_id` (core version).
   - When `DuplicateProjectError` is caught and `remove_conflicting_id` is true, resolve the conflicting project via `project_from_id_core(project.id)`, call `remove_project_from_config(str(conflicting.path))`, then proceed with `add_project_to_config`. Add a code comment noting the layering caveat (libs/server cannot unregister the in-memory GitSyncRegistry manager).
   - When `remove_conflicting_id` is false (default), raise 409 as before.

2. **Regenerate OpenAPI bindings** using `generate_schema` after the backend change.

3. **Frontend: Add conflict recovery button to `import_project.svelte`** (`app/web_ui/src/lib/components/import/import_project.svelte`)
   - Add `let import_conflict = false` state variable.
   - In the `import_project` function, after catching an error, detect 409 from `response` and set `import_conflict = true`.
   - Refactor `import_project` to accept a `remove_conflicting_id` boolean parameter, passing it as a query param when true.
   - In the `local_file` template section, when `import_conflict` is true, show a red `btn btn-error btn-outline` button labeled "Remove existing and re-import" that retries with `remove_conflicting_id: true`.

4. **Backend tests** (`libs/server/kiln_server/test_project_api.py`)
   - `test_import_project_duplicate_remove_conflicting_id_success`: with `remove_conflicting_id=true`, resolves and removes the conflicting project, then succeeds.
   - `test_import_project_duplicate_remove_conflicting_id_no_conflict`: flag is true but no duplicate exists; import succeeds normally.

5. **Frontend tests** (new file: `app/web_ui/src/lib/components/import/import_project.test.ts`)
   - Test that 409 response shows the conflict button.
   - Test that clicking the conflict button retries with `remove_conflicting_id=true`.
   - Test that non-409 errors do not show the conflict button.

## Tests

- `test_import_project_duplicate_remove_conflicting_id_success`: verifies that with flag=true a duplicate is resolved and import succeeds
- `test_import_project_duplicate_remove_conflicting_id_no_conflict`: verifies flag is no-op when no conflict
- Frontend: 409 renders "Remove existing and re-import" button; click retries with flag; non-409 does not show button
