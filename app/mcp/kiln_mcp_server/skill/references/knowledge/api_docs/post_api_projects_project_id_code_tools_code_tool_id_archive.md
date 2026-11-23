# Archive/Unarchive Code Tool

**POST /api/projects/{project_id}/code_tools/{code_tool_id}/archive**

**Tags:** Code Tools

Archive or unarchive a code tool.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|code_tool_id|string|Yes|The unique identifier of the code tool.|

### Request Body

**Content Type:** `application/json`

|Field|Type|Required|Description|
|-|-|-|-|
|archived|boolean|Yes|Whether to archive or unarchive the tool.|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|id|one of: string or null||
|name|string||
|description|one of: string or null||
|is_archived|boolean||
|tool_function_name|string||
|tool_description|string||
|parameters_schema|object||
|code|string||
|timeout_seconds|integer||
|tool_allowlist|array of string||
|created_at|one of: string or null||
|created_by|one of: string or null||
|provenance|one of: KilnArtifactProvenance or null||

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
