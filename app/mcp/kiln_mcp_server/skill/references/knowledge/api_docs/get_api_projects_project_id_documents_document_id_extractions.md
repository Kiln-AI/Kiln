# Get Extractions

**GET /api/projects/{project_id}/documents/{document_id}/extractions**

**Tags:** Documents

List a document's extractions, one per extractor config that ran on it.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|document_id|string|Yes|The unique identifier of the document.|

## Responses

### 200 OK

Successful Response

**Body:** array of ExtractionSummary

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### ExtractionSummary

A summary of an extraction result.

|Field|Type|Required|Description|
|-|-|-|-|
|id|string|Yes|The extraction ID.|
|created_at|string|Yes|When the extraction was created. Format: date-time|
|created_by|string|Yes|The user who created the extraction.|
|source|string|Yes|The source type of the extraction.|
|output_content|string|Yes|The extracted text content.|
|extractor.id|string|Yes|The extractor config ID.|
|extractor.name|string|Yes|The name of the extractor config.|
|extractor.description|one of: string or null|No|The description of the extractor config.|
|extractor.output_format|string|Yes|The output format for extraction results. One of: text/plain, text/markdown|
|extractor.passthrough_mimetypes|array of string|Yes|MIME types that bypass extraction and return the file content as-is.|
|extractor.extractor_type|string|Yes|The type of extractor used to process documents. One of: litellm|
|output_content_truncated|boolean|Yes|Whether the output content was truncated.|

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
