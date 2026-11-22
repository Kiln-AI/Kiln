# Bulk Upload Runs

**POST /api/projects/{project_id}/tasks/{task_id}/runs/bulk_upload**

**Tags:** Runs

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
|file|string|Yes|The CSV file containing run data to import.|
|splits|one of: string or null|No|JSON string mapping split names to numeric proportions (0-1).|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|success|boolean|Whether the import succeeded.|
|filename|string|The filename that was imported.|
|imported_count|integer|The number of task runs imported.|
|imported_conversation_count|one of: integer or null|The number of conversations imported. None for single-turn uploads; set for multiturn uploads (where one row = one conversation that materializes as multiple TaskRuns linked via parent_task_run_id).|

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
