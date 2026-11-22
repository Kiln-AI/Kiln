# Patch Extractor Config

**PATCH /api/projects/{project_id}/extractor_configs/{extractor_config_id}**

**Tags:** Documents

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|extractor_config_id|string|Yes|The unique identifier of the extractor configuration.|

### Request Body

**Content Type:** `application/json`

|Field|Type|Required|Description|
|-|-|-|-|
|name|one of: string or null|No|A name for this entity.|
|description|one of: string or null|No|The description of the extractor config|
|is_archived|one of: boolean or null|No|Whether the extractor config is archived|

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
