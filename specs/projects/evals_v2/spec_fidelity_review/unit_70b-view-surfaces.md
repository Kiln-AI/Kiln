# Spec-Fidelity Review: 70b-view-surfaces

**Unit:** 70b-view-surfaces
**Title:** UI: result renderers, registry, config view, comparison
**Spec:** `components/70_builder_and_onboarding.md` sections 4, 4.1, 4.2, 4.3

---

## Summary

Requirements: 18 total — MET 12, PARTIAL 3, MISSING 1, CONTRADICTED 0, DEFERRED_OK 0, CANNOT_VERIFY 2

---

## Requirements

### 70b-view-surfaces-R01
- **Category:** Registry architecture
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Renderer registry keyed on `properties.type` discriminator (same as backend adapter registry).
- **Spec quote:** "View surfaces render per-type via a renderer registry keyed on the same `properties.type` discriminator the backend adapter registry uses"
- **Evidence:** `app/web_ui/src/lib/utils/eval_types/registry.ts:72-157` — `getV2EvalTypeMetadata(type: V2EvalType)` uses a switch on the type discriminator string to return per-type metadata including `resultRendererComponent`.

### 70b-view-surfaces-R02
- **Category:** Registry architecture
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Two parallel registries — create-form-by-type and result-renderer-by-type — expressed as one per-type module exporting label, icon, createForm, resultRenderer, requiresTrust.
- **Spec quote:** "best expressed as one per-type module exporting `{ label, icon, createForm, resultRenderer, requiresTrust }`"
- **Evidence:** `registry.ts:59-66` — `V2EvalTypeMetadata` interface exports `label`, `icon`, `requiresTrust`, `createFormComponent`, `resultRendererComponent`. All 8 types registered in `getV2EvalTypeMetadata`. Separate component files exist for each type's form and result renderer.

### 70b-view-surfaces-R03
- **Category:** Registry architecture
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Mixed-type display: an Eval whose candidate configs are different types must not choke the view.
- **Spec quote:** "Mixed-type display: an Eval whose candidate configs are different types must not choke the view."
- **Evidence:** `eval_configs/+page.svelte:737-764` — Each config is rendered independently using `eval_config_to_detailed_ui_name()`, not assuming a single type. `run_config_comparison_table.svelte` also doesn't assume a uniform type. The run_result page resolves the renderer per eval_config, not globally.

### 70b-view-surfaces-R04
- **Category:** Defensive binding
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Registry is exhaustive over V2EvalType enum — compile-time (TS exhaustiveness / `never`).
- **Spec quote:** "compile-time (TS exhaustiveness / `never`)"
- **Evidence:** `registry.ts:154-155` — `default: return assertNever(type)` in the switch statement ensures TS will flag missing cases at compile time.

### 70b-view-surfaces-R05
- **Category:** Defensive binding
- **Verdict:** PARTIAL
- **Severity:** minor
- **Requirement:** Runtime assert that every enum value maps to a module. A backend type added without a UI module FAILS LOUDLY rather than rendering blank.
- **Spec quote:** "A backend type added without a UI module fails loudly rather than rendering blank."
- **Evidence:** `registry.ts:163-174` (`getV2TypeFromEvalConfig`) returns `null` for a type string not in `ALL_V2_EVAL_TYPES`. In `run_result/+page.svelte:288-299`, when `v2_result_component` is null (unknown V2 type), the fallback branch renders basic per-score columns (lines 291-299) — it does NOT throw, log an error, or show a warning. Similarly in `eval_configs/+page.svelte` the display simply uses `eval_config_to_detailed_ui_name` which would just show the raw type string. The compile-time guard (`assertNever`) is solid, but the runtime path for an unrecognized type string arriving from the backend does not "fail loudly" — it silently degrades.
- **Divergence:** Spec requires a runtime assertion / visible error ("fails loudly"). Code silently falls back to basic rendering for an unknown V2 type string.

### 70b-view-surfaces-R06
- **Category:** Result renderer — firm requirement
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Every type's result renderer shows the score(s) against output_scores.
- **Spec quote:** "every type's result renderer shows the score(s) against output_scores (the existing score badge component — pass/fail / pass_fail_critical / five_star)"
- **Evidence:** All 8 result renderers import and render `EvalResultScores` (`eval_result_scores.svelte`). `eval_result_scores.svelte:24-32` iterates over `Object.entries(scores)` rendering each key:value pair. Scores are passed as `result.scores` from the API which corresponds to output_scores.

### 70b-view-surfaces-R07
- **Category:** Result renderer — firm requirement
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** Every type's result renderer shows skip state (skipped_reason) when set.
- **Spec quote:** "and skip state (`skipped_reason`) when set"
- **Evidence:** All 8 result renderers pass `{skipped_reason}` and `{skipped_detail}` to `EvalResultScores`. `eval_result_scores.svelte:11-23` shows a "Skipped" badge with the reason and detail when `skipped_reason` is truthy.

### 70b-view-surfaces-R08
- **Category:** Result renderer — illustrative (NOT binding)
- **Verdict:** MET (illustrative — not flagged)
- **Severity:** n/a
- **Requirement:** [ILLUSTRATIVE] Per-type result renderer content as described in the table (e.g., llm_judge shows reasoning, code_eval shows stdout/stderr, etc.)
- **Spec quote:** "This is not a binding layout spec. The coding agent should take a run at it... The table below is illustrative guidance"
- **Evidence:** Each result renderer implements reasonable content. Not checked against illustrative table per instructions.

### 70b-view-surfaces-R09
- **Category:** View surfaces — routes
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** `…/[eval_id]/+page.svelte` — eval detail (config list + summary scores) integrates V2.
- **Spec quote:** lists this route under §4.2
- **Evidence:** `eval_id/+page.svelte:315-320` — handles V2 configs via `eval_config_to_detailed_ui_name()` and shows "Judge Type" for v2 configs.

### 70b-view-surfaces-R10
- **Category:** View surfaces — routes
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** `…/[eval_id]/eval_configs/+page.svelte` — eval-configs list / candidates integrates V2.
- **Spec quote:** lists this route under §4.2
- **Evidence:** `eval_configs/+page.svelte:737-743` — V2 configs show name and type via `eval_config_to_detailed_ui_name()`. The page handles mixed V1/V2 configs in the same table.

### 70b-view-surfaces-R11
- **Category:** View surfaces — routes
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** `…/[eval_id]/compare_run_configs/+page.svelte` + `run_config_comparison_table.svelte` — calibration comparison table tolerates mixed types.
- **Spec quote:** lists this route under §4.2 and "must tolerate mixed types per §4"
- **Evidence:** `compare_run_configs/+page.svelte:573-594` uses `RunConfigComparisonTable` which renders scores from `EvalResultSummary` without assuming a specific eval type. The component uses `evaluator.output_scores` for column headers regardless of config type.

### 70b-view-surfaces-R12
- **Category:** View surfaces — routes
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** `…/[eval_config_id]/[run_config_id]/run_result/+page.svelte` — per-run result detail uses the resultRenderer.
- **Spec quote:** "the primary home of the resultRenderer content above"
- **Evidence:** `run_result/+page.svelte:211-216` resolves `v2_result_component` from the eval_config's type, and lines 354-361 render via `<svelte:component this={v2_result_component}>` passing scores, skipped_reason, skipped_detail, and eval_config.

### 70b-view-surfaces-R13
- **Category:** View surfaces — Thinking column
- **Verdict:** PARTIAL
- **Severity:** minor
- **Requirement:** Thinking column conditional on intermediate_outputs (only llm_judge/code_eval).
- **Spec quote:** "Thinking column conditional on intermediate_outputs (only llm_judge/code_eval)"
- **Evidence:** `run_result/+page.svelte:285-286` — The Thinking column is shown only for non-V2 configs (`{#if !is_v2_config}`). For V2 configs, it is completely hidden — even for `llm_judge` and `code_eval` V2 configs that DO produce intermediate_outputs (reasoning/chain_of_thought). The intent per the focus notes was to show Thinking conditionally based on whether intermediate_outputs exist, specifically for llm_judge and code_eval.
- **Divergence:** V2 llm_judge and code_eval configs lose the Thinking column entirely. The spec intends it to appear when intermediate_outputs are available.

### 70b-view-surfaces-R14
- **Category:** Read-only config detail
- **Verdict:** PARTIAL
- **Severity:** minor
- **Requirement:** Read-only config-detail view is in scope for V2.0. A user must be able to see what a candidate config does before cloning it. Content is the right-hand column of §4.1 table.
- **Spec quote:** "the saved-config view is read-only and in scope for V2.0 (a user must be able to see what a candidate config does before cloning it). It reuses the same per-type module's createForm in a disabled/read-only mode, or a lightweight configDetail renderer"
- **Evidence:** There is no dedicated config-detail view page at the `[eval_config_id]` level. The `EvalConfigInstruction` component (`eval_config_instruction.svelte`) only extracts `eval_steps` and `task_description` (llm_judge properties), showing nothing useful for other V2 types. On the `eval_configs/+page.svelte`, V2 configs show only name and type label (lines 737-743). The result renderers (`*_result.svelte`) DO show config properties (e.g., pattern, mode, expected value) in a compact form alongside results, which partially serves the "see what a config does" need. But there is no standalone read-only config detail that shows the full configuration properties (criteria/rubric for llm_judge, code for code_eval, etc.) independent of results.
- **Divergence:** No dedicated read-only config-detail view. Per-type config properties are only visible inline within result renderers, not before cloning/outside of a result context.

### 70b-view-surfaces-R15
- **Category:** Registry architecture
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** A new type = one registered file.
- **Spec quote:** "A new type = one registered file."
- **Evidence:** Each type has a corresponding `*_form.svelte` and `*_result.svelte` file in `app/web_ui/src/lib/components/eval_types/`. Adding a new type requires: (1) adding a new case to the switch in `getV2EvalTypeMetadata`, (2) adding the form and result component files. The pattern is clear and consistent.

### 70b-view-surfaces-R16
- **Category:** View surfaces — routes
- **Verdict:** CANNOT_VERIFY
- **Severity:** n/a
- **Requirement:** The renderer registry plugs into existing eval routes — no new routes needed; V2 configs/results render wherever V1 ones already do.
- **Spec quote:** "No new routes — V2 configs/results must render wherever V1 ones already do"
- **Evidence:** All four routes listed in §4.2 exist and handle V2. No new routes were created for V2. However, I cannot exhaustively verify that there are no other eval-related routes that might have been missed. The four specified routes do work correctly.
- **Note:** Marking CANNOT_VERIFY because while the four listed routes are verified, I cannot rule out other potential surfaces. On balance, likely MET.

### 70b-view-surfaces-R17
- **Category:** Result renderer — scores rendering
- **Verdict:** MISSING
- **Severity:** minor
- **Requirement:** Score display uses "the existing score badge component — pass/fail / pass_fail_critical / five_star" (badge-style rendering of scores that understands the rating type).
- **Spec quote:** "the score(s) against output_scores (the existing score badge component — pass/fail / pass_fail_critical / five_star)"
- **Evidence:** `eval_result_scores.svelte:24-32` renders scores as plain `key: value.toFixed(2)` text. It does not use badge styling or interpret the score type (pass_fail vs five_star). Contrast with the non-V2 path in `run_result/+page.svelte:366-370` which also just shows `score_value.toFixed(2)`. There is no "score badge component" usage anywhere — scores are raw numbers. The existing pattern in the codebase (e.g., the comparison table) also shows raw numbers, so this may be a pre-existing gap rather than a V2 regression.
- **Divergence:** Spec references "the existing score badge component" for pass/fail/five_star, but no such badge component is used in result renderers — scores display as raw floats.

### 70b-view-surfaces-R18
- **Category:** Result renderer — illustrative (NOT binding)
- **Verdict:** MET (illustrative — not flagged)
- **Severity:** n/a
- **Requirement:** [ILLUSTRATIVE] Read-only config-detail per-type content as described in §4.1 right column.
- **Spec quote:** "This is not a binding layout spec."
- **Evidence:** Marked illustrative per spec language.

---

## Verifier-Added Requirements

### 70b-view-surfaces-R19 (verifier_added)
- **Category:** Registry architecture
- **Verdict:** MET
- **Severity:** n/a
- **Requirement:** `ALL_V2_EVAL_TYPES` array matches the full V2 type catalog (8 types: exact_match, pattern_match, contains, set_check, tool_call_check, step_count_check, llm_judge, code_eval).
- **Evidence:** `registry.ts:39-48` lists all 8 types. The array constant is used in `buildV2EvalTypeRegistry()` (line 181) to iterate all types, ensuring full coverage.

### 70b-view-surfaces-R20 (verifier_added)
- **Category:** View surfaces — run_result page
- **Verdict:** CANNOT_VERIFY
- **Severity:** n/a
- **Requirement:** V2 result renderers receive all necessary data (scores, skipped_reason, eval_config) to render correctly.
- **Evidence:** `run_result/+page.svelte:355-361` passes `scores`, `skipped_reason`, `skipped_detail`, and `eval_config`. All result renderers declare these as props. Correct data flow confirmed in code. Marking CANNOT_VERIFY because runtime API response shape cannot be confirmed from static analysis alone, but the wiring is correct.
