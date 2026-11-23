# Create Code Tool

**POST /api/projects/{project_id}/code_tools**

**Tags:** Code Tools

Create a code tool: Python code the project's agents can call as a tool.
While the project's code is not trusted, it saves nothing and returns
`not_trusted: true`. Only the user can grant code trust: explain what the
code will run and that it runs with no sandbox, give them the link
http://localhost:8757/settings/trust_code/{project_id}, and ask them to
tell you when they have approved. Then confirm with
GET /api/projects/{project_id}/add_code_trust and create the tool.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|

### Request Body

**Content Type:** `application/json`

|Field|Type|Required|Description|
|-|-|-|-|
|name|string|Yes|User-facing display name.|
|description|one of: string or null|No|User-facing notes shown in the UI.|
|tool_function_name|string|Yes|The function name exposed to the model.|
|tool_description|string|Yes|Shown to agents as the tool description. >=1 chars|
|parameters_schema|object|Yes|JSON Schema for the tool's parameters.|
|code|string|Yes|Inline Python source.|
|timeout_seconds|integer|No|Wall-clock timeout. >=1.0|
|tool_allowlist|array of string|No|Tools this code tool may call.|
|provenance|one of: KilnArtifactProvenance or null|No|Provenance: why this code tool exists and what it was derived from.|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|id|one of: string or null||
|name|one of: string or null||
|description|one of: string or null||
|is_archived|boolean||
|tool_function_name|one of: string or null||
|tool_description|one of: string or null||
|parameters_schema|one of: object or null||
|code|one of: string or null||
|timeout_seconds|one of: integer or null||
|tool_allowlist|array of string||
|created_at|one of: string or null||
|created_by|one of: string or null||
|provenance|one of: KilnArtifactProvenance or null||
|not_trusted|boolean|True when the project's code is not trusted, so nothing ran and nothing was saved. Only the user can grant code trust, in the Kiln app at http://localhost:8757/settings/trust_code/{project_id}. Explain what the code will run and that it runs with no sandbox, give the user that link, and ask them to tell you when they have approved. Then confirm with GET /api/projects/{project_id}/add_code_trust and call again.|

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
