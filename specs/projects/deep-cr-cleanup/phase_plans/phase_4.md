---
status: complete
---

# Phase 4: Data-model robustness

## Overview

Three targeted improvements to the V2 eval data model and runtime:

1. **5.8** Replace the fragile double-`get_args` `_V2_PROPERTY_TYPES` unwrap with an explicit tuple defined alongside the `V2EvalConfigProperties` union in `eval.py`.
2. **5.9** Cache `output_scores` in `BaseV2EvalBridge.__init__` so `build_binary_scores` (and `CodeEvalAdapter._validate_scores`) don't call `parent_eval()` disk I/O per item.
3. **5.6** Clarify the `dataset_id`/`eval_input_id` mutual-exclusivity error message to explain V1-vs-V2 source distinction.

## Steps

### 5.8 — Explicit property-types tuple

1. In `libs/core/kiln_ai/datamodel/eval.py`, define `V2_PROPERTY_TYPES` (public tuple) immediately after the `V2EvalConfigProperties` alias, enumerating all 8 union members explicitly.
2. In `libs/core/kiln_ai/adapters/eval/base_eval.py`, remove the `_V2_PROPERTY_TYPES = get_args(get_args(...))` derivation; import `V2_PROPERTY_TYPES` from `eval.py` instead.
3. In `libs/core/kiln_ai/adapters/eval/registry.py`, update import from `base_eval` to `eval.py`.

### 5.9 — Cache output_scores for per-item scoring

1. In `BaseV2EvalBridge.__init__`, cache `self._output_scores = self.eval.output_scores` (already loaded from disk by parent `BaseEval.__init__`).
2. Change `build_binary_scores` signature to accept `output_scores: list[EvalOutputScore]` instead of `eval_config: EvalConfig`, removing the per-item `parent_eval()` call.
3. Update all callers (6 deterministic adapters) to pass `self._output_scores`.
4. In `CodeEvalAdapter._validate_scores`, use `self.eval.output_scores` (from `BaseEval.__init__`) instead of calling `parent_eval()` again.
5. In `CodeEvalAdapter._resolve_project_path`, use `self.eval` and `self.target_task` (already cached by `BaseEval.__init__`) instead of calling `parent_eval()` / `parent_task()`.

### 5.6 — Clarify mutual-exclusivity error

1. In `EvalRun.validate_input_source`, replace the error message with one that explains the V1 (dataset_id / TaskRun) vs V2 (eval_input_id / EvalInput) distinction.

## Tests

- `test_v2_property_types_matches_union`: verify the explicit tuple contains all and only the types in `V2EvalConfigProperties`.
- `test_build_binary_scores_uses_output_scores_directly`: verify `build_binary_scores` works with a list of `EvalOutputScore` without any `EvalConfig`.
- `test_build_binary_scores_no_scores`: verify empty list returns `{}`.
- `test_validate_input_source_error_message`: verify the new error message mentions V1/V2 distinction.
- Existing tests continue to pass (exact_match, contains, pattern_match, set_check, step_count_check, tool_call_check adapters all call `build_binary_scores`).
