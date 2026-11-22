# Delete Extraction

**DELETE /api/projects/{project_id}/documents/{document_id}/extractions/{extraction_id}**

**Tags:** Documents

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|document_id|string|Yes|The unique identifier of the document.|
|extraction_id|string|Yes|The unique identifier of the extraction.|

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
