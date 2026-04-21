---
status: draft
---

# Phase 3: Extract `compute_score_summary` from `/score_summary` handler

## Overview

Behavior-preserving refactor of `eval_api.py`. Extract the aggregation logic (lines 1034-1110) from the `get_eval_config_score_summary` handler into a standalone module-level function `compute_score_summary(...)`. The existing route becomes a thin wrapper that fetches data and delegates. Existing tests lock in behavioral parity.

## Steps

1. Define `compute_score_summary` as a module-level function in `eval_api.py`, above `connect_eval_api`:

```python
def compute_score_summary(
    eval: Eval,
    eval_config: EvalConfig,
    task_run_configs: list[TaskRunConfig],
    expected_dataset_ids: set[ID_TYPE],
) -> EvalResultSummary:
```

The body is the existing lines 1034-1110, with `task_runs_configs` renamed to `task_run_configs` for consistency, and using the function parameters instead of local variables from the handler.

2. Slim down `get_eval_config_score_summary` to ~10 lines: fetch task, eval, eval_config, task_run_configs, compute expected_dataset_ids, guard empty, call `compute_score_summary`.

## Tests

- No new tests needed. This is a behavior-preserving refactor; the existing `test_get_eval_config_score_summary` test locks in the current behavior. If the extraction breaks anything, that test fails.
- Verify all existing tests still pass after the refactor.
