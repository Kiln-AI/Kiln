---
status: complete
---

# Phase 3: Rename legacy dispatcher + dedupe dispatch tests

## Overview

Rename `eval_adapter_from_type` to `legacy_eval_adapter_from_type` across the entire codebase to clearly signal it is the legacy (V1) dispatch path. Update the V2-branch error message to point callers at `v2_eval_adapter_from_config`. Then deduplicate the now-overlapping dispatch tests in `test_registry.py` that were introduced alongside the V2 dispatch tests in `test_v2_dispatch_and_contract.py`.

## Steps

### 5.2 -- Rename legacy dispatcher

1. **registry.py**: Rename `def eval_adapter_from_type` to `def legacy_eval_adapter_from_type`. Update docstring. Update the V2 branch error message to read: `"V2 eval configs should use v2_eval_adapter_from_config(), not legacy_eval_adapter_from_type()"`.
2. **eval_runner.py**: Update the import and the one call site at line 311.
3. **test_registry.py**: Update the import and all 4 call sites inside `TestEvalAdapterFromType`.
4. **test_v2_dispatch_and_contract.py**: Update the import and the one call site in `test_legacy_dispatch_unchanged`.
5. **test_eval_runner.py**: Update all 10 mock patch strings from `"kiln_ai.adapters.eval.eval_runner.eval_adapter_from_type"` to `"kiln_ai.adapters.eval.eval_runner.legacy_eval_adapter_from_type"`.

### 6.2 -- Dedupe overlapping dispatch tests in test_registry.py

The `TestEvalAdapterFromType` class in `test_registry.py` has two pairs of duplicate tests:
- `test_v2_raises_not_implemented` and `test_legacy_dispatch_v2_raises` both test the same V2 error path.
- `test_legacy_types_return_geval` (parametrized) and `test_legacy_dispatch_unchanged` (loop) both test legacy types returning GEval.

After the rename, consolidate:
- Remove `test_legacy_dispatch_v2_raises` (exact dupe of `test_v2_raises_not_implemented`).
- Remove `test_legacy_dispatch_unchanged` (covered by the parametrized `test_legacy_types_return_geval`).
- Update `test_v2_raises_not_implemented` match string to reflect the new error message.

The `test_v2_dispatch_and_contract.py::TestV2Dispatch::test_legacy_dispatch_unchanged` is not a dupe -- it is the only legacy-dispatch test in that file and provides coverage that the legacy path still works when testing from the V2 dispatch perspective. Keep it.

## Tests

- Existing `test_legacy_types_return_geval` (parametrized) covers both g_eval and llm_as_judge returning GEval via the renamed function.
- Existing `test_v2_raises_not_implemented` covers the V2 branch error with updated match string pointing at `v2_eval_adapter_from_config`.
- All 10 mock-patched tests in `test_eval_runner.py` validate the renamed import path works correctly.
- `test_v2_dispatch_and_contract.py::test_legacy_dispatch_unchanged` validates the renamed function from the V2 test perspective.
