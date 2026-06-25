---
status: complete
---

# Phase 10 — Test-pane score-range validation (D16)

## Overview

The project's only backend change. Extract the per-rating-type range checks from
`EvalRun.validate_scores` into a shared pure function
`validate_scores_against_output_scores`, refactor `EvalRun` to call it (no behavior
change), then call it from `test_v2_eval` to surface out-of-range scores on a new
`TestV2EvalResponse.score_range_errors` field. On the frontend, fold those errors into
the existing warning pattern and gate Save.

## Steps

1. **Backend — extract shared validator (libs/core/kiln_ai/datamodel/eval.py)**
   - Add `validate_scores_against_output_scores(scores: EvalScores, output_scores: list[EvalOutputScore]) -> list[str]`
     as a module-level pure function. Returns human-readable problem strings (empty = OK).
   - Replicates the per-rating-type range loop currently inside `EvalRun.validate_scores`
     (five_star 1.0–5.0, pass_fail 0.0–1.0, pass_fail_critical -1.0–1.0, custom = error).
   - Refactor `EvalRun.validate_scores` to call the new function and raise ValueError with
     the first problem string, preserving exact existing behavior.

2. **Backend — new API response field (app/desktop/studio_server/eval_api.py)**
   - Add `score_range_errors: list[str] | None = None` to `TestV2EvalResponse`.
   - In `test_v2_eval`, after a non-skipped adapter result, run
     `validate_scores_against_output_scores(scores, eval_obj.output_scores)`.
     If problems, set `score_range_errors` on the response. Scores still returned.

3. **OpenAPI schema regeneration**
   - Run `mcp__HooksMCP__generate_schema` then `mcp__HooksMCP__check_schema`.

4. **Frontend — surface score-range errors (eval_config_builder + eval_test_run_pane)**
   - In `eval_config_builder.svelte` `run_test()`, after shape validation, check
     `result.score_range_errors`. If non-empty, set a new `test_score_range_warning`
     variable and set `test_has_valid_run = false`.
   - In `eval_test_run_pane.svelte`, accept a new `test_score_range_warning` prop and
     render it in the same visual family as `test_shape_warning` (alert-warning).
   - Save button remains gated by `test_has_valid_run`.

## Tests

- **Core:** `validate_scores_against_output_scores` returns problems for each rating type's
  out-of-range bounds and returns `[]` for in-range. `EvalRun.validate_scores` behavior
  unchanged — existing tests pass; add one confirming it still raises on out-of-range.
- **API:** `test_v2_eval` returns `score_range_errors` populated for an out-of-range code
  result and None/empty for in-range.
- **Frontend:** out-of-range result shows the warning and leaves Save gated
  (`test_has_valid_run=false`); removing the gating would cause the test to fail.
