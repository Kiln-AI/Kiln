# Save Memory

**POST /api/projects/{project_id}/memories**

**Tags:** Memory

Save a memory: a note for agents working on the project.

It has an overview, a scope, and optional content and tags.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|

### Request Body

**Content Type:** `application/json`

|Field|Type|Required|Description|
|-|-|-|-|
|overview|string|Yes|One-line summary written so a future reader can decide whether to fetch the content. For very short memories this IS the whole memory (leave content null). No newlines. <=280 chars|
|scope|string|Yes|Opaque scope string. Conventions: 'project' for project-wide knowledge; 'task::<task_id>' for task-scoped work. Not validated against existing records. <=255 chars|
|content|one of: string or null|No|The memory body: the finding/fact/decision with its conditions and evidence level. Null when the overview says everything.|
|tags|array of string|No|Snake_case tags (no spaces) for filtering.|

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
|overview|string|One-line summary written so a future reader can decide whether to fetch the full content. For very short memories this IS the whole memory (leave content null). No newlines. <=280 chars|
|content|one of: string or null|The memory body: the finding/fact/decision with its conditions and evidence level, citing related Kiln records as prose IDs (e.g. 'run_config 184623901234', 'eval 5678'). Null when the overview says everything. Record observations with conditions ('batch API 429'd at 50rps on 07-04'), never universal rules.|
|tags|array of string|Snake_case tags for filtering (existing Kiln tag rules). Free-form; skills define the working vocabulary (e.g. experiment, dead_end, constraint, api_quirk, session_state; faceted tags like lever_prompt, verdict_accept, evidence_weak).|
|scope|string|Opaque scope string, exact-match filterable. Conventions: 'project' for project-wide knowledge (constraints, environment facts); 'task::<task_id>' for task-scoped work. Not validated against existing records — a convention, not a reference. <=255 chars|
|model_type|string||

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
