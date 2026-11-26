# Data Guide Job Status

**GET /api/projects/{project_id}/tasks/{task_id}/copilot/data_guide_job/{job_id}/status**

**Tags:** Copilot

Return the current status of a data guide draft job (e.g. running,
succeeded, failed, cancelled). The web UI polls this while showing the
analyzing animation and the task-wide progress widget.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|task_id|string|Yes|The unique identifier of the task within the project.|
|job_id|string|Yes|The data guide draft job identifier.|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|status|string|Current job status (e.g. running, succeeded, failed, cancelled).|

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
