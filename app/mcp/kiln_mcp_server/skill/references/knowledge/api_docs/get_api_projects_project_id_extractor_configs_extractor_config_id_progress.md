# Get Extraction Progress

**GET /api/projects/{project_id}/extractor_configs/{extractor_config_id}/progress**

**Tags:** Documents

Get how many of the project's documents an extractor config has extracted.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|extractor_config_id|string|Yes|The unique identifier of the extractor configuration.|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|document_count_total|integer|The total number of documents to extract.|
|document_count_successful|integer|The number of documents successfully extracted.|
|extractor_config|one of: ExtractorConfig or null|The extractor config used.|

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### LitellmExtractorConfigProperties

|Field|Type|Required|Description|
|-|-|-|-|
|extractor_type|string|Yes|One of: litellm|
|prompt_document|string|Yes||
|prompt_image|string|Yes||
|prompt_video|string|Yes||
|prompt_audio|string|Yes||

### KilnArtifactProvenance

Why this artifact exists and what it was derived from.

Written once at creation; immutable thereafter (enforced at the API layer).
Compile-time metadata for future agent sessions and humans — never shown to
runtime models (not part of any tool/prompt surface).

|Field|Type|Required|Description|
|-|-|-|-|
|notes|one of: string or null|No|Why this artifact exists: the problem/hypothesis it addresses, what changed vs. the derived_from_ids parents, what validation/evidence supports it (cite eval/run_config/trace IDs inline), and known limits. First line = one-sentence summary. Record observations with conditions, never universal rules. Max ~2000 chars.|
|derived_from_ids|array of one of: string or null|No|IDs of same-type sibling artifacts this one was derived from. Ordered: first = primary parent (the artifact this replaces or is a new version of); further entries = additional sources merged in. Empty = not derived. IDs resolve among siblings in the same parent scope only.|
|origin|one of: string or null|No|Whose judgment created this artifact. 'human': a person authored it directly OR an agent created it fulfilling a direct human request. 'agent': an agent created it autonomously. None: unknown/legacy. Required when this provenance is created; consumers must tolerate unknown values.|

### ExtractorConfig

Configuration for extracting content from documents using a specific model and prompts.

|Field|Type|Required|Description|
|-|-|-|-|
|v|integer|No|Schema version for migration support.|
|id|one of: string or null|No|Unique identifier for this record.|
|path|one of: string or null|No|File system path where the record is stored.|
|created_at|string|No|Timestamp when the model was created. Timezone-aware; stores the writer's local offset. Format: date-time|
|created_by|string|No|User ID of the creator.|
|name|string|Yes|A name to identify the extractor config. 1-120 chars|
|is_archived|boolean|No|Whether the extractor config is archived. Archived extractor configs are not shown in the UI and are not available for use.|
|description|one of: string or null|No|The description of the extractor config|
|model_provider_name|string|Yes|The name of the model provider to use for the extractor config.|
|model_name|string|Yes|The name of the model to use for the extractor config.|
|output_format|string|No|The output format for extraction results. One of: text/plain, text/markdown|
|passthrough_mimetypes|array of string|No|If the mimetype is in this list, the extractor will not be used and the text content of the file will be returned as is.|
|extractor_type|string|Yes|The type of extractor used to process documents. One of: litellm|
|properties|one of: LitellmExtractorConfigProperties|Yes|Properties to be used to execute the extractor config. This is extractor_type specific and should serialize to a json dict.|
|provenance|one of: KilnArtifactProvenance or null|No|Why this artifact exists and what it was derived from.|
|model_type|string|Yes||

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
