# Edit Run Tags

**POST /api/projects/{project_id}/tasks/{task_id}/runs/edit_tags**

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
|run_ids|array of string|Yes|The list of task run IDs to edit.|
|add_tags|one of: array of string or null|No|Tags to add to the task runs.|
|remove_tags|one of: array of string or null|No|Tags to remove from the task runs.|

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
