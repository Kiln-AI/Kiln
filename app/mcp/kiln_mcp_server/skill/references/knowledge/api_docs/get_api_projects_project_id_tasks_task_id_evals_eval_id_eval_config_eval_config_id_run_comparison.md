# Run Run Config Comparison

**GET /api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/eval_config/{eval_config_id}/run_comparison**

**Tags:** Evals

Run a specific eval config against one or more run configs and stream progress via SSE. Executes model runs and scores them.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|task_id|string|Yes|The unique identifier of the task within the project.|
|eval_id|string|Yes|The unique identifier of the eval.|
|eval_config_id|string|Yes|The unique identifier of the eval configuration.|

### Query Parameters

|Name|Type|Required|Default|Description|
|-|-|-|-|-|
|run_config_ids|array of string|No|[]|The list of run configuration IDs to evaluate.|
|all_run_configs|boolean|No|False|Whether to evaluate all run configurations for the task.|

## Responses

### 200 OK

Successful Response

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
