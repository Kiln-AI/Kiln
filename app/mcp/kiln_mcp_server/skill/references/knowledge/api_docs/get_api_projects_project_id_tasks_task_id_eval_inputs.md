# List Eval Inputs

**GET /api/projects/{project_id}/tasks/{task_id}/eval_inputs**

**Tags:** Eval Inputs

List a task's eval input items, optionally restricted to a filter.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|task_id|string|Yes|The unique identifier of the task within the project.|

### Query Parameters

|Name|Type|Required|Default|Description|
|-|-|-|-|-|
|filter_id|one of: string or null|No||Optional eval-input filter to apply, e.g. 'all' or 'tag::my_tag' (the same IDs evals use as eval_input_filter_id).|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|eval_inputs|array of EvalInput|The eval input items which loaded successfully.|
|load_error_count|integer|How many eval input files failed to load. Usually because they were written by a newer version of Kiln.|

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### SingleTurnEvalInputData

|Field|Type|Required|Description|
|-|-|-|-|
|type|string|No|One of: single_turn|
|user_message.text|string|Yes||

### OpenEnvReset

Start a new episode on the OpenEnv server named by `openenv_server_id`, by calling the
environment's `reset()` with these keyword arguments before the run. The trace records
that episode.

`reset_kwargs` is opaque to Kiln: it is passed as the keyword arguments of the
environment's `reset` (a dataset or scenario identifier, a seed, a clock override). The
trace key carries a digest of the whole reset, so an input whose reset is edited
after its trace was made generates a new one rather than reusing it.

|Field|Type|Required|Description|
|-|-|-|-|
|openenv_server_id|string|Yes|ID of the OpenEnv server to start the episode on. >=1 chars|
|reset_kwargs|object|No|Keyword arguments for the environment's reset(), passed verbatim. Which keywords exist is the environment's business, e.g. which dataset or scenario to start from, a seed, a clock override.|

### EvalInput

A single evaluation input item, stored as a child of a Task.

Each EvalInput contains the data needed to run an evaluation (e.g. a user
message) plus optional reference data for comparison and tags for filtering.

|Field|Type|Required|Description|
|-|-|-|-|
|v|integer|No|Schema version for migration support.|
|id|one of: string or null|No|Unique identifier for this record.|
|path|one of: string or null|No|File system path where the record is stored.|
|created_at|string|No|Timestamp when the model was created. Timezone-aware; stores the writer's local offset. Format: date-time|
|created_by|string|No|User ID of the creator.|
|data|one of: SingleTurnEvalInputData, object|Yes|The input data for this eval item.|
|reference|one of: object or null|No|Optional reference data (ground truth) for this eval input, keyed by reference name.|
|tags|array of string|No|Tags for filtering eval inputs.|
|openenv_reset|one of: OpenEnvReset or null|No|Start a new episode on the OpenEnv server named by openenv_server_id before the run, by calling the environment's reset() with these keyword arguments. The trace records that episode. A run config that lists the OpenEnv server's tools runs the input in that episode; a run config listing the project's own version of a tool the environment serves is refused. None runs against the project tools.|
|model_type|string|Yes||

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
