# Create Feedback

**POST /api/projects/{project_id}/tasks/{task_id}/runs/{run_id}/feedback**

**Tags:** Feedback

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|task_id|string|Yes|The unique identifier of the task within the project.|
|run_id|string|Yes|The unique identifier of the task run.|

### Request Body

**Content Type:** `application/json`

|Field|Type|Required|Description|
|-|-|-|-|
|feedback|string|Yes|Free-form text feedback on the task run. >=1 chars|
|source|string|Yes|Where a piece of feedback originated.

This is an append-only enum: new sources can be added freely, but existing
values must never be removed or renamed so that older persisted data
continues to load. One of: run-page, spec-feedback|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|v|integer|Schema version for migration support.|
|id|one of: string or null|Unique identifier for this record.|
|path|one of: string or null|File system path where the record is stored.|
|created_at|string|Timestamp when the model was created. Timezone-aware; stores the writer's local offset. Format: date-time|
|created_by|string|User ID of the creator.|
|feedback|string|Free-form text feedback on the task run. >=1 chars|
|source|string|Where a piece of feedback originated.

This is an append-only enum: new sources can be added freely, but existing
values must never be removed or renamed so that older persisted data
continues to load. One of: run-page, spec-feedback|
|model_type|string||

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
