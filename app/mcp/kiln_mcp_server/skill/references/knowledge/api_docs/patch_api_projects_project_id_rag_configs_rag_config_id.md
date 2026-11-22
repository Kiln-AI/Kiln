# Update Rag Config

**PATCH /api/projects/{project_id}/rag_configs/{rag_config_id}**

**Tags:** Documents

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|rag_config_id|string|Yes|The unique identifier of the RAG configuration.|

### Request Body

**Content Type:** `application/json`

|Field|Type|Required|Description|
|-|-|-|-|
|name|one of: string or null|No|The updated name.|
|description|one of: string or null|No|The updated description.|
|is_archived|one of: boolean or null|No|Whether the config is archived.|

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
|name|string|A name to identify this RAG configuration for your own reference. 1-120 chars|
|is_archived|boolean|Whether the RAG configuration is archived. Archived RAG configurations are not shown in the UI and are not available for use.|
|description|one of: string or null|A description of the RAG configuration for you and your team. Will not be used in prompts/training/validation.|
|tool_name|string|A name for the model to identify the Search Tool in conversations. 1-64 chars|
|tool_description|string|A description of the purpose of the tool. The model will use this description to understand the tool's capabilities. <=128 chars|
|extractor_config_id|one of: string or null|The ID of the extractor config used to extract the documents.|
|chunker_config_id|one of: string or null|The ID of the chunker config used to chunk the documents.|
|embedding_config_id|one of: string or null|The ID of the embedding config used to embed the documents.|
|vector_store_config_id|one of: string or null|The ID of the vector store config used to store the documents.|
|reranker_config_id|one of: string or null|The ID of the reranker config used to rerank the documents. If None, no reranking will be performed.|
|tags|one of: array of string or null|List of document tags to filter by. If None, all documents in the project are used.|
|provenance|one of: KilnArtifactProvenance or null|Why this artifact exists and what it was derived from.|
|model_type|string||

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

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

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
