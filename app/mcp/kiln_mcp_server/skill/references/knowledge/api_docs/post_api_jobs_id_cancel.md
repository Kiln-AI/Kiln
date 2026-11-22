# Cancel Job

**POST /api/jobs/{id}/cancel**

**Tags:** Jobs

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|id|string|Yes|The job id.|

## Responses

### 202 Accepted

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
