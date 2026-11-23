# Get Eval Config Comparison Summary

**GET /api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/eval_configs_score_summary**

**Tags:** Evals

Compare an eval's judges against the human ratings of its golden set: how
well each judge agrees.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|task_id|string|Yes|The unique identifier of the task within the project.|
|eval_id|string|Yes|The unique identifier of the eval.|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|results|object|Correlation results keyed by eval_config_id then output_score_id.|
|eval_config_percent_complete|object|Percent of dataset processed per eval config.|
|dataset_size|integer|Total size of the eval config comparison dataset.|
|fully_rated_count|integer|Number of fully rated dataset items.|
|partially_rated_count|integer|Number of partially rated dataset items.|
|not_rated_count|integer|Number of unrated dataset items.|

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
