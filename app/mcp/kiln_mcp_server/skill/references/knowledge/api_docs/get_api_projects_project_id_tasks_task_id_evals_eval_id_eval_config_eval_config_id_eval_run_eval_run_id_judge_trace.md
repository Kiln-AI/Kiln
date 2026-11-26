# Get Eval Run Judge Trace

**GET /api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/eval_config/{eval_config_id}/eval_run/{eval_run_id}/judge_trace**

**Tags:** Evals

Get the judge's full conversation for one eval run: system prompt, judge prompt, replies.

Null for runs whose judge called no model, and for runs recorded before
judge traces were saved.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|task_id|string|Yes|The unique identifier of the task within the project.|
|eval_id|string|Yes|The unique identifier of the eval.|
|eval_config_id|string|Yes|The unique identifier of the eval configuration.|
|eval_run_id|string|Yes|The unique identifier of the eval run.|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|value|one of: array of one of: object, object, object, object, object, object or null||

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
