# Get Default LLM Judge Prompt

**GET /api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/default_llm_judge_prompt**

**Tags:** Evals

Get the default LLM judge prompt and system prompt for an eval, and the
reference keys it needs.

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
|judge_prompt|string||
|system_prompt|string||
|reference_keys|array of string|Reference data keys the server will require of a judge for this eval, derived the same way `create_llm_judge_config` derives them. Returned so the builder can offer a place to supply them when testing, rather than re-deriving the rule client-side from the prompt's text.|

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
