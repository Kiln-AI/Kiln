---
status: complete
---

# Phase 8: V1 Coexistence Test Guard

## Overview

Add the A0.1 V1-regression guard tests (item 6.4, absorbing 5.10). These ensure that V1 evals continue to behave exactly as on `main` even after V2 additions. Test-only phase -- no production code changes.

## Existing Coverage from 42050a2

Commit `42050a2` already provides substantial coverage:

- **(a) V1 EvalRun new-fields -> None**: COVERED. `TestV1EvalRunCoexistence` verifies both in-memory defaults and disk round-trip for `eval_input_id`, `reference_data`, `skipped_reason`, `skipped_detail`.
- **(5.10) Misroute guard**: COVERED. `test_v1_properties_with_type_key_not_misrouted` and `test_v1_config_round_trip_with_type_key_in_properties` verify a V1 g_eval whose `properties` dict contains a `"type": "exact_match"` key is not misrouted into the V2 discriminated union.
- **(c) config_type=None model load**: PARTIALLY COVERED. `test_v1_config_from_dict_without_config_type_key` verifies model-level load defaults to g_eval -- but does not test running through the legacy runner.

## Gaps to Fill

### Gap (b): V1 config through legacy runner end-to-end

Add to `test_eval_runner.py`. Construct a real V1 g_eval EvalConfig and run it through `EvalRunner._run_legacy_job` (both `task_run_eval` and `eval_config_eval` modes), verifying:
- `legacy_eval_adapter_from_type` is called (not the V2 path)
- The resulting EvalRun has correct V1 shape (dataset_id set, eval_input_id=None, skipped_reason=None)

### Gap (c): V1 config_type omitted (legacy on-disk) runs through legacy runner

Add to `test_eval_runner.py`. Create an EvalConfig from a raw dict with no `config_type` key (simulating a legacy on-disk config), verify it dispatches through the legacy path and produces correct results.

### Gap (5.10 runner-level): misroute guard at dispatch level

The existing `test_v1_properties_with_type_key_not_misrouted` only tests model parsing. Add a test in `test_eval_runner.py` that constructs a V1 g_eval config whose properties contain `"type": "exact_match"` and verifies `run_job` routes it through `_run_legacy_job` (not `_run_v2_job`).

## Steps

1. Write phase plan (this file).
2. Add `TestV1LegacyRunnerCoexistence` class to `test_eval_runner.py` with tests for gaps (b), (c), and runner-level 5.10.
3. Run targeted tests + linting.

## Tests

- `test_v1_g_eval_dispatches_through_legacy_runner`: V1 g_eval config routes to `_run_legacy_job`, produces correct EvalRun.
- `test_v1_config_without_config_type_key_runs_through_legacy_runner`: Config from dict missing `config_type` defaults to g_eval and runs through legacy path.
- `test_v1_config_with_type_key_in_properties_not_misrouted_at_runner`: V1 g_eval config with `properties.type="exact_match"` routes to legacy path, not V2.
