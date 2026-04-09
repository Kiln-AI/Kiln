---
status: draft
---

# Phase 5: Import Flow Unification & Git Sync UX

## Overview

Merge the "Sync from Git" wizard and "Import Project" local-file flow into a single "Import Project" entry point with method selection. Remove the `?import=true` query param hack. Make git import available during `/setup/` onboarding. Reduce Manage Projects from 3 action buttons to 2.

## Steps

1. **`git mv` step components to `$lib/components/import/`** -- Move `step_url.svelte`, `step_credentials.svelte`, `step_branch.svelte`, `step_project.svelte`, `step_complete.svelte` from `routes/(app)/settings/git_sync/` to `src/lib/components/import/`.

2. **Create `import_project.svelte`** at `$lib/components/import/import_project.svelte` (based on the old `+page.svelte` from git_sync). Changes:
   - Remove `AppPage` wrapper (caller provides layout)
   - Add `export let create_link: string` and `export let on_complete: (project_id: string) => void` props
   - Add `"method"` as new first step in `step_order`
   - Add method selection UI: two cards ("Import from Local File" and "Import from Git")
   - Add local file import logic (extracted from `edit_project.svelte`): file picker, manual path entry, POST `/api/import_project`
   - Wire `on_complete` into `step_complete` and local file import success paths

3. **Update `step_complete.svelte`** to accept and call `on_complete` callback instead of hardcoding `goto("/settings/manage_projects")`.

4. **Clean up `edit_project.svelte`**:
   - Remove `importing` state, `onMount` query param check
   - Remove `select_project_file()`, `import_project()`, `project_has_tasks()` functions
   - Remove `import_project_path`, `select_file_unavailable`, `show_select_file`, `import_submit_visible` variables
   - Remove import form UI (the `{:else}` block for `importing`)
   - Remove "Project Imported!" success state
   - Add `export let import_link: string` prop
   - Replace inline toggle with link to `import_link`

5. **Create `/settings/import_project/+page.svelte`** -- thin wrapper with AppPage, passes `create_link="/settings/create_project"` and `on_complete` that goes to manage_projects.

6. **Create `/setup/import_project/+page.svelte`** -- fullscreen setup layout wrapper, passes `create_link="/setup/create_project"` and `on_complete` with task-check logic (redirect to select_task or create_task).

7. **Update `/settings/create_project/+page.svelte`** to pass `import_link="/settings/import_project"` to `EditProject`.

8. **Update `/setup/create_project/+page.svelte`** to pass `import_link="/setup/import_project"` to `EditProject`.

9. **Update `manage_projects/+page.svelte`** -- reduce to 2 buttons: "Create Project" and "Import Project" (pointing to `/settings/import_project`).

10. **Delete `/settings/git_sync/` route directory** (empty after git mv).

11. **Update any remaining references** to old routes (`git_sync`, `?import=true`).

## Tests

- Existing `api.test.ts` tests should continue passing (API layer unchanged)
- Run `npm run check` to verify TypeScript/Svelte type checking catches missing props
- Run `npm run build` to verify build succeeds
- Run `npm run test_run` for existing test suite
- Manual verification: all routes render correctly, cross-links work, method selection step works
