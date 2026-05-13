---
status: complete
---

# Phase 2: Frontend — fork UI

## Overview

Add the multiturn trace fork UI on the run-detail page. This phase is pure
frontend and uses the `ancestors` endpoint shipped in Phase 1.

The user-visible work:

- Each eligible user block in the trace gets a small "fork" icon button.
- Clicking the icon truncates the visible trace at that turn and opens an
  inline composer prefilled with that turn's original user text, defaulting
  the run config to the leaf's current run config.
- The inline composer has Cancel (with dirty-confirm) and Send. Send POSTs
  to the existing `/run` endpoint with `parent_task_run_id` = turn K-1's
  run id and navigates to the new leaf.
- Broken-chain or ancestors-fetch-failure renders a non-blocking warning
  banner.

Implementation strategy: extract the current inline append-mode composer
into a reusable `MultiturnComposer.svelte` and extend it with a fork mode.
Add a new `ForkIcon.svelte`. Extend `trace.svelte` with three optional
props (`forkable_run_ids`, `truncate_at_trace_index`, `on_fork`). Wire the
state on the run-detail `+page.svelte`.

## Steps

1. **Add `TaskRunAncestor` type alias** in
   `app/web_ui/src/lib/types.ts` exposing the OpenAPI schema entry.

2. **Create `app/web_ui/src/lib/ui/icons/fork_icon.svelte`** — a small
   git-branch SVG icon, single-file, matching the conventions of the other
   icons in the same folder (`refresh_icon.svelte`, `tools_icon.svelte`).

3. **Extend `app/web_ui/src/lib/ui/trace/trace.svelte`** — add three
   optional props:

   ```ts
   export let forkable_run_ids: (string | null)[] | undefined = undefined
   export let truncate_at_trace_index: number | null = null
   export let on_fork: ((run_id: string, trace_index: number) => void) | undefined = undefined
   ```

   Inside the `{#each trace as message, index}` loop:
   - Wrap the block render in `{#if truncate_at_trace_index === null || index < truncate_at_trace_index}`.
   - In the user-block header (when `message.role === "user"` and
     `forkable_run_ids?.[index]` is set and `on_fork` is provided), render
     a `btn btn-ghost btn-xs` fork button before the collapse arrow with
     `aria-label="Fork from this turn"`, `title="Fork from here"`, and
     `on:click|stopPropagation` calling `on_fork(forkable_run_ids[index]!, index)`.

4. **Create `app/web_ui/src/lib/ui/conversation/multiturn_composer.svelte`** —
   extracts the current inline `FormContainer + RunInputForm + SavedRunConfigurationsDropdown + RunConfigComponent` block from
   `+page.svelte` into a reusable component with these props:

   ```ts
   export let mode: "append" | "fork" = "append"
   export let project_id: string
   export let task: Task
   export let parent_task_run_id: string | null
   export let initial_model: string = ""
   export let initial_prompt: string = "simple_prompt_builder"
   export let prefill_text: string = ""
   export let forked_turn_index: number | undefined = undefined
   export let on_success: (new_run_id: string) => void | Promise<void>
   export let on_cancel: (() => void) | undefined = undefined
   ```

   Behavior:
   - Builds the internal `FormContainer` with submit handler that calls
     `send_multiturn` and forwards `on_success`.
   - In `fork` mode: top of the component renders a thin context strip with
     a ForkIcon and the text `Forking turn N` and a muted right-side hint
     ("Original message preserved on parent.").
   - In `fork` mode: textarea is initialized from `prefill_text`. On mount in
     fork mode the textarea gets focus with cursor at end.
   - In `fork` mode: a Cancel button is rendered next to Send via the
     `submit_left` slot of `FormContainer`. Cancel does:
     - If textarea content equals the original `prefill_text`, calls
       `on_cancel()` immediately.
     - Otherwise opens a DaisyUI `<dialog>` (via `Dialog` component) with
       buttons "Keep editing" / "Discard" — discard calls `on_cancel()`.
   - Append-mode behaves identically to today (no context strip, no
     Cancel) so the existing flow is unchanged.

   The component owns `RunInputForm`, the `RunConfigComponent`, and the
   `SavedRunConfigurationsDropdown`. The `+page.svelte` no longer
   directly instantiates these for multiturn runs — it just hosts the
   composer.

5. **Update `app/web_ui/src/routes/(app)/dataset/[project_id]/[task_id]/[run_id]/run/+page.svelte`**:

   - Add state:
     ```ts
     let ancestors: TaskRunAncestor[] = []
     let ancestors_chain_broken = false
     let ancestors_load_failed = false
     let fork_target: { turn_index: number; parent_run_id: string | null; trace_index: number; prefill: string } | null = null
     ```
   - Reactive fetch: when `task && run && task.turn_mode === "multiturn"`,
     call `load_ancestors(project_id, task_id, run_id)` which GETs the new
     endpoint via the typed `client`, ignoring out-of-date responses
     (matching `load_run` pattern). On error set `ancestors_load_failed`.
   - Reset `fork_target` whenever `run_id` changes.
   - Compute `forkable_run_ids` from `(run.trace, ancestors)` (helper
     factored into `fork_helpers.ts`).
   - Replace the existing inline composer block with
     `<MultiturnComposer mode="append" .../>` when `fork_target` is null,
     and with `<MultiturnComposer mode="fork" .../>` when `fork_target` is
     set. Pass through `initial_model` and `initial_prompt` derived from
     the run's existing config in both modes (matches today's behavior).
   - Render warning banners above `TraceComponent` for the
     `ancestors_chain_broken` / `ancestors_load_failed` cases.
   - Pass `forkable_run_ids` / `truncate_at_trace_index` / `on_fork` to
     `TraceComponent`.

6. **Create `fork_helpers.ts`** alongside `+page.svelte` with
   `compute_forkable_run_ids(trace, ancestors)` and
   `fork_target_from_user_block(run_id, ancestors, trace)`. Pure
   functions, exported for unit testing.

## Tests

- **`trace.svelte` (vitest)**:
  - Fork button renders on user blocks where `forkable_run_ids[i]` is set.
  - Fork button absent on system / assistant / tool blocks and when
    `forkable_run_ids[i]` is null.
  - Clicking fork calls `on_fork(run_id, index)` and does not toggle the
    collapse checkbox (stopPropagation works).
  - `truncate_at_trace_index = K` hides messages at index ≥ K (visible
    collapse count drops accordingly).

- **`multiturn_composer.svelte` (vitest)**:
  - Append mode renders no Cancel button and no context strip.
  - Fork mode renders the context strip with "Forking turn 3".
  - Fork mode prefills the textarea with `prefill_text`.
  - Cancel with unchanged input calls `on_cancel` synchronously (no
    dialog shown).
  - Cancel with dirty input opens the discard-confirmation dialog and does
    NOT call `on_cancel` until the Discard button is clicked.

- **`fork_helpers.test.ts` (vitest)**:
  - `compute_forkable_run_ids` for a clean 3-turn chain returns
    `[null, null, runA, null, runB, null, runC, null]` (trace = system +
    3 × {user, assistant}; turn 1 user has `null` because turn 1 is not
    forkable).
  - `compute_forkable_run_ids` with ancestors length 1 (turn_index=3) on a
    3-user-message trace returns nulls except for the third user index
    (suffix-aligned).
  - `compute_forkable_run_ids` with empty ancestors returns all nulls.
  - `fork_target_from_user_block` returns the parent run id for an
    interior turn and null when the requested run isn't found.
