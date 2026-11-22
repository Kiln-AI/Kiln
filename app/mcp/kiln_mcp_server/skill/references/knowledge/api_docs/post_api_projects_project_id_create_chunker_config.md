# Create Chunker Config

**POST /api/projects/{project_id}/create_chunker_config**

**Tags:** Documents

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|

### Request Body

**Content Type:** `application/json`

|Field|Type|Required|Description|
|-|-|-|-|
|name|one of: string or null|No|A name for this entity.|
|description|one of: string or null|No|The description of the chunker config|
|chunker_type|string|Yes|The type of chunking algorithm to use. One of: fixed_window, semantic|
|properties|one of: SemanticChunkerPropertiesPublic, FixedWindowChunkerPropertiesPublic|Yes||
|provenance|one of: KilnArtifactProvenance or null|No|Provenance: why this chunker config exists and what it was derived from.|

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
|name|string|A name to identify the chunker config. 1-120 chars|
|description|one of: string or null|The description of the chunker config|
|chunker_type|string|The type of chunking algorithm to use. One of: fixed_window, semantic|
|properties|one of: SemanticChunkerProperties, FixedWindowChunkerPropertiesPublic|Properties to be used to execute the chunker config. This is chunker_type specific and should serialize to a json dict.|
|provenance|one of: KilnArtifactProvenance or null|Why this artifact exists and what it was derived from.|
|model_type|string||

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### SemanticChunkerPropertiesPublic

|Field|Type|Required|Description|
|-|-|-|-|
|chunker_type|string|Yes|The type of the chunker. One of: semantic|
|embedding_config_id|string|Yes|The embedding config to use for the RAG workflow.|
|buffer_size|integer|Yes|The buffer size to use for the chunker.|
|breakpoint_percentile_threshold|integer|Yes|The breakpoint percentile threshold to use for the chunker.|

### FixedWindowChunkerPropertiesPublic

|Field|Type|Required|Description|
|-|-|-|-|
|chunker_type|string|Yes|The type of the chunker. One of: fixed_window|
|chunk_size|integer|Yes|The chunk size to use for the chunker.|
|chunk_overlap|integer|Yes|The chunk overlap to use for the chunker.|

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

### SemanticChunkerProperties

|Field|Type|Required|Description|
|-|-|-|-|
|chunker_type|string|Yes|One of: semantic|
|embedding_config_id|string|Yes||
|buffer_size|integer|Yes||
|breakpoint_percentile_threshold|integer|Yes|>=0.0|
|include_metadata|boolean|Yes||
|include_prev_next_rel|boolean|Yes||

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
