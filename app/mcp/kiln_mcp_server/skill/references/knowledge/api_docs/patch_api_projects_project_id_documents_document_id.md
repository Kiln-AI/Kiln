# Patch Document

**PATCH /api/projects/{project_id}/documents/{document_id}**

**Tags:** Documents

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|document_id|string|Yes|The unique identifier of the document.|

### Request Body

**Content Type:** `application/json`

|Field|Type|Required|Description|
|-|-|-|-|
|name_override|one of: string or null|No|A name for this document.|
|description|one of: string or null|No|The description of the document|
|tags|one of: array of string or null|No|Tags for the document|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|v|integer|Schema version for migration support.|
|id|one of: string or null|Unique identifier for this record.|
|path|one of: string or null|File system path where the record is stored.|
|created_at|string|Timestamp when the model was created. Timezone-aware; stores the writer's local offset. Format: date-time|
|created_by|string|User ID of the creator.|
|name|string|A name to identify the document. Should not be changed after creation. 1-120 chars|
|name_override|one of: string or null|A friendly name to identify the document. This is used for display purposes and can be different from the name.|
|description|string|A description for the file|
|original_file.filename|string|The filename of the file|
|original_file.size|integer|The size of the file in bytes|
|original_file.mime_type|string|The MIME type of the file|
|original_file.attachment|object|The attachment to the file|
|kind|string|The kind of content a document contains. One of: document, image, video, audio|
|tags|array of string|Tags for the document. Tags are used to categorize documents for filtering and reporting.|
|model_type|string||
|friendly_name|string||

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
