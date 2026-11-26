# Task Summaries (agent-tuned)

**GET /api/task_summaries**

**Tags:** Tasks

Return a workspace-wide list of projects and their tasks, with truncated
task.instruction values. Unlike typical list endpoints, entries here are
intentionally lossy — the shape is tuned for LLM-agent context efficiency,
not for driving UIs that need the full Task model.

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|projects|array of TaskSummariesProject||

## Schemas

### TaskSummary

|Field|Type|Required|Description|
|-|-|-|-|
|id|string|Yes||
|name|string|Yes||
|description|one of: string or null|Yes||
|instruction|string|Yes||

### TaskSummariesProject

|Field|Type|Required|Description|
|-|-|-|-|
|id|string|Yes||
|name|string|Yes||
|description|one of: string or null|Yes||
|tasks|array of TaskSummary|Yes||
