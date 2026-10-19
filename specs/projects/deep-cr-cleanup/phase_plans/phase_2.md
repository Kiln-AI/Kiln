---
status: complete
---

# Phase 2: Backend correctness guards (Batch 1) + 5.4

## Overview

This phase fixes three correctness issues and removes one piece of dead code, all in the core eval backend:

1. **1a** -- `v2_eval_helpers.py`: `extract_value` and `check_required_vars` only check for Jinja `Undefined` but not Python `None`. When an expression resolves to `None` (e.g., a reference_data key exists but its value is null), the value passes through as if valid. Fix: treat `None` as a skip signal alongside `Undefined`.
2. **1b** -- DROPPED. `_filter_output_to_score_keys` was removed with the RAG templates (commit `5efc626`). Nothing to implement.
3. **1c** -- `eval.py` `validate_output_fields` V1 branch: a V1 EvalRun with `output=None` passes validation, then causes `AttributeError` downstream. Add an `output is not None` guard for non-skipped V1 runs.
4. **5.4** -- `eval.py` `CodeEvalProperties.validate_code`: remove the dead `except SyntaxError: pass` block. The preceding `compile()` call already catches and re-raises `SyntaxError` as `ValueError`, so `ast.parse()` will never raise `SyntaxError` for code that survived `compile()`.

## Steps

1. In `v2_eval_helpers.py`:
   - `extract_value`: after the `Undefined` check, add a `None` check that returns a skip signal (`SkippedReason.extraction_failed`) with a descriptive message.
   - `check_required_vars`: after the `Undefined` check, add a `None` check that returns a skip signal.
   - Update the docstring for `check_required_vars` to mention `None`.

2. In `eval.py` `validate_output_fields`:
   - In the V1 branch (after the V2 early-return, after confirming `parent_eval` exists), add a guard: if `self.output is None` and `self.skipped_reason is None`, raise `ValueError("V1 EvalRun requires output to be set")`.

3. In `eval.py` `CodeEvalProperties.validate_code`:
   - Remove the `except SyntaxError: pass` block (lines ~223-224), leaving the `try` body (`ast.parse` + function check + raise) to run without a catch.

4. Write tests in `libs/core/kiln_ai/adapters/eval/test_v2_eval_helpers.py` (new file) for `extract_value` and `check_required_vars` None-handling.

5. Add tests in `libs/core/kiln_ai/datamodel/test_eval_model.py` for the V1 `output is None` guard and the dead `SyntaxError` removal.

## Tests

- `test_extract_value_none_result_skips`: expression resolves to `None` -> returns skip signal.
- `test_extract_value_undefined_skips`: expression resolves to `Undefined` -> returns skip signal (existing behavior).
- `test_extract_value_valid_result`: expression resolves to a real value -> returns value with no skip.
- `test_extract_value_default_final_message`: `None` expression -> returns `final_message`.
- `test_check_required_vars_none_skips`: required_var resolves to `None` -> returns skip.
- `test_check_required_vars_undefined_skips`: required_var resolves to `Undefined` -> returns skip.
- `test_check_required_vars_all_present`: all vars resolve to non-None -> passes.
- `test_check_reference_key_value_is_none_skips`: reference_data key exists but value is `None` -> skip.
- `test_v1_eval_run_output_none_raises`: V1 EvalRun with `output=None` raises `ValueError`.
- `test_v1_eval_run_output_none_skipped_allowed`: V1 EvalRun with `output=None` but `skipped_reason` set -> allowed.
- `test_code_eval_no_syntax_error_catch`: `CodeEvalProperties` with valid code that has no `score` function raises `ValueError` (confirms `ast.parse` path works without the dead catch).
