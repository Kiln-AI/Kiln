# Get Task Data Guide

**GET /api/projects/{project_id}/tasks/{task_id}/data_gen_guide**

**Tags:** Synthetic Data

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|task_id|string|Yes|The unique identifier of the task within the project.|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|value|one of: DataGuide or null||

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### DataGuide

Persistent input data guide for synthetic data generation, stored as a
child of a Task.

The guide describes what realistic *inputs* to this task look like — input
shape, format, distribution, and the kinds of values inputs contain. It is
consumed at the topic and input generation stages of synthetic data
generation, never at the output stage. Output behavior is the job of the
task's system prompt, not this guide.

The guide is a single markdown body. Two canonical shapes are supported
depending on origin:

- **Manual flow** (user-authored examples): leads with `# Reference Inputs`
  (user-owned `## Example N` blocks), followed by `# Semantics`, `# Style`,
  `# Presentation Defaults`.
- **Kiln Pro / Copilot flow** (analyze pipeline): only `# Semantics`,
  `# Style`, `# Presentation Defaults` — the analyze prompt derives rules
  from input documents rather than quoting them.

The metaprompter treats the whole body as one editable artifact and returns
a refined version on each refine pass; refine auto-detects which shape it
is working on by checking for a `# Reference Inputs` heading.

|Field|Type|Required|Description|
|-|-|-|-|
|v|integer|No|Schema version for migration support.|
|id|one of: string or null|No|Unique identifier for this record.|
|path|one of: string or null|No|File system path where the record is stored.|
|created_at|string|No|Timestamp when the model was created. Timezone-aware; stores the writer's local offset. Format: date-time|
|created_by|string|No|User ID of the creator.|
|guide|string|No|Markdown body of the input data guide. Manual-flow guides start with `# Reference Inputs`; Kiln Pro / Copilot-flow guides have only `# Semantics`, `# Style`, `# Presentation Defaults`.|
|source|string|No|Which flow created this guide. Refine + verify pipelines branch on this to choose the right metaprompter (manual = user-curated examples + edits all sections; kiln_pro = LLM-derived, refine is feedback-only surgical edits). One of: manual, kiln_pro|
|model_type|string|Yes||

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
