# Ephemeral Split Document

**POST /api/projects/{project_id}/extractor_configs/{extractor_config_id}/documents/{document_id}/ephemeral_split**

**Tags:** Documents

Return chunks for a document extraction using FixedWindowChunker without persisting.

If chunk_size is None, return a single chunk with the full extraction output.
chunk_overlap defaults to 0 when not provided.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|extractor_config_id|string|Yes|The unique identifier of the extractor configuration.|
|document_id|string|Yes|The unique identifier of the document.|

### Request Body

**Content Type:** `application/json`

|Field|Type|Required|Description|
|-|-|-|-|
|chunk_size|one of: integer or null|No|The size of each chunk in tokens. If None, return a single chunk with the full extraction output.|
|chunk_overlap|one of: integer or null|No|The overlap between chunks in tokens. If None, use the default overlap for the chunker.|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|chunks|array of EphemeralSplitChunk|The resulting chunks.|

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### EphemeralSplitChunk

A single chunk from an ephemeral split.

|Field|Type|Required|Description|
|-|-|-|-|
|id|string|Yes|The chunk index as a string.|
|text|string|Yes|The text content of the chunk.|

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
