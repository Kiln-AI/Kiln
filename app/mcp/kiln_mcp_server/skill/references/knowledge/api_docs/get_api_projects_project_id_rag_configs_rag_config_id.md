# Get Rag Config

**GET /api/projects/{project_id}/rag_configs/{rag_config_id}**

**Tags:** Documents

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|rag_config_id|string|Yes|The unique identifier of the RAG configuration.|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|id|one of: string or null|The RAG config ID.|
|name|string|The name of the RAG config.|
|description|one of: string or null|The description of the RAG config.|
|tool_name|string|The tool name for the model.|
|tool_description|string|The tool description for the model.|
|created_at|string|When the config was created. Format: date-time|
|created_by|string|The user who created the config.|
|is_archived|boolean|Whether the config is archived.|
|extractor_config.v|integer|Schema version for migration support.|
|extractor_config.id|one of: string or null|Unique identifier for this record.|
|extractor_config.path|one of: string or null|File system path where the record is stored.|
|extractor_config.created_at|string|Timestamp when the model was created. Timezone-aware; stores the writer's local offset. Format: date-time|
|extractor_config.created_by|string|User ID of the creator.|
|extractor_config.name|string|A name to identify the extractor config. 1-120 chars|
|extractor_config.is_archived|boolean|Whether the extractor config is archived. Archived extractor configs are not shown in the UI and are not available for use.|
|extractor_config.description|one of: string or null|The description of the extractor config|
|extractor_config.model_provider_name|string|The name of the model provider to use for the extractor config.|
|extractor_config.model_name|string|The name of the model to use for the extractor config.|
|extractor_config.output_format|string|The output format for extraction results. One of: text/plain, text/markdown|
|extractor_config.passthrough_mimetypes|array of string|If the mimetype is in this list, the extractor will not be used and the text content of the file will be returned as is.|
|extractor_config.extractor_type|string|The type of extractor used to process documents. One of: litellm|
|extractor_config.properties|one of: LitellmExtractorConfigProperties|Properties to be used to execute the extractor config. This is extractor_type specific and should serialize to a json dict.|
|extractor_config.provenance|one of: KilnArtifactProvenance or null|Why this artifact exists and what it was derived from.|
|extractor_config.model_type|string||
|chunker_config.v|integer|Schema version for migration support.|
|chunker_config.id|one of: string or null|Unique identifier for this record.|
|chunker_config.path|one of: string or null|File system path where the record is stored.|
|chunker_config.created_at|string|Timestamp when the model was created. Timezone-aware; stores the writer's local offset. Format: date-time|
|chunker_config.created_by|string|User ID of the creator.|
|chunker_config.name|string|A name to identify the chunker config. 1-120 chars|
|chunker_config.description|one of: string or null|The description of the chunker config|
|chunker_config.chunker_type|string|The type of chunking algorithm to use. One of: fixed_window, semantic|
|chunker_config.properties|one of: SemanticChunkerProperties, FixedWindowChunkerProperties|Properties to be used to execute the chunker config. This is chunker_type specific and should serialize to a json dict.|
|chunker_config.provenance|one of: KilnArtifactProvenance or null|Why this artifact exists and what it was derived from.|
|chunker_config.model_type|string||
|embedding_config.v|integer|Schema version for migration support.|
|embedding_config.id|one of: string or null|Unique identifier for this record.|
|embedding_config.path|one of: string or null|File system path where the record is stored.|
|embedding_config.created_at|string|Timestamp when the model was created. Timezone-aware; stores the writer's local offset. Format: date-time|
|embedding_config.created_by|string|User ID of the creator.|
|embedding_config.name|string|A name to identify the embedding config. 1-120 chars|
|embedding_config.description|one of: string or null|A description for your reference, not shared with embedding models.|
|embedding_config.model_provider_name|string|Enumeration of supported AI model providers. One of: openai, groq, amazon_bedrock, ollama, openrouter, fireworks_ai, kiln_fine_tune, kiln_custom_registry, openai_compatible, anthropic, gemini_api, azure_openai, huggingface, vertex, together_ai, siliconflow_cn, cerebras, docker_model_runner, featherless_ai, cloudflare, typesafe|
|embedding_config.model_name|string|The model to use to generate embeddings.|
|embedding_config.properties.dimensions|integer||
|embedding_config.provenance|one of: KilnArtifactProvenance or null|Why this artifact exists and what it was derived from.|
|embedding_config.model_type|string||
|vector_store_config.v|integer|Schema version for migration support.|
|vector_store_config.id|one of: string or null|Unique identifier for this record.|
|vector_store_config.path|one of: string or null|File system path where the record is stored.|
|vector_store_config.created_at|string|Timestamp when the model was created. Timezone-aware; stores the writer's local offset. Format: date-time|
|vector_store_config.created_by|string|User ID of the creator.|
|vector_store_config.name|string|A name for your own reference to identify the vector store config. 1-120 chars|
|vector_store_config.description|one of: string or null|A description for your own reference.|
|vector_store_config.store_type|string|The type of vector store backend. One of: lancedb_fts, lancedb_hybrid, lancedb_vector|
|vector_store_config.properties|one of: LanceDBConfigFTSProperties, LanceDBConfigVectorProperties, LanceDBConfigVectorProperties|The properties of the vector store config, specific to the selected store_type.|
|vector_store_config.provenance|one of: KilnArtifactProvenance or null|Why this artifact exists and what it was derived from.|
|vector_store_config.model_type|string||
|reranker_config|one of: RerankerConfig or null|The reranker config, if any.|
|tags|one of: array of string or null|Tags for document filtering.|
|provenance|one of: KilnArtifactProvenance or null|Provenance: why this RAG config exists and what it was derived from.|

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

### CohereCompatibleProperties

|Field|Type|Required|Description|
|-|-|-|-|
|type|string|Yes|One of: cohere_compatible|

### RerankerConfig

Configuration for reranking search results using a reranking model.

|Field|Type|Required|Description|
|-|-|-|-|
|v|integer|No|Schema version for migration support.|
|id|one of: string or null|No|Unique identifier for this record.|
|path|one of: string or null|No|File system path where the record is stored.|
|created_at|string|No|Timestamp when the model was created. Timezone-aware; stores the writer's local offset. Format: date-time|
|created_by|string|No|User ID of the creator.|
|name|string|Yes|A name for your own reference to identify the reranker config. 1-120 chars|
|description|one of: string or null|No|A description for your own reference.|
|top_n|integer|Yes|The number of results to return from the reranker.|
|model_provider_name|string|Yes|The name of the model provider to use.|
|model_name|string|Yes|The name of the model to use.|
|properties|one of: CohereCompatibleProperties|Yes|The properties of the reranker config, specific to the selected type.|
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
