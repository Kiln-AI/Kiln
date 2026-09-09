---
status: complete
---

# Phase 5 — Test Run Pane (extraction + states)

## Overview

Extract the entire right-column Test Run pane from `eval_config_builder.svelte` into a
presentational `eval_test_run_pane.svelte` component. The builder remains the orchestrator
(owns state, trust/save logic); the pane receives state as props and dispatches events.
Implement the 5 visual states (empty, ready, running, results, browse modal) plus supporting
sub-components.

## Steps

### 1. Create `test_run_input_card.svelte`

**File:** `app/web_ui/src/lib/components/eval_types/test_run/test_run_input_card.svelte`

- Props: `run: TaskRunOutput`, `variant: "selected" | "pick"`, `disabled: boolean`
- Shows truncated 2-line Input + 2-line Output (CSS line-clamp)
- Full text in tooltip (title attr) for both
- `selected` variant: prominent card with "Selected Run" label + "Change" button (dispatches `change` event)
- `pick` variant: compact clickable row (dispatches `select` with the run)
- `disabled` prop locks the "Change" button (running state)

### 2. Create `manual_example_dialog.svelte`

**File:** `app/web_ui/src/lib/components/eval_types/test_run/manual_example_dialog.svelte`

- Two textareas: Input, Output
- Confirm disabled when both are empty
- On confirm: dispatches `confirm` with an ephemeral `TaskRunOutput`-shaped object
  (`{ input, output: { output } }`) -- not persisted to the dataset
- Cancel closes the dialog

### 3. Create `test_run_browse_dialog.svelte`

**File:** `app/web_ui/src/lib/components/eval_types/test_run/test_run_browse_dialog.svelte`

- Props: `available_runs: TaskRunOutput[]`
- Wide Dialog (`width="wide"`), title "Choose an input", subtitle
- Restyled table: Input preview, Output preview, Created columns
- Pagination (reuse PAGE_SIZE=5 logic from TaskRunPicker)
- No search field
- First row preselected; radio selection
- "Add manual example" button opens `manual_example_dialog`
- Footer: count caption + Cancel / "Use input" (primary)
- Dispatches `select` with chosen run on "Use input"

### 4. Create `reference_data_field.svelte`

**File:** `app/web_ui/src/lib/components/eval_types/test_run/reference_data_field.svelte`

- Props: `reference_data: string` (the raw JSON string)
- Displays as a property-row: "Reference Data" label, value "None" or truncated summary
- Click opens a Dialog with a textarea for JSON editing
- On save: `JSON.parse` validation, inline error on bad JSON
- Dispatches `change` with the new JSON string

### 5. Create `eval_test_run_pane.svelte`

**File:** `app/web_ui/src/lib/components/eval_types/test_run/eval_test_run_pane.svelte`

Props (all from builder):
- `runs_loading`, `runs_error`, `available_runs`, `selected_run`
- `reference_data`, `test_loading`, `test_result`, `test_error`
- `test_shape_warning`, `test_has_valid_run`
- `is_llm_judge`, `can_submit_llm`
- `task_id`, `project_id`, `spec_id`

Events dispatched up to builder:
- `select` (run), `run`, `cancel`, `saveWithoutTesting`
- `updateReferenceData` (string), `runAgain`, `save`

State machine (driven by props):
1. `runs_loading` -> spinner
2. `runs_error` -> inline error
3. Empty (`available_runs.length === 0`): educational empty state + "Save Without Testing"
4. Ready (has runs, not loading, no result): selected card + 2 quick-picks + browse link +
   reference data field + Run button + results placeholder
5. Running (`test_loading`): spinner + "Running..." + caption, selected input shown, Change locked, Cancel
6. Results (`test_result`): scores display + shape warning + Run again + Save

Auto-select: `selected_run` defaults to `available_runs[0]` (handled by builder).
Quick-picks: `available_runs.filter(r => r !== selected_run).slice(0, 2)`.

### 6. Refactor `eval_config_builder.svelte`

- Replace the entire right-column markup (lines ~439-603) with `<EvalTestRunPane>` component
- Wire all props from existing state variables
- Wire all events to existing handler functions
- Add auto-select logic: after `load_task_runs()` completes, set
  `selected_task_run = available_runs[0] ?? null`
- Replace `advanced_reference_data` collapse with `reference_data` prop/event flow
- Remove `clear_selection()` (replaced by browse dialog flow)
- Keep `select_task_run`, `run_test`, `cancel_test`, `handle_submit`, `do_save`,
  `grant_trust_and_retry` in the builder
- Remove imports no longer needed (Collapse, TaskRunPicker, formatExpandedContent)

### 7. Create stubs for testing

- `test_run_pane_stub.svelte` (if needed for builder tests)
- Extend existing dialog_stub if needed

### 8. Write tests

**File:** `app/web_ui/src/lib/components/eval_types/test_run/eval_test_run_pane.test.ts`

Tests for:
- Each of the 5 states renders correctly
- Input card: quick-picks layout, 2-line truncation, selected vs pick variant
- Browse dialog: wide, no search field, add-manual-example button present
- Manual example dialog: ephemeral (dispatches confirm, not API call), both-empty guard
- Reference data field: JSON modal, invalid JSON error
- Auto-select first run

Additional tests in `page.test.ts`:
- Builder wires pane events correctly (spot checks)

## Tests List

1. State 1 (empty dataset): renders "No sample inputs yet", "Go to Run" button, "Save Without Testing"
2. State 2 (ready): renders selected card + 2 quick-picks + "Browse all" link + Run button
3. State 3 (running): renders spinner + "Running..." + Cancel, Change disabled
4. State 4 (results): renders scores, shape warning, "Run again" + Save
5. State 5 (browse dialog): wide, no search, table with Input/Output/Created, "Add manual example"
6. Input card quick-picks: 2 quick-pick rows shown, click selects
7. Input card 2-line layout: truncation via line-clamp classes present
8. Manual example dialog: ephemeral run created on confirm, both-empty guarded
9. Reference data field: opens JSON modal, shows error on invalid JSON
10. Auto-select first run: first available run is selected on mount
