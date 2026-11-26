# List Extractions for Extractor Config

**GET /api/projects/{project_id}/extractor_configs/{extractor_config_id}/extractions**

**Tags:** Documents

Return mapping of document id to list of extractions for the given extractor config id.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|extractor_config_id|string|Yes|The unique identifier of the extractor configuration.|

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
