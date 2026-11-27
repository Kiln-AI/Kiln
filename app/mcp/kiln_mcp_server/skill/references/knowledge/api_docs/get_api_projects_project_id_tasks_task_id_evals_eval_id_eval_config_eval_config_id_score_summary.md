# Get Run Config Score Summary

**GET /api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/eval_config/{eval_config_id}/score_summary**

**Tags:** Evals

Get one judge's mean scores on the eval's test split, for every run config of
the task.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|task_id|string|Yes|The unique identifier of the task within the project.|
|eval_id|string|Yes|The unique identifier of the eval.|
|eval_config_id|string|Yes|The unique identifier of the eval configuration.|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|results|object|Scores keyed by run_config_id then output_score_id.|
|run_config_percent_complete|object|Percent of dataset processed per run config.|
|dataset_size|integer|Total size of the eval dataset.|

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
