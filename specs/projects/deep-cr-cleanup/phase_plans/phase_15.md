---
status: complete
---

# Phase 15: Frontend test hygiene

## Overview

Improve frontend test robustness and reduce duplication across three areas: (1) extend the with/without `eval_config` renderer test pattern from `exact_match_result` to the other 7 V2 result renderers, (2) parametrize repetitive error-path tests in `v2_eval_api.test.ts`, (3) derive the `toHaveLength` count in `registry.test.ts` from the expected-types array.

## Steps

1. **6.7 — Result renderer with/without eval_config tests**: For each of the 7 non-exact_match renderers (`pattern_match_result`, `contains_result`, `set_check_result`, `tool_call_check_result`, `step_count_check_result`, `llm_judge_result`, `code_eval_result`), add a test that renders with scores but **without** `eval_config` and asserts the config-specific detail section is absent. This confirms the `extractV2Props` null-props path renders safely for each renderer (existing tests already cover the with-config path).

2. **6.13 — Parametrize v2_eval_api error paths**: The 4 API functions each have 2 error-path tests (message field, detail fallback) = 8 tests with identical structure. Consolidate using `it.each` with a table of `[description, setupMock, callFn, expectedMessage]` entries, preserving every assertion.

3. **6.14 — Derive registry count**: Replace the hardcoded `toHaveLength(8)` in `registry.test.ts` with a value derived from the `expected` array already defined in the test.

## Tests

- `pattern_match_result.test.ts`: "does not show config details when eval_config is null" — renders with scores only, asserts Pattern:/Mode: not present
- `contains_result.test.ts`: "does not show config details when eval_config is null" — renders with scores only, asserts Substring:/Mode: not present
- `set_check_result.test.ts`: "does not show config details when eval_config is null" — renders with scores only, asserts Expected:/mode labels not present
- `tool_call_check_result.test.ts`: "does not show config details when eval_config is null" — renders with scores only, asserts Tools:/match mode labels not present
- `step_count_check_result.test.ts`: "does not show config details when eval_config is null" — renders with scores only, asserts count type/range not present
- `llm_judge_result.test.ts`: "does not show config details when eval_config is null" — renders with scores only, asserts Model: not present
- `code_eval_result.test.ts`: "does not show config details when eval_config is null" — renders with scores only, asserts Timeout: not present
- `v2_eval_api.test.ts`: 8 error-path parametrized tests — all existing assertions preserved, just deduplicated via `it.each`
- `registry.test.ts`: count derived from array — test still validates correct length
