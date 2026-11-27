# Create Eval Input

**POST /api/projects/{project_id}/tasks/{task_id}/eval_inputs**

**Tags:** Eval Inputs

Create an eval input item. Evals pick it up via their eval_input_filter_id, so tag it accordingly.

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
|data|one of: SingleTurnEvalInputData, MultiTurnSyntheticEvalInputData-Input|Yes|The input data for this eval item. A multi_turn_synthetic item must carry both a drive_config and a first_message with non-empty text: they are what make it re-drivable, and neither can be added after the item is created.|
|reference|one of: object or null|No|Optional reference data (ground truth) for this eval input, keyed by reference name.|
|tags|array of string|No|Tags for filtering eval inputs (matched by tag:: eval_input_filter_ids).|
|openenv_reset|one of: OpenEnvReset or null|No|Optional environment to run this item in: an environment in this project, plus the keyword arguments its reset() is called with. A run config that lists that environment's tools runs the item in the episode the reset starts; omit it and the item runs against the project's own tools. Like the scenario, it cannot be changed afterwards — send a new item instead.|

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

### UserMessage

|Field|Type|Required|Description|
|-|-|-|-|
|text|string|Yes||

### MultiTurnDriveConfig

Settings for re-driving a multi-turn synthetic input at eval time.

A multi-turn eval run regenerates each conversation: the agent under test
comes from the run config being evaluated, while the synthetic user
(customer) configured here is held constant across run configs — so a
comparison varies only the agent. Stored per item, on
MultiTurnSyntheticEvalInputData.drive_config.

|Field|Type|Required|Description|
|-|-|-|-|
|model_name|string|Yes|The model that plays the synthetic user during re-drives.|
|model_provider|string|Yes|The provider of the synthetic-user model.|
|turns|integer|Yes|Ceiling on the assistant turns per re-driven conversation. 1.0-20.0|

### MultiTurnSyntheticEvalInputData-Input

A re-drivable multi-turn case: the opening user message, the synthetic
user who continues the conversation at eval time, and the drive settings
that synthetic user runs with.

Together these make the item a self-contained replication recipe: with the
persona, first_message, and drive_config it re-drives identically under any
eval that references it, which is what makes conversation traces keyed to
the item reusable across evals.

first_message may be None; such items carry no seed to open a
conversation with, so the eval runner skips them instead of re-driving.

|Field|Type|Required|Description|
|-|-|-|-|
|type|string|No|One of: multi_turn_synthetic|
|first_message|one of: UserMessage or null|No||
|synthetic_user_info.persona|string|Yes||
|synthetic_user_info.goal|string|Yes||
|synthetic_user_info.behavior_guidance|one of: string or null|No||
|drive_config|one of: MultiTurnDriveConfig or null|No|How this item's conversation is re-driven: the synthetic-user model and turn count, stamped when the item is minted. This is the ONLY home for drive settings — no eval-level copy exists; displays and prefills derive from items. Held constant across run configs so a comparison varies only the agent under test. Immutable once minted: changing the synthetic-user setup means minting new items, which keeps traces keyed to this item valid. None only on items minted before drive settings were stamped; the eval runner skips such items with a clear reason rather than guessing a config.|

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
