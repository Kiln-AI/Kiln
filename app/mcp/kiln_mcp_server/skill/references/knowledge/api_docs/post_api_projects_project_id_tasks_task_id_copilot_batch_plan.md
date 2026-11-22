# Batch Plan

**POST /api/projects/{project_id}/tasks/{task_id}/copilot/batch_plan**

**Tags:** Copilot

Plan a synthetic batch: turn the user's guidance + count into one
tailored prompt per input (plus a user-facing summary). Requires a
connected Kiln Pro / Copilot key (connection only, no paid tier).

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|task_id|string|Yes|The unique identifier of the task within the project.|

### Request Body

**Content Type:** `application/json`

|Field|Type|Required|Description|
|-|-|-|-|
|guidance|string|No|User guidance describing this batch (distribution, focus, edge cases).|
|count|integer|Yes|Number of inputs to plan — the planner returns one prompt per input. 1.0-200.0|
|data_guide|one of: string or null|No|The task's input data guide (input profile) to include, or null to omit.|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|prompts|array of string|One tailored prompt per input; length equals the requested count.|
|summary|string|A short, user-facing overview of the planned batch.|

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
