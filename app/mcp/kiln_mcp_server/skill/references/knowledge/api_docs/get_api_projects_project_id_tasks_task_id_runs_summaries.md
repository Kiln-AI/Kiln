# List Run Summaries

**GET /api/projects/{project_id}/tasks/{task_id}/runs_summaries**

**Tags:** Runs

List short summaries of the task's runs, lighter than List Runs. For multi-turn tasks, only leaf TaskRuns (those that are not the parent of another run via parent_task_run_id) are summarized. For single-turn tasks this is equivalent to summarizing every run.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|task_id|string|Yes|The unique identifier of the task within the project.|

## Responses

### 200 OK

Successful Response

**Body:** array of RunSummary

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### TaskOutputRating-Output

A rating for a task output, including an overall rating and ratings for each requirement.

Supports:
- five_star: 1-5 star ratings
- pass_fail: boolean pass/fail (1.0 = pass, 0.0 = fail)
- pass_fail_critical: tri-state (1.0 = pass, 0.0 = fail, -1.0 = critical fail)

|Field|Type|Required|Description|
|-|-|-|-|
|v|integer|No|Schema version for migration support.|
|id|one of: string or null|No|Unique identifier for this record.|
|path|one of: string or null|No|File system path where the record is stored.|
|created_at|string|No|Timestamp when the model was created. Timezone-aware; stores the writer's local offset. Format: date-time|
|created_by|string|No|User ID of the creator.|
|type|string|No|Defines the types of rating systems available for task outputs. One of: five_star, pass_fail, pass_fail_critical, custom|
|value|one of: number or null|No|The rating value. Interpretation depends on rating type:
- five_star: 1-5 stars
- pass_fail: 1.0 (pass) or 0.0 (fail)
- pass_fail_critical: 1.0 (pass), 0.0 (fail), or -1.0 (critical fail)|
|requirement_ratings|object|No|The ratings of the requirements of the task. The ID can be either a task_requirement_id or a named rating for an eval_output_score name (in format 'named::<name>').|
|model_type|string|Yes||

### RunSummary

A summary of a task run for list views.

|Field|Type|Required|Description|
|-|-|-|-|
|id|one of: string or null|Yes|The unique identifier of the task run.|
|rating|one of: TaskOutputRating-Output or null|No|The rating of the task run output.|
|created_at|string|Yes|When the run was created. Format: date-time|
|input_preview|one of: string or null|No|A truncated preview of the task input.|
|output_preview|one of: string or null|No|A truncated preview of the task output.|
|repair_state|one of: string or null|No|The repair state of the run (e.g., 'Repaired', 'No repair needed').|
|model_name|one of: string or null|No|The model used for this run.|
|input_source|one of: string or null|No|The source of the input (human, synthetic, etc.).|
|tags|one of: array of string or null|No|Tags applied to the run.|

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
