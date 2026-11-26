# Set Default Eval Config

**POST /api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/set_current_eval_config/{eval_config_id}**

**Tags:** Evals

Make a judge (eval config) the eval's default, the one whose scores Kiln
shows.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|task_id|string|Yes|The unique identifier of the task within the project.|
|eval_id|string|Yes|The unique identifier of the eval.|
|eval_config_id|string|Yes|The unique identifier of the eval configuration to set as default, or 'None' to clear the default.|

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
|name|string|The name of the eval. 1-120 chars|
|description|one of: string or null|The description of the eval|
|template|one of: string or null|The template selected when creating this eval. Useful for suggesting eval steps and output scores.|
|current_config_id|one of: string or null|The id of the current config to use for this eval. This can be changed over time to run the same eval with different configs.|
|eval_set_filter_id|one of: string or null|Deprecated, and neither read nor written. It exists only so evals written by a Kiln build that predates `splits` still load: on load its value is migrated into splits['test'] once, and the field is then cleared. It is always saved as null. Read splits['test'] instead.|
|eval_configs_filter_id|one of: string or null|The id of the dataset filter which defines which dataset items are included when comparing the quality of the eval configs under this eval. Should consist of dataset items with ratings.|
|train_set_filter_id|one of: string or null|Deprecated, and neither read nor written. It exists only so evals written by a Kiln build that predates `splits` still load: on load its value is migrated into splits['train'] once, and the field is then cleared. It is always saved as null. Read splits['train'] instead.|
|splits|object|The eval's dataset splits, keyed by split name ('test', 'train', 'val'), and the only place they are stored. Each split names the store its items come from and the filter that selects them. Keys this build doesn't know are preserved but not exposed. 'golden' is not a split and does not belong here: the golden set must be dataset (TaskRun) based, because human ratings only exist on dataset items, so it is stored in eval_configs_filter_id instead. Nothing reads splits['golden'] — writing it is accepted and silently ignored. In Python, prefer Eval.set_split() to assigning into this dict: it refuses to mutate a readonly (cached) eval, and marks the field as set so exclude_unset dumps keep it.|
|output_scores|array of EvalOutputScore|The scores this evaluator should produce.|
|favourite|boolean|Whether this eval is a favourite of the user. Rendered as a star icon in the UI.|
|priority|one of: integer or null|The priority of the eval. None on evals created before priority lived on evals; read through resolved_priority(), which falls back to the associated spec.|
|status|one of: string or null|The status of the eval. None on evals created before status lived on evals; read through resolved_status(), which falls back to the associated spec.|
|template_properties|one of: object or null|Properties to be used to execute the eval. This is template_type specific and should serialize to a json dict.|
|evaluation_data_type|one of: string or null|The output of the task run to evaluate. Can be final answer, full trace, or None for V2 evals.|
|model_type|string||

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### EvalOutputScore

A definition of a score that an evaluator will produce.

Very similar to TaskRequirement, but conceptually different keeping in a separate models.

|Field|Type|Required|Description|
|-|-|-|-|
|name|string|Yes|The name of the score. Will be provided to the model so use a descriptive name. Should align to the model's TaskRequirement name if you want to use human evals to evaluate the evaluator's performance. 1-32 chars|
|display_name|one of: string or null|No|An optional, user-facing display name for the score, shown throughout the UI in place of 'name'. Purely cosmetic: it does not affect the JSON key, stored eval run scores, or the name provided to models. Falls back to 'name' when not set. Surrounding whitespace is stripped; blank values, or a value equal to 'name', are stored as None.|
|instruction|one of: string or null|No|A description of the score, used to help the model understand the goal of the score. Will be provided to evaluator models, so should be written for the model, not the team/user.|
|type|string|Yes|Defines the types of rating systems available for task outputs. One of: five_star, pass_fail, pass_fail_critical, custom|
|direction|string|No|The direction of improvement for an eval output score.

Tells consumers how to interpret a change in the score's value: 'higher_is_better'
means an increase is an improvement, 'lower_is_better' means a decrease is an
improvement, and 'informational' scores carry context only and should never drive
decisions in either direction. One of: higher_is_better, lower_is_better, informational|

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
