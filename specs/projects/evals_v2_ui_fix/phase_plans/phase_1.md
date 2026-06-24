---
status: complete
---

# Phase 1: Routing & Container Restructure (Nav Fix)

## Overview

Replace the in-page state machine (local `selected_v2_type` variable switching
between picker and form views) with real SvelteKit routes. This gives the
create-eval-config flow proper URL-based navigation: browser Back returns to the
picker, refresh preserves the selected type, and deep-linking works. An
`EvalConfigBuilder` container component is extracted to own the form + test pane
+ save logic, keeping the per-type forms and existing behavior intact.

## Steps

### 1. Create shared layout (`+layout.svelte`)

File: `…/create_eval_config/+layout.svelte`

- Loads eval, task, spec, and available_models on mount (moved from the current
  `+page.svelte:56-73`).
- Passes loaded data to child routes via Svelte `setContext`.
- Handles legacy `?config_type=g_eval|llm_as_judge` redirect: if the query
  param is present, `goto('…/create_eval_config/llm_judge', { replaceState: true })`.
- Carries `next_page` and `save_as_default` query params through.
- Shows loading spinner / error while data loads; renders `<slot />` when ready.

### 2. Create `+layout.ts` (disable prerender)

File: `…/create_eval_config/+layout.ts`

- `export const prerender = false` (shared by both child routes).
- Delete the existing `+page.ts` (which just has `prerender = false`).

### 3. Refactor picker into index route (`+page.svelte`)

File: `…/create_eval_config/+page.svelte` (rewritten)

- Reads eval/task/spec from layout context.
- Renders AppPage with title, subtitle, breadcrumbs.
- Shows the type-picker card grid (moved from current `:477-508`).
- On card click: `goto('…/create_eval_config/' + type + query_params)` (real
  history push).
- Reorder types: "LLM as Judge (recommended)" first, then the rest. Update
  label in registry.
- Sets `agentInfo`.

### 4. Create `[eval_config_type]/+page.svelte` builder route

File: `…/create_eval_config/[eval_config_type]/+page.svelte`

- Reads `eval_config_type` from `$page.params`.
- Validates it against `ALL_V2_EVAL_TYPES`; renders an error if unknown.
- Gets shared data from layout context.
- Renders `<EvalConfigBuilder>` with the correct type, eval, task, spec.
- Sets `agentInfo`.

### 5. Extract `EvalConfigBuilder` container component

File: `$lib/components/eval_types/eval_config_builder.svelte`

Props: `eval_config_type: V2EvalType`, `evaluator: Eval`, `task: Task`,
`spec: Spec | null`, `project_id`, `task_id`, `eval_id`, `spec_id`.

Owns (moved from current `+page.svelte`):
- `FormContainer` with `warn_before_unload` + `beforeNavigate` guard.
- Per-type form rendering via `<svelte:component>` (deterministic/code) or
  `<LlmJudgeForm>` (llm_judge).
- Type header (icon + label, no Back button).
- Test Run pane (the existing `<Collapse>` with free-text inputs, for now).
- `do_save`, `handle_submit`, trust gate, save-without-testing confirm.
- Post-save navigation (`next_page`, `save_as_default`).
- Breadcrumbs.
- Trust + confirm-save `<Dialog>` components.

The on-screen Back button is removed (browser Back navigates to the picker).

### 6. Update registry: reorder types, update label

File: `$lib/utils/eval_types/registry.ts`

- Move `llm_judge` to first position in `ALL_V2_EVAL_TYPES`.
- Update label to `"LLM as Judge (recommended)"`.

### 7. Update existing tests

- Update `page.test.ts` to test the **picker page** (card grid rendering,
  click triggers `goto` to child route, legacy redirect).
- Add a test file for `EvalConfigBuilder` covering: correct form rendered per
  type, save posts correct payload, trust gating, save-without-testing.
- Add a test for the `[eval_config_type]` route: unknown type shows error,
  valid type renders builder.

### 8. Clean up

- Remove `eval_steps_utils.ts` and `get_eval_steps.test.ts` from the route
  folder (these are duplicates of the version in `$lib/utils/eval_types/`).
- Remove the old `+page.ts` (replaced by `+layout.ts`).

## Tests

- **picker renders type cards**: verifies all 8 types are shown, with
  "LLM as Judge (recommended)" first.
- **picker card click navigates**: clicking a card calls `goto` with the
  correct child route path + preserved query params.
- **legacy redirect**: `?config_type=g_eval` redirects to `…/llm_judge`.
- **builder renders correct form**: each V2EvalType renders the right form
  component via `EvalConfigBuilder`.
- **unknown type shows error**: `[eval_config_type]` with an invalid value
  renders an error message.
- **trust gate for code_eval**: save triggers trust check, shows dialog if
  untrusted.
- **save-without-testing confirm**: save without a prior test run shows
  confirm dialog.
- **save posts correct payload**: deterministic types send `config_type="v2"`
  with full properties; llm_judge sends V1 shape (unchanged until Phase 2).
