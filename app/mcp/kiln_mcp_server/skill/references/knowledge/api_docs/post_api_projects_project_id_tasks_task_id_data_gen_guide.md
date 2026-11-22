# Save Task Data Guide

**POST /api/projects/{project_id}/tasks/{task_id}/data_gen_guide**

**Tags:** Synthetic Data

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|task_id|string|Yes|The unique identifier of the task within the project.|

### Request Body

**Content Type:** `application/json`

|Field|Type|Required|Description|
|-|-|-|-|
|guide|string|No|Markdown body of the input data guide.|
|source|one of: string or null|No|Which flow created this guide. Determines which refine metaprompter branch runs on subsequent edits. On edit, omit to preserve the existing source; on first save, send the originating flow.|

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
|guide|string|Markdown body of the input data guide. Manual-flow guides start with `# Reference Inputs`; Kiln Pro / Copilot-flow guides have only `# Semantics`, `# Style`, `# Presentation Defaults`.|
|source|string|Which flow created this guide. Refine + verify pipelines branch on this to choose the right metaprompter (manual = user-curated examples + edits all sections; kiln_pro = LLM-derived, refine is feedback-only surgical edits). One of: manual, kiln_pro|
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
