# List Documents

**GET /api/projects/{project_id}/documents**

**Tags:** Documents

List the documents in the project's library, optionally only those with given
tags.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|

### Query Parameters

|Name|Type|Required|Default|Description|
|-|-|-|-|-|
|tags|one of: string or null|No||Comma-separated list of tags to filter by.|

## Responses

### 200 OK

Successful Response

**Body:** array of Document

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### Document

A document uploaded to a project for extraction and RAG.

|Field|Type|Required|Description|
|-|-|-|-|
|v|integer|No|Schema version for migration support.|
|id|one of: string or null|No|Unique identifier for this record.|
|path|one of: string or null|No|File system path where the record is stored.|
|created_at|string|No|Timestamp when the model was created. Timezone-aware; stores the writer's local offset. Format: date-time|
|created_by|string|No|User ID of the creator.|
|name|string|Yes|A name to identify the document. Should not be changed after creation. 1-120 chars|
|name_override|one of: string or null|No|A friendly name to identify the document. This is used for display purposes and can be different from the name.|
|description|string|Yes|A description for the file|
|original_file.filename|string|Yes|The filename of the file|
|original_file.size|integer|Yes|The size of the file in bytes|
|original_file.mime_type|string|Yes|The MIME type of the file|
|original_file.attachment|object|Yes|The attachment to the file|
|kind|string|Yes|The kind of content a document contains. One of: document, image, video, audio|
|tags|array of string|No|Tags for the document. Tags are used to categorize documents for filtering and reporting.|
|model_type|string|Yes||
|friendly_name|string|Yes||

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
