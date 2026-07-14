---
status: complete
---

# Phase 7: Backend test hygiene

## Overview

Deduplicate test helpers and improve test coverage/quality across the eval test suite. Five items: extract shared stub classes (6.1), extract shared config/input factory fixtures (6.3), convert a test from `run_until_complete` to `@pytest.mark.asyncio` (6.5), add a test for SkippedReason validity (5.5), and add provenance documentation for `test_g_eval_data.py` (6.12).

## Steps

1. **6.1 — Shared StubV2Eval / SkippingStubV2Eval**: Create `conftest.py` in `libs/core/kiln_ai/adapters/eval/` with the `StubV2Eval` and `SkippingStubV2Eval` classes. Remove the duplicate definitions from `test_v2_dispatch_and_contract.py` and `test_eval_runner.py`; import from conftest instead.

2. **6.3 — Shared `_make_config` / `_inp` fixture factory**: Add `make_v2_eval_config` and `make_eval_task_input` factory functions to the new `conftest.py`. These are generalized versions of the `_make_config`/`_inp` boilerplate duplicated across the 6 deterministic matcher test files (`test_v2_exact_match.py`, `test_v2_contains.py`, `test_v2_pattern_match.py`, `test_v2_set_check.py`, `test_v2_tool_call_check.py`, `test_v2_step_count_check.py`). Each test file adopts the shared factory, removing its local `_make_config`/`_inp`. Preserve each test's exact default `final_message` since some tests rely on specific defaults.

3. **6.5 — Convert `test_g_eval_raises_when_provider_lacks_logprobs`**: In `test_v2_eval_llm_judge.py`, convert the test from `asyncio.get_event_loop().run_until_complete(...)` to `@pytest.mark.asyncio` / `async def` / `await`.

4. **5.5 — Test runner emits valid SkippedReason values**: Add a new test that asserts every `skipped_reason` string literal the runner writes is a valid member of the `SkippedReason` enum. Inspect `eval_runner.py` for all `.value` usages.

5. **6.12 — Provenance docstring for `test_g_eval_data.py`**: The spec references a `test_g_eval_data/` directory but the fixture is a single `.py` file. Expand the existing header comment into a proper provenance docstring documenting what the fixture is, how it was generated, and how to regenerate it.

## Tests

- All existing tests in the 8 affected test files must continue to pass with identical behavior after the dedup refactors.
- **5.5**: `test_runner_skip_reasons_are_valid_enum_members` verifies all skip-path string values match `SkippedReason` members.
- **6.5**: The converted test still asserts `ValueError` with "logprobs support" match.
