# Get Extraction

**GET /api/projects/{project_id}/documents/{document_id}/extractions/{extraction_id}**

**Tags:** Documents

Get one extraction of a document, with its text.

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

|Field|Type|Description|
|-|-|-|
|id|string|The extraction ID.|
|created_at|string|When the extraction was created. Format: date-time|
|created_by|string|The user who created the extraction.|
|source|string|The source type of the extraction.|
|output_content|string|The extracted text content.|
|extractor.id|string|The extractor config ID.|
|extractor.name|string|The name of the extractor config.|
|extractor.description|one of: string or null|The description of the extractor config.|
|extractor.output_format|string|The output format for extraction results. One of: text/plain, text/markdown|
|extractor.passthrough_mimetypes|array of string|MIME types that bypass extraction and return the file content as-is.|
|extractor.extractor_type|string|The type of extractor used to process documents. One of: litellm|
|output_content_truncated|boolean|Whether the output content was truncated.|

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
