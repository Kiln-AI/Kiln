# Get Run Config Eval Scores

**GET /api/projects/{project_id}/tasks/{task_id}/run_configs/{run_config_id}/eval_scores**

**Tags:** Run Configs

Get one run config's scores on every eval of the task.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|task_id|string|Yes|The unique identifier of the task within the project.|
|run_config_id|string|Yes|The unique identifier of the run configuration.|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|eval_results|array of RunConfigEvalResult|Eval results for each eval.|
|mean_usage|one of: MeanUsage or null|Average usage statistics across eval runs.|

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### EvalConfigResult

Results for a single eval config.

|Field|Type|Required|Description|
|-|-|-|-|
|eval_config_id|one of: string or null|Yes|The eval config ID.|
|results|object|Yes|Scores keyed by output_score_id. None when no data.|
|percent_complete|number|Yes|Percent of the dataset processed.|
|n_excluded|integer|No|Number of EvalRuns excluded due to skipped_reason.|

### RunConfigEvalResult

Eval results for a specific run config.

|Field|Type|Required|Description|
|-|-|-|-|
|eval_id|one of: string or null|Yes|The unique identifier of the eval.|
|eval_name|string|Yes|The human-readable name of the eval.|
|dataset_size|integer|Yes|The dataset size for this eval.|
|eval_config_result|one of: EvalConfigResult or null|No|The eval config results, if available.|
|missing_default_eval_config|boolean|Yes|Whether the default eval config is missing.|
|spec_id|one of: string or null|No|The associated spec ID, if any.|
|score_display_names|object|Yes|The user-facing name of each of the eval's output scores, keyed by the score's JSON key (the keys of eval_config_result.results). The score's display_name when set, otherwise its name.|

### MeanUsage

Average token usage across eval runs.

|Field|Type|Required|Description|
|-|-|-|-|
|mean_input_tokens|one of: number or null|No|Average input tokens per run.|
|mean_output_tokens|one of: number or null|No|Average output tokens per run.|
|mean_total_tokens|one of: number or null|No|Average total tokens per run.|
|mean_cost|one of: number or null|No|Average cost per run in USD.|
|mean_total_llm_latency_ms|one of: number or null|No|Average total LLM latency per run in milliseconds.|

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
