# Generate Prompt

**GET /api/projects/{project_id}/tasks/{task_id}/gen_prompt/{prompt_id}**

**Tags:** Prompts

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|task_id|string|Yes|The unique identifier of the task within the project.|
|prompt_id|string|Yes|The prompt generator ID to use.|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|prompt|string||
|prompt_id|string||
|chain_of_thought_instructions|one of: string or null||

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
