# Get Eval Input

**GET /api/projects/{project_id}/tasks/{task_id}/eval_inputs/{eval_input_id}**

**Tags:** Eval Inputs

Get one eval input item.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|task_id|string|Yes|The unique identifier of the task within the project.|
|eval_input_id|string|Yes|The unique identifier of the eval input.|

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
|data|one of: SingleTurnEvalInputData, object|The input data for this eval item.|
|reference|one of: object or null|Optional reference data (ground truth) for this eval input, keyed by reference name.|
|tags|array of string|Tags for filtering eval inputs.|
|openenv_reset|one of: OpenEnvReset or null|Start a new episode on the OpenEnv server named by openenv_server_id before the run, by calling the environment's reset() with these keyword arguments. The trace records that episode. A run config that lists the OpenEnv server's tools runs the input in that episode; a run config listing the project's own version of a tool the environment serves is refused. None runs against the project tools.|
|model_type|string||

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

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
