# Get Memories

**GET /api/projects/{project_id}/memories/by_ids**

**Tags:** Memory

Fetch full memory records by id. Unknown ids are omitted from the result.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|

### Query Parameters

|Name|Type|Required|Default|Description|
|-|-|-|-|-|
|ids|array of string|Yes||The memory ids to fetch.|

## Responses

### 200 OK

Successful Response

**Body:** array of Memory

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### Memory

One memory record of the assistant working on this project.

Stored at assistant_memory/{id}/memory.kiln. Concurrent-append safe
(file per memory); updates are last-writer-wins.

|Field|Type|Required|Description|
|-|-|-|-|
|v|integer|No|Schema version for migration support.|
|id|one of: string or null|No|Unique identifier for this record.|
|path|one of: string or null|No|File system path where the record is stored.|
|created_at|string|No|Timestamp when the model was created. Timezone-aware; stores the writer's local offset. Format: date-time|
|created_by|string|No|User ID of the creator.|
|overview|string|Yes|One-line summary written so a future reader can decide whether to fetch the full content. For very short memories this IS the whole memory (leave content null). No newlines. <=280 chars|
|content|one of: string or null|No|The memory body: the finding/fact/decision with its conditions and evidence level, citing related Kiln records as prose IDs (e.g. 'run_config 184623901234', 'eval 5678'). Null when the overview says everything. Record observations with conditions ('batch API 429'd at 50rps on 07-04'), never universal rules.|
|tags|array of string|No|Snake_case tags for filtering (existing Kiln tag rules). Free-form; skills define the working vocabulary (e.g. experiment, dead_end, constraint, api_quirk, session_state; faceted tags like lever_prompt, verdict_accept, evidence_weak).|
|scope|string|Yes|Opaque scope string, exact-match filterable. Conventions: 'project' for project-wide knowledge (constraints, environment facts); 'task::<task_id>' for task-scoped work. Not validated against existing records — a convention, not a reference. <=255 chars|
|model_type|string|Yes||

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
