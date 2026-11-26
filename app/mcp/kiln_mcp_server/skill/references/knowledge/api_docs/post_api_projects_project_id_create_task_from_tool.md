# Create Task From Tool

**POST /api/projects/{project_id}/create_task_from_tool**

**Tags:** Tasks

Create a task whose input and output schemas come from an MCP tool, and a run
config that calls it.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|

### Request Body

**Content Type:** `application/json`

|Field|Type|Required|Description|
|-|-|-|-|
|tool_id|string|Yes|The tool ID to create the task from.|
|task_name|string|Yes|The name for the new task.|
|instruction|string|Yes|The instruction for the new task. >=1 chars|
|provenance|one of: KilnArtifactProvenance or null|No|Provenance stamped onto the created run config. The run config belongs to a new task, so derived_from_ids must be empty.|

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
|name|string|The name of the task. 1-120 chars|
|description|one of: string or null|A description of the task for you and your team. Will not be used in prompts/training/validation.|
|instruction|string|The instructions for the task. Will be used in prompts/training/validation. >=1 chars|
|requirements|array of TaskRequirement|Deprecated: Use specs and prompts instead.|
|output_json_schema|one of: string or null|JSON schema for structured task output. Must be an object schema.|
|input_json_schema|one of: string or null|JSON schema for structured task input. Can be an object or array schema.|
|thinking_instruction|one of: string or null|Instructions for the model 'thinking' about the requirement prior to answering. Used for chain of thought style prompting.|
|default_run_config_id|one of: string or null|ID of the run config to use for this task by default. Must exist in saved run configs for this task.|
|turn_mode|string|Whether a Task runs as a single turn or as a multiturn conversation. One of: single_turn, multiturn|
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

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
