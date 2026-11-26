# Get Vector Store Configs

**GET /api/projects/{project_id}/vector_store_configs**

**Tags:** Documents

List the project's vector store configs.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|

## Responses

### 200 OK

Successful Response

**Body:** array of VectorStoreConfig

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

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

### VectorStoreConfig

Configuration for a vector store used to index and search document embeddings.

|Field|Type|Required|Description|
|-|-|-|-|
|v|integer|No|Schema version for migration support.|
|id|one of: string or null|No|Unique identifier for this record.|
|path|one of: string or null|No|File system path where the record is stored.|
|created_at|string|No|Timestamp when the model was created. Timezone-aware; stores the writer's local offset. Format: date-time|
|created_by|string|No|User ID of the creator.|
|name|string|Yes|A name for your own reference to identify the vector store config. 1-120 chars|
|description|one of: string or null|No|A description for your own reference.|
|store_type|string|Yes|The type of vector store backend. One of: lancedb_fts, lancedb_hybrid, lancedb_vector|
|properties|one of: LanceDBConfigFTSProperties, LanceDBConfigVectorProperties, LanceDBConfigVectorProperties|Yes|The properties of the vector store config, specific to the selected store_type.|
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
