# Get Chunker Configs

**GET /api/projects/{project_id}/chunker_configs**

**Tags:** Documents

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|

## Responses

### 200 OK

Successful Response

**Body:** array of ChunkerConfig

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### SemanticChunkerProperties

|Field|Type|Required|Description|
|-|-|-|-|
|chunker_type|string|Yes|One of: semantic|
|embedding_config_id|string|Yes||
|buffer_size|integer|Yes||
|breakpoint_percentile_threshold|integer|Yes|>=0.0|
|include_metadata|boolean|Yes||
|include_prev_next_rel|boolean|Yes||

### FixedWindowChunkerProperties

|Field|Type|Required|Description|
|-|-|-|-|
|chunker_type|string|Yes|One of: fixed_window|
|chunk_overlap|integer|Yes|>=0.0|
|chunk_size|integer|Yes||

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

### ChunkerConfig

Configuration for chunking extracted documents into smaller pieces.

|Field|Type|Required|Description|
|-|-|-|-|
|v|integer|No|Schema version for migration support.|
|id|one of: string or null|No|Unique identifier for this record.|
|path|one of: string or null|No|File system path where the record is stored.|
|created_at|string|No|Timestamp when the model was created. Timezone-aware; stores the writer's local offset. Format: date-time|
|created_by|string|No|User ID of the creator.|
|name|string|Yes|A name to identify the chunker config. 1-120 chars|
|description|one of: string or null|No|The description of the chunker config|
|chunker_type|string|Yes|The type of chunking algorithm to use. One of: fixed_window, semantic|
|properties|one of: SemanticChunkerProperties, FixedWindowChunkerProperties|Yes|Properties to be used to execute the chunker config. This is chunker_type specific and should serialize to a json dict.|
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
