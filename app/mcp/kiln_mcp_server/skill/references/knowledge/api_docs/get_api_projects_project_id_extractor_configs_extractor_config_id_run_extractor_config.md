# Run Extractor Config

**GET /api/projects/{project_id}/extractor_configs/{extractor_config_id}/run_extractor_config**

**Tags:** Documents

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|extractor_config_id|string|Yes|The unique identifier of the extractor configuration.|

### Query Parameters

|Name|Type|Required|Default|Description|
|-|-|-|-|-|
|tags|one of: string or null|No||Comma-separated list of tags to filter documents by.|
|document_ids|one of: string or null|No||Comma-separated list of document ids to filter by. Combined (AND) with tags when both are set.|

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
