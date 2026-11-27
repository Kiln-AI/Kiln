# Get Job Errors

**GET /api/jobs/{id}/errors**

**Tags:** Jobs

Get the errors a background job logged for its items. Empty when the job is
unknown or had none.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|id|string|Yes|The job id.|

### Query Parameters

|Name|Type|Required|Default|Description|
|-|-|-|-|-|
|run_id|one of: string or null|No||Read the error log for a specific past run id.|

## Responses

### 200 OK

Successful Response

**Body:** array of object

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
