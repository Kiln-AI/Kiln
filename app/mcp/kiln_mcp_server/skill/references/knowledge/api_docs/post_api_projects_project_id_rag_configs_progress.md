# Get Rag Config Progress

**POST /api/projects/{project_id}/rag_configs/progress**

**Tags:** Documents

Get how far the index of each RAG config is built, for some or all of the
project's RAG configs.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|

### Request Body

**Content Type:** `application/json`

|Field|Type|Required|Description|
|-|-|-|-|
|rag_config_ids|one of: array of string or null|No|The RAG config ids to get progress for, if left empty, progress for all RAG configs in the project will be returned|

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
