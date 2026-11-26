# Start Data Guide Job

**POST /api/projects/{project_id}/tasks/{task_id}/copilot/data_guide_job/start**

**Tags:** Copilot

Kick off the input data guide draft job on kiln_server and return its
job id. The job summarizes and aggregates the heterogeneous list of
input examples (manual entries, existing task runs, uploaded text
documents) into a draft guide.

The job runs in the background so the user can leave the page and come
back. The web UI polls `.../data_guide_job/{job_id}/status` and, once
the job succeeds, fetches `.../data_guide_job/{job_id}/result` and
generates preview inputs locally via the existing
`/data_gen_guide_preview` flow.

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
|input_examples|array of string|Yes|Heterogeneous list of input examples — short manual entries, the input portion of selected task runs, or full text of uploaded text documents (txt, md, csv). Every entry is a string and is treated as a candidate reference input regardless of source.|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|job_id|string|Identifier for the started data guide draft job.|

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
