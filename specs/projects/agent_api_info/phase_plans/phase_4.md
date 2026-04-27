---
status: draft
---

# Phase 4: `eval_results_summary` endpoint + response models

## Overview

Add the `eval_results_summary` endpoint to `eval_api.py`. This endpoint fans out the existing `compute_score_summary` (extracted in Phase 3) across every eval x eval_config for a task, returning a single aggregated response. Response models are defined inline. The endpoint handles empty dataset filters gracefully (returns empty summary instead of 400).

## Steps

1. Add response models to `eval_api.py` (inline, near existing models):

```python
class EvalResultsSummaryRunConfigRef(BaseModel):
    id: ID_TYPE
    name: str

class EvalResultsSummaryEvalConfig(BaseModel):
    eval_config_id: ID_TYPE
    eval_config_name: str
    is_default: bool
    summary: EvalResultSummary

class EvalResultsSummaryEval(BaseModel):
    eval_id: ID_TYPE
    eval_name: str
    default_judge_config_id: ID_TYPE | None
    run_configs: list[EvalResultsSummaryRunConfigRef]
    eval_configs: list[EvalResultsSummaryEvalConfig]

class EvalResultsSummaryResponse(BaseModel):
    evals: list[EvalResultsSummaryEval]
```

2. Add the `eval_results_summary` route inside `connect_evals_api(app)`:

```python
@app.get(
    "/api/projects/{project_id}/tasks/{task_id}/eval_results_summary",
    summary="Get Eval Results Summary",
    tags=["Evals"],
    openapi_extra=ALLOW_AGENT,
)
async def get_eval_results_summary(project_id, task_id) -> EvalResultsSummaryResponse:
```

Route logic:
- Load task and task_run_configs once
- Cache expected_dataset_ids per eval_set_filter_id
- Loop over task.evals() x eval.configs()
- For each eval_config, call compute_score_summary or return empty summary if no dataset ids
- Build and return EvalResultsSummaryResponse

3. Regenerate the OpenAPI schema (`generate_schema.sh`)

## Tests

- `test_eval_results_summary_happy_path`: task with 2 evals x 2 configs x 3 run_configs. Verify nested shape and score values match expectations.
- `test_eval_results_summary_behavioral_equivalence`: for each (eval, eval_config), assert that the summary in eval_results_summary matches what /score_summary returns for the same pair.
- `test_eval_results_summary_empty_filter`: eval with filter matching zero runs returns empty summary (dataset_size=0, results={}, run_config_percent_complete={}) instead of 400.
- `test_eval_results_summary_is_default`: verify is_default is true when eval_config_id == eval.current_config_id, false otherwise.
- `test_eval_results_summary_no_evals`: task with no evals returns `{"evals": []}`.
- `test_eval_results_summary_single_task_runs_call`: instrument task.runs() call counter, assert called once across multiple evals x configs (perf sanity).
