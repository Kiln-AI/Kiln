# Get Eval Results Summary

**GET /api/projects/{project_id}/tasks/{task_id}/eval_results_summary**

**Tags:** Evals

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|task_id|string|Yes|The unique identifier of the task within the project.|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|evals_by_id|object|Eval metadata keyed by eval ID.|
|run_configs_by_id|object|Run config metadata keyed by run config ID.|
|scores_by_run_config_by_eval|object|Results keyed by run config ID then eval ID.|

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
