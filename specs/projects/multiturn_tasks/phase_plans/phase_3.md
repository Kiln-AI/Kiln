---
status: complete
---

# Phase 3: Task creation/edit form — turn_mode selector

## Overview

Frontend-only. Add a `turn_mode` segmented control to the task creation form, hide structured input/output schema sections when the user picks `multiturn`, send `turn_mode` in the create payload, and render the value as a read-only label on the edit page (turn_mode is immutable post-creation per Phase 1).

End state for Phase 3:

- `app/web_ui/src/routes/(fullscreen)/setup/(setup)/create_task/edit_task.svelte` exposes a two-option DaisyUI `join` selector for `turn_mode` (defaulting to `single_turn`). When `multiturn` is selected, both the input-schema and output-schema sections (and their descriptive headers) hide and small explanatory notes show in their place. The selector lives near the top of the form, before the input-schema section.
- The create-task POST body includes `turn_mode`.
- The component accepts a `read_only_turn_mode: boolean = false` prop. When `true` (set by `load_task_editor.svelte` on the edit page), the selector renders as a labelled, non-interactive value with a hint that it cannot be changed.
- Component tests under `app/web_ui/src/routes/(fullscreen)/setup/(setup)/create_task/edit_task.test.ts` cover the toggle behavior, conditional rendering, payload contents, and read-only mode.

OpenAPI types already include `Task.turn_mode` and `TurnMode` (regenerated in Phase 1) — no schema regeneration in this phase.

## Steps

1. **`app/web_ui/src/lib/types.ts` — export `TurnMode` alias.** Add `export type TurnMode = components["schemas"]["TurnMode"]` so the component can reference the literal-union type.

2. **`app/web_ui/src/routes/(fullscreen)/setup/(setup)/create_task/edit_task.svelte` — add the selector and wire it through.**

   - Import the new `TurnMode` type.
   - Add a new prop:
     ```ts
     export let read_only_turn_mode: boolean = false
     ```
   - Add a local reactive variable initialised from the task (so an existing task's value drives the read-only label, while a fresh form starts as `single_turn`):
     ```ts
     let turn_mode: TurnMode = task.turn_mode ?? "single_turn"
     ```
   - In `create_task()`, when `creating`, include `turn_mode` in the request body. Don't add it to the PATCH body — backend rejects changes (Phase 1) and the field isn't editable.
   - Add a new section just before "Part 2: Input Schema". Two render branches:
     - `read_only_turn_mode === true` (edit page): render the value as a small label-style block (`Task type: Single-turn` / `Task type: Multiturn`) plus a one-line gray hint "This setting can't be changed after the task is created." Match the existing read-only schema-display pattern (text label + `Output` style).
     - Otherwise: render `<div class="join">` with two `join-item btn` buttons toggling `turn_mode` between `single_turn` and `multiturn`. The active button gets `btn-active` (mirrors `dataset/[project_id]/[task_id]/+page.svelte` and `docs/extractors/[project_id]/+page.svelte`). Below the toggle: a one-line description for each option per `ui_design.md`:
       - `Single-turn — Each run is independent.`
       - `Multiturn — Conversational; runs continue prior runs.`
   - Wrap the existing "Part 2: Input Schema" and "Part 3: Output Schema" blocks with `{#if turn_mode === "single_turn"}` … `{:else}` branches. The else branches render small explanatory notes per `ui_design.md`:
     - Input: "Multiturn tasks use plain-text input."
     - Output: "Structured output is not supported for multiturn tasks yet."
     The header strips ("Part 2: Input Schema" / "Part 3: Output Schema") still render in both branches so the form's part numbering remains stable; only the schema editor (or read-only display) is hidden.
   - The existing `has_edits` function references `inputSchemaSection.get_schema_string(...)` / `outputSchemaSection.get_schema_string(...)`. When `multiturn`, those `bind:this` targets won't exist. Guard with optional chaining (`inputSchemaSection?.get_schema_string("input_schema")`) and treat missing/empty as falsey. Same for the create-task body construction: skip the schema fields when multiturn so the backend doesn't get a stale string.

3. **`app/web_ui/src/routes/(app)/settings/edit_task/[project_id]/[task_id]/load_task_editor.svelte` — pass the read-only prop.** Add `read_only_turn_mode={!clone_mode}` on the `<EditTask>` invocation. Clone mode is treated as creation (the cloned task gets a fresh id), so the user can pick a new `turn_mode`; pure-edit mode is read-only.

## Tests

New file `app/web_ui/src/routes/(fullscreen)/setup/(setup)/create_task/edit_task.test.ts` (vitest, `@vitest-environment jsdom`):

- Mock `$lib/api_client` so `client.POST` is a `vi.fn()` returning `{ data: { id: "task-1" }, error: null }`.
- Mock `$lib/stores` (`current_project`, `projects`, `ui_state`, `load_current_task`, `load_rating_options`) so the form can run without real backend calls.
- Mock `$app/navigation` (`goto`) and `posthog-js` (`capture`).

Test cases:

- **`renders single_turn by default and shows both schema sections`** — mount with no task; assert the Single-turn button has `btn-active`, the Multiturn button does not, and the input/output `SchemaSection` containers are present in the DOM.
- **`switching to multiturn hides the input + output schema sections`** — click the Multiturn button; assert input/output schema editors are no longer in the DOM and the explanatory notes ("Multiturn tasks use plain-text input." and "Structured output is not supported for multiturn tasks yet.") are present.
- **`switching back to single_turn re-shows the schema sections`** — click Multiturn, then click Single-turn; assert the schema sections render again.
- **`read_only_turn_mode renders the value as a label and hides the toggle`** — mount with `read_only_turn_mode={true}` and a task whose `turn_mode === "multiturn"`; assert the static label "Task type: Multiturn" plus the hint copy is present and no `<button>` for `Single-turn`/`Multiturn` exists.
- **`creating a single_turn task posts turn_mode: "single_turn"`** — fill `name` + `instruction`, submit; assert `client.POST` was called once with body containing `turn_mode: "single_turn"`.
- **`creating a multiturn task posts turn_mode: "multiturn" without schema fields`** — switch to Multiturn, submit; assert the POST body has `turn_mode: "multiturn"` and `input_json_schema` / `output_json_schema` are unset (or null/empty).

## Out of scope

- `/run` page branching, dataset run-detail conversation view, `ConversationView`/`TurnCard`/`Composer` — Phase 4.
- Backend changes — already shipped in Phases 1 & 2.
- OpenAPI regeneration — already done in Phase 1.
