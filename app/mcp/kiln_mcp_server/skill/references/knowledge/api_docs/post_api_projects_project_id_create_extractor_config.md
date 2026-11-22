# Create Extractor Config

**POST /api/projects/{project_id}/create_extractor_config**

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
|description|one of: string or null|No|The description of the extractor config|
|model_provider_name|string|Yes|Enumeration of supported AI model providers. One of: openai, groq, amazon_bedrock, ollama, openrouter, fireworks_ai, kiln_fine_tune, kiln_custom_registry, openai_compatible, anthropic, gemini_api, azure_openai, huggingface, vertex, together_ai, siliconflow_cn, cerebras, docker_model_runner, featherless_ai, cloudflare, typesafe|
|model_name|string|Yes|The name of the model to use for the extractor config.|
|output_format|string|Yes|The output format for extraction results. One of: text/plain, text/markdown|
|passthrough_mimetypes|array of string|No|MIME types that bypass extraction and return the file content as-is.|
|properties.extractor_type|string|Yes|One of: litellm|
|properties.prompt_document|string|Yes||
|properties.prompt_image|string|Yes||
|properties.prompt_video|string|Yes||
|properties.prompt_audio|string|Yes||
|provenance|one of: KilnArtifactProvenance or null|No|Provenance: why this extractor config exists and what it was derived from.|

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
|name|string|A name to identify the extractor config. 1-120 chars|
|is_archived|boolean|Whether the extractor config is archived. Archived extractor configs are not shown in the UI and are not available for use.|
|description|one of: string or null|The description of the extractor config|
|model_provider_name|string|The name of the model provider to use for the extractor config.|
|model_name|string|The name of the model to use for the extractor config.|
|output_format|string|The output format for extraction results. One of: text/plain, text/markdown|
|passthrough_mimetypes|array of string|If the mimetype is in this list, the extractor will not be used and the text content of the file will be returned as is.|
|extractor_type|string|The type of extractor used to process documents. One of: litellm|
|properties|one of: LitellmExtractorConfigProperties|Properties to be used to execute the extractor config. This is extractor_type specific and should serialize to a json dict.|
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

### LitellmExtractorConfigProperties

|Field|Type|Required|Description|
|-|-|-|-|
|extractor_type|string|Yes|One of: litellm|
|prompt_document|string|Yes||
|prompt_image|string|Yes||
|prompt_video|string|Yes||
|prompt_audio|string|Yes||

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
