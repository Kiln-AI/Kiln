# Data Guide Job Result

**GET /api/projects/{project_id}/tasks/{task_id}/copilot/data_guide_job/{job_id}/result**

**Tags:** Copilot

Return the draft guide markdown produced by a completed data guide
draft job. The web UI calls this once the job status is `succeeded`.

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
|draft_guide|string|Full draft input data guide markdown.|

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
