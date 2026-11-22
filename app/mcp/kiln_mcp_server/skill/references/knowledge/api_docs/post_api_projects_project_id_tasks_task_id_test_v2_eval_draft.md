# Test V2 Eval Config Draft

**POST /api/projects/{project_id}/tasks/{task_id}/test_v2_eval_draft**

**Tags:** Evals

Test a judge config for an eval that hasn't been created yet.

Builds a transient in-memory eval from the drafted output_scores so
the creation flow can test its judge before saving anything.

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
|properties|one of: LlmJudgeProperties, ExactMatchProperties, PatternMatchProperties, SetCheckProperties, ToolCallCheckProperties, ContainsProperties, StepCountCheckProperties, CodeEvalProperties|Yes|The V2 eval config properties to test.|
|output_scores|array of EvalOutputScore|Yes|The scores the drafted eval will declare; returned scores are validated against them.|
|eval_input.final_message|string|Yes|The final model output (task output text).|
|eval_input.trace|one of: array of object or null|No|The full conversation trace, if available.|
|eval_input.reference_data|one of: object or null|No|Ground-truth data for the item being evaluated, keyed by reference name. Taken from EvalInput.reference for an EvalInput-backed item; for a TaskRun-backed dataset item it is the item's own stored output under the key 'reference_answer', since that output is the curated answer. None when a TaskRun is scored as itself (judge calibration), where the item and the scored run are the same record.|
|eval_input.task_input|one of: string or null|No|The original task input text.|
|eval_input.openenv_episode|one of: OpenEnvEpisode or null|No|The OpenEnv episode the trace's OpenEnv tools ran in, when the run used an OpenEnv server: the reset it started from, what the environment reported at reset, and the environment's final state. Judges reference it in their prompt template (e.g. {{ openenv_episode.final_state }}); code scorers receive it as the `openenv_episode` argument.|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|scores|object||
|skipped_reason|one of: string or null||
|skipped_detail|one of: string or null||
|score_range_errors|one of: array of string or null||
|intermediate_outputs|one of: object or null||
|tool_call_log|array of ToolCallLogEntryResponse|Tools the scorer code called, in call order. Code evals only.|
|judge_trace|one of: array of one of: object, object, object, object, object, object or null|The judge's full conversation in OpenAI format: the system prompt, the rendered judge prompt, and every reply. None for evals that call no model.|

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### LlmJudgeRunConfig

Optional settings for the judge model call. Every field is optional: an unset
field keeps the value the judge would use without it (the provider's default
thinking level, and the run config's default temperature and top_p).

|Field|Type|Required|Description|
|-|-|-|-|
|thinking_level|one of: string or null|No|The judge model's thinking level (e.g. 'none', 'low', 'medium'). Must be one the model's provider offers. If unset, the provider's default applies, which for some models is 'none'.|
|temperature|one of: number or null|No|The judge model's temperature, between 0 and 2. If unset, the run config default applies.|
|top_p|one of: number or null|No|The judge model's top_p, between 0 and 1. If unset, the run config default applies.|

### LlmJudgeProperties

|Field|Type|Required|Description|
|-|-|-|-|
|type|string|No|One of: llm_judge|
|model_name|string|Yes||
|model_provider|string|Yes||
|system_prompt|one of: string or null|No||
|prompt_template|string|Yes||
|reference_keys|array of string|No||
|thinking_instruction|one of: string or null|No||
|g_eval|boolean|No||
|judge_instructions|one of: array of string or null|No||
|run_config|one of: LlmJudgeRunConfig or null|No||

### ExactMatchProperties

|Field|Type|Required|Description|
|-|-|-|-|
|type|string|No|One of: exact_match|
|value_expression|one of: string or null|No||
|expected_value|one of: string or null|No||
|reference_key|one of: string or null|No||
|case_sensitive|boolean|No||

### PatternMatchProperties

|Field|Type|Required|Description|
|-|-|-|-|
|type|string|No|One of: pattern_match|
|value_expression|one of: string or null|No||
|pattern|string|Yes||
|mode|string|No|One of: must_match, must_not_match|

### SetCheckProperties

|Field|Type|Required|Description|
|-|-|-|-|
|type|string|No|One of: set_check|
|value_expression|one of: string or null|No||
|expected_set|one of: array of string or null|No||
|reference_key|one of: string or null|No||
|mode|string|Yes|One of: subset, superset, equal|

### ToolCallSpec

|Field|Type|Required|Description|
|-|-|-|-|
|tool_name|string|Yes||
|expected_args|one of: object or null|No||

### ToolCallCheckProperties

|Field|Type|Required|Description|
|-|-|-|-|
|type|string|No|One of: tool_call_check|
|expected_tools|array of ToolCallSpec|Yes||
|match_mode|string|No|One of: any, all, ordered, never|
|on_unexpected_tools|string|No|One of: ignore, fail|

### ContainsProperties

|Field|Type|Required|Description|
|-|-|-|-|
|type|string|No|One of: contains|
|value_expression|one of: string or null|No||
|substring|one of: string or null|No||
|reference_key|one of: string or null|No||
|case_sensitive|boolean|No||
|mode|string|No|One of: must_contain, must_not_contain|

### StepCountCheckProperties

|Field|Type|Required|Description|
|-|-|-|-|
|type|string|No|One of: step_count_check|
|count_type|string|Yes|One of: tool_calls, model_responses, turns|
|min_count|one of: integer or null|No||
|max_count|one of: integer or null|No||

### CodeEvalProperties

|Field|Type|Required|Description|
|-|-|-|-|
|type|string|No|One of: code_eval|
|code|string|Yes||
|reference_keys|array of string|No||
|timeout_seconds|integer|No|1.0-300.0|
|tool_allowlist|array of string|No|Explicit per-tool allowlist of tools the scorer code may call.|

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

### OpenEnvEpisode

One reset-to-close run on an environment, recorded on the trace of the
task run that used it. The environment's tools ran inside the episode; any other tools
in the run config ran as themselves, outside the environment.

Persisted on `TaskRun.openenv_episode` so graders (including judges added later,
which reuse the same trace) can read what the run left behind. The live session is
closed when the episode ends; `final_state` is the durable record.

|Field|Type|Required|Description|
|-|-|-|-|
|reset.openenv_server_id|string|Yes|ID of the OpenEnv server to start the episode on. >=1 chars|
|reset.reset_kwargs|object|No|Keyword arguments for the environment's reset(), passed verbatim. Which keywords exist is the environment's business, e.g. which dataset or scenario to start from, a seed, a clock override.|
|episode_id|string|Yes|Kiln's id for this episode, passed to the environment's reset() as `episode_id`. >=1 chars|
|openenv_version|string|Yes|The environment's name@version as its server reported it when the episode started (not the version of the openenv package): what produced this state. Kiln trusts a version to be immutable. >=1 chars|
|reset_metadata|object|No|What the environment reported in the observation metadata when the episode was reset: facts about the starting state that judges may want, such as the scenario it started from or the clock it runs on.|
|final_state|one of: object or null|No|The environment's state() after generation, read when the episode ends. Whatever the environment chooses to report: a diff against its starting state, counters, an episode summary.|

### ToolCallLogEntryResponse

One nested tool call a sandboxed run made, as reported to a test pane.

|Field|Type|Required|Description|
|-|-|-|-|
|tool_name|string|Yes||
|arguments|object|Yes||
|output_preview|string|Yes||
|is_error|boolean|Yes||
|duration_ms|integer|Yes||

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
