---
status: complete
---

# Phase 10: API consistency fixes

## Overview

Fix four API-layer issues in `eval_api.py` and its test file: de-leak two V1-specific 400 messages (2.2a), clean up raw Pydantic ValidationError exposure for V2 configs (2.3), move lazy imports to top-level (2.6), and fix `test_nothing_persisted` to assert against the real data-model directory (6.8).

## Steps

1. **2.2a — De-leak 400 messages.** In `get_eval_progress` and `get_eval_config_score_summary`, replace `"This eval does not have a V1 eval set filter."` with `"This endpoint isn't supported for this eval type."` (two occurrences).

2. **2.3 — Clean V2 validation 400.** In `create_eval_config`, change the `except (ValueError, ValidationError)` handler to produce a clean message for `ValidationError` matching the V1 style: `"Invalid properties for eval config type '{type}'."`. Keep `ValueError` messages as-is (they are already clean).

3. **2.6 — Move lazy imports to top-level.** Move the four lazy imports (`project_from_id` x2, `grant_code_eval_trust`, `is_code_eval_trusted`) from inside the two trust endpoint functions to the module's top-level import block. No import cycle exists (verified: neither `v2_eval_code_eval` nor `project_api` imports `eval_api`).

4. **6.8 — Fix `test_nothing_persisted`.** Replace `tmp_path.rglob("*")` with `mock_v2_eval.path.parent.rglob("*")` so the test asserts against the eval's actual on-disk directory (where EvalConfig children would be persisted), not a potentially-unrelated temp directory.

## Tests

- `test_create_eval_config_invalid_v2_properties`: new test asserting that a malformed V2 config body returns 400 with the clean message (not raw Pydantic output).
- Existing `test_nothing_persisted`: updated to assert against `mock_v2_eval.path.parent`.
- Existing tests for `get_eval_progress`, `get_eval_config_score_summary`, and trust endpoints remain passing.
