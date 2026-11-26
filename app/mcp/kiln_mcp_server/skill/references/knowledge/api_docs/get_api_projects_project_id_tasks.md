# List Tasks

**GET /api/projects/{project_id}/tasks**

**Tags:** Tasks

List a project's tasks.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|

## Responses

### 200 OK

Successful Response

**Body:** array of Task

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### TaskRequirement

Defines a specific requirement that should be met by task outputs.

Includes an identifier, name, description, instruction for meeting the requirement,
priority level, and rating type (five_star, pass_fail, pass_fail_critical, custom).

|Field|Type|Required|Description|
|-|-|-|-|
|id|one of: string or null|No|Unique identifier for this record.|
|name|string|Yes|The name of the task requirement. 1-32 chars|
|description|one of: string or null|No|Optional elaboration on the requirement's purpose.|
|instruction|string|Yes|Instructions for meeting the requirement. >=1 chars|
|priority|integer|No|Priority levels, where P0 is highest priority. One of: 0, 1, 2, 3|
|type|string|No|Defines the types of rating systems available for task outputs. One of: five_star, pass_fail, pass_fail_critical, custom|

### Task

Represents a specific task to be performed, with associated requirements and validation rules.

Contains the task definition, requirements, input/output schemas, and maintains
a collection of task runs.

|Field|Type|Required|Description|
|-|-|-|-|
|v|integer|No|Schema version for migration support.|
|id|one of: string or null|No|Unique identifier for this record.|
|path|one of: string or null|No|File system path where the record is stored.|
|created_at|string|No|Timestamp when the model was created. Timezone-aware; stores the writer's local offset. Format: date-time|
|created_by|string|No|User ID of the creator.|
|name|string|Yes|The name of the task. 1-120 chars|
|description|one of: string or null|No|A description of the task for you and your team. Will not be used in prompts/training/validation.|
|instruction|string|Yes|The instructions for the task. Will be used in prompts/training/validation. >=1 chars|
|requirements|array of TaskRequirement|No|Deprecated: Use specs and prompts instead.|
|output_json_schema|one of: string or null|No|JSON schema for structured task output. Must be an object schema.|
|input_json_schema|one of: string or null|No|JSON schema for structured task input. Can be an object or array schema.|
|thinking_instruction|one of: string or null|No|Instructions for the model 'thinking' about the requirement prior to answering. Used for chain of thought style prompting.|
|default_run_config_id|one of: string or null|No|ID of the run config to use for this task by default. Must exist in saved run configs for this task.|
|turn_mode|string|No|Whether a Task runs as a single turn or as a multiturn conversation. One of: single_turn, multiturn|
|model_type|string|Yes||

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
