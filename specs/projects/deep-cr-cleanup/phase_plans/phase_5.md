---
status: complete
---

# Phase 5: Reference-data UI TODO-gates

## Overview

In V2.0, no wired UI path populates `reference_data` on EvalInputs. Any eval-type form that lets a user select `reference_key` as the data source would produce an eval config that always silently skips at runtime (the `required_var`/`extract_value` helpers treat missing reference data as a clean skip). This phase adds deliberate `TODO` comments at each such UI affordance, creating a hard pre-ship gate via CI's no-TODO-on-main rule. The SDK code path is untouched; this is a UI-completeness gate only.

## Steps

1. **`exact_match_form.svelte`** — Added `TODO(pre-ship 5.3)` comment above the `source` variable declaration, which controls the "Match Source" `<FormElement>` selector offering `["reference_key", "Reference Data Key"]`. The TODO states the affordance must be wired or removed before shipping to main.

2. **`set_check_form.svelte`** — Added `TODO(pre-ship 5.3)` comment above the `source` variable declaration, which controls the "Expected Set Source" `<FormElement>` selector offering `["reference_key", "Reference Data Key"]`. Same gate language.

3. **`contains_form.svelte`** — Added `TODO(pre-ship 5.3)` comment above the `source` variable declaration, which controls the "Match Source" `<FormElement>` selector offering `["reference_key", "Reference Data Key"]`. Same gate language.

4. **Forms verified clean (no reference_key source affordance):**
   - `pattern_match_form.svelte` — no `reference_key` usage
   - `step_count_check_form.svelte` — no `reference_key` usage
   - `tool_call_check_form.svelte` — no `reference_key` usage
   - `llm_judge_form.svelte` — no `reference_key` usage
   - `code_eval_form.svelte` — mentions `reference_data` only as a Python function parameter in code templates, not as a UI source selector

## Tests

N/A — comment-only change. All existing frontend tests (1115 tests across 59 files), lint, type-check, and build pass with the TODOs present.
