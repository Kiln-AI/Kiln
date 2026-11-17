---
status: complete
---

# Phase 3: Entry Points

## Overview

The Experiment Lineage page exists but nothing links to it. This phase adds the three entry points from the functional spec: a header button and a row menu item on the Optimize page, and an AppPage action button on the Compare page. All three build their URL with `experiment_lineage_link` from `lib/utils/link_builder.ts`, which phase 1 added and tested. It adds page tests for the Optimize and Compare pages that pin each entry point, and runs docs-sync to fix the stale statements in the project's spec docs.

All paths below are relative to `app/web_ui/src/`.

## Steps

1. **`routes/(app)/optimize/[project_id]/[task_id]/+page.svelte`** (edit).
   - Import `experiment_lineage_link` alongside `tool_link` from `$lib/utils/link_builder`.
   - In the Run Configurations header, inside the `{:else}` (not select mode) branch, add before "Compare":

     ```svelte
     <button
       class="btn btn-mid"
       on:click={() => goto(experiment_lineage_link(project_id, task_id))}
     >
       Experiment Lineage
     </button>
     ```

   - In each row's `TableActionMenu`, add after "Set as Task Default":

     ```ts
     {
       label: "Show in Experiment Lineage",
       onclick: () => goto(experiment_lineage_link(project_id, task_id, config.id)),
     },
     ```

     If the label wraps at the menu's current `w-56`, widen the menu so every item stays on one line.

2. **`routes/(app)/specs/[project_id]/[task_id]/compare/+page.svelte`** (edit).
   - Import `experiment_lineage_link` alongside `prompt_link`.
   - Pass to `AppPage`:

     ```svelte
     action_buttons={[
       { label: "Experiment Lineage", href: experiment_lineage_link(project_id, task_id) },
     ]}
     ```

3. **Test stubs.** `routes/(app)/optimize/[project_id]/[task_id]/__tests__/create_run_config_dialog_stub.svelte`: a stand-in for `CreateNewRunConfigDialog` with the same props and no-op `show`, `showClone` and `close`, so the Optimize page test doesn't mount the run config picker. The Compare page test stubs its heavy child components the same way if they don't mount in jsdom.

4. **docs-sync.** Run the repo's `docs-sync` skill over the branch. Known fixes in `specs/projects/experiments_page/architecture.md`:
   - `ChangeKind` and `CHANGE_KINDS` are defined in `lineage_changes.ts` and re-exported from `lineage_graph.ts`.
   - With nothing selected, an arrow key picks the oldest starting point, falling back to `layout.rows[0][0]`.

   Fix any other stale statement the skill finds. The doc edits are left uncommitted with the phase.

5. **Visual check.** Extend the phase 2 mocked API if needed, open the Optimize page and the Compare page in Chromium, and screenshot the header row, the open row menu, and the Compare header. Confirm each entry point opens the lineage page, and that the row item selects its run config.

## Tests

- `routes/(app)/optimize/[project_id]/[task_id]/page.test.ts` (new, jsdom, stores partially mocked):
  - The Run Configurations header shows "Experiment Lineage" before "Compare", and clicking it calls `goto("/optimize/proj1/task1/experiment_lineage")`.
  - After "Compare" turns on select mode, "Experiment Lineage" is gone; after "Cancel Selection" it is back.
  - Opening a row's menu shows "Show in Experiment Lineage" after "Set as Task Default", and clicking it calls `goto` with `?selected=<that run config's id>`.
- `routes/(app)/specs/[project_id]/[task_id]/compare/page.test.ts` (new, jsdom, loads left pending):
  - The header has an "Experiment Lineage" button, and clicking it calls `goto("/optimize/proj1/task1/experiment_lineage")` with no selection.
