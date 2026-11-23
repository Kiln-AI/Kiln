# Create Vector Store Config

**POST /api/projects/{project_id}/create_vector_store_config**

**Tags:** Documents

Create a vector store config: the index type and search settings for RAG.

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
|description|one of: string or null|No|The description of the vector store config|
|store_type|string|Yes|The type of vector store backend. One of: lancedb_fts, lancedb_hybrid, lancedb_vector|
|properties|one of: LanceDBConfigFTSPropertiesPublic, LanceDBConfigFTSPropertiesPublic, LanceDBConfigFTSPropertiesPublic|Yes|The properties of the vector store config, specific to the selected store_type.|
|provenance|one of: KilnArtifactProvenance or null|No|Provenance: why this vector store config exists and what it was derived from.|

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
|name|string|A name for your own reference to identify the vector store config. 1-120 chars|
|description|one of: string or null|A description for your own reference.|
|store_type|string|The type of vector store backend. One of: lancedb_fts, lancedb_hybrid, lancedb_vector|
|properties|one of: LanceDBConfigFTSProperties, LanceDBConfigVectorProperties, LanceDBConfigVectorProperties|The properties of the vector store config, specific to the selected store_type.|
|provenance|one of: KilnArtifactProvenance or null|Why this artifact exists and what it was derived from.|
|model_type|string||

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### LanceDBConfigFTSPropertiesPublic

|Field|Type|Required|Description|
|-|-|-|-|
|similarity_top_k|integer|Yes|The number of results to return from the vector store.|

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

### LanceDBConfigFTSProperties

|Field|Type|Required|Description|
|-|-|-|-|
|store_type|string|Yes|One of: lancedb_fts|
|similarity_top_k|integer|Yes||
|overfetch_factor|integer|Yes||
|vector_column_name|string|Yes||
|text_key|string|Yes||
|doc_id_key|string|Yes||

### LanceDBConfigVectorProperties

|Field|Type|Required|Description|
|-|-|-|-|
|store_type|string|Yes|One of: lancedb_vector|
|similarity_top_k|integer|Yes||
|overfetch_factor|integer|Yes||
|vector_column_name|string|Yes||
|text_key|string|Yes||
|doc_id_key|string|Yes||
|nprobes|integer|Yes||

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
