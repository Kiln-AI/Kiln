---
status: complete
---

# Phase 2: Frontend dialog + sample asset

## Overview

Make the existing CSV upload dialog turn-mode aware so multiturn tasks get
multiturn-specific help text, a tailored title, an inline example, and a sample
CSV link. Add the sample asset to `static/` so the link resolves. The
OpenAPI client was regenerated in Phase 1, so no schema regeneration is needed
unless `git status` shows the dev server produced new diffs.

## Steps

1. `app/web_ui/static/sample_multiturn.csv` (new file):
   - Two rows demonstrating one-turn and multi-turn shapes, matching architecture §5.5.
   - Columns `trace,tags`. Trace cells are JSON-encoded OpenAI message lists with
     escaped quotes per CSV rules.

2. `app/web_ui/src/routes/(app)/dataset/[project_id]/[task_id]/upload_dataset_dialog.svelte`:
   - Import `current_task` from `$lib/stores`.
   - Add reactive `is_multiturn = $current_task?.turn_mode === "multiturn"`.
   - Add reactive `dialog_title = is_multiturn ? "Add Multiturn CSV to Dataset" : "Add CSV to Dataset"`.
   - Replace the hardcoded `title="Add CSV to Dataset"` with `title={dialog_title}`.
   - Wrap the existing help block in `{#if is_multiturn} … {:else} …existing… {/if}`.
   - Multiturn help block contents (per architecture §5.2):
     - Intro sentence explaining one row = one conversation.
     - `<ul>` listing `trace` (required) and `tags` (optional).
     - Inline `<pre>` example showing alternating user/assistant messages.
     - A callout: "Multiturn traces must alternate user/assistant and end with
       assistant. System messages are not supported — set the system prompt on
       the task instead."
     - "Download sample CSV" link to `/sample_multiturn.csv` with `download`
       attribute.
   - Single-turn branch keeps the existing help block verbatim (no behavior
     change for single-turn tasks).

3. `app/web_ui/src/routes/(app)/dataset/[project_id]/[task_id]/upload_dataset_dialog.test.ts` (new test file):
   - Use `@testing-library/svelte` with `@vitest-environment jsdom`, mirroring
     the pattern in `sidebar_rail_task_chip.test.ts`.
   - Reset `current_task` in `beforeEach`/`afterEach`.
   - Mock the `$app/stores` `page` store (param read in script).

## Tests

Vitest (`upload_dataset_dialog.test.ts`):

- `renders single-turn help when current_task is single-turn` — `current_task`
  set to a `{turn_mode: "single_turn"}` task. Asserts dialog title is
  "Add CSV to Dataset"; help text mentions `input` / `output` columns; does NOT
  contain `trace` column or "Download sample CSV" link.
- `renders multiturn help when current_task is multiturn` — `current_task` set
  to a `{turn_mode: "multiturn"}` task. Asserts dialog title is
  "Add Multiturn CSV to Dataset"; help text lists `trace` and `tags`; contains
  the "System messages are not supported" callout; renders a download link
  pointing at `/sample_multiturn.csv` with `download` attribute.
- `dialog title falls back to single-turn when current_task is null` —
  exercises the default branch of the optional chain.
