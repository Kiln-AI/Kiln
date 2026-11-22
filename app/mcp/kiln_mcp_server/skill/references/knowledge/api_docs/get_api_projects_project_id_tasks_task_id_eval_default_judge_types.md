# Get Default Judge Types

**GET /api/projects/{project_id}/tasks/{task_id}/eval_default_judge_types**

**Tags:** Evals

Map of eval ID to its default judge's type discriminator.

V2 configs report their properties type (e.g. "code_eval",
"llm_judge"); legacy configs report their config_type (e.g. "g_eval").
Evals with no default judge are omitted. Used by the evals list to
display each eval's type without fetching every config.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|task_id|string|Yes|The unique identifier of the task within the project.|

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
