# Get Eval Run Results

**GET /api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/eval_config/{eval_config_id}/run_config/{run_config_id}/results**

**Tags:** Evals

Results for one run config, scoped to one of the eval's splits.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|task_id|string|Yes|The unique identifier of the task within the project.|
|eval_id|string|Yes|The unique identifier of the eval.|
|eval_config_id|string|Yes|The unique identifier of the eval configuration.|
|run_config_id|string|Yes|The unique identifier of the run configuration.|

### Query Parameters

|Name|Type|Required|Default|Description|
|-|-|-|-|-|
|split|string|Yes||Which of the eval's dataset splits to return results for. Required: every response about eval results is scoped to exactly one split, and reading has no obvious default the way running does. One of: train, val, test|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|results|array of EvalRunWithTrace|The individual eval run results.|
|eval.v|integer|Schema version for migration support.|
|eval.id|one of: string or null|Unique identifier for this record.|
|eval.path|one of: string or null|File system path where the record is stored.|
|eval.created_at|string|Timestamp when the model was created. Timezone-aware; stores the writer's local offset. Format: date-time|
|eval.created_by|string|User ID of the creator.|
|eval.name|string|The name of the eval. 1-120 chars|
|eval.description|one of: string or null|The description of the eval|
|eval.template|one of: string or null|The template selected when creating this eval. Useful for suggesting eval steps and output scores.|
|eval.current_config_id|one of: string or null|The id of the current config to use for this eval. This can be changed over time to run the same eval with different configs.|
|eval.eval_set_filter_id|one of: string or null|Deprecated, and neither read nor written. It exists only so evals written by a Kiln build that predates `splits` still load: on load its value is migrated into splits['test'] once, and the field is then cleared. It is always saved as null. Read splits['test'] instead.|
|eval.eval_configs_filter_id|one of: string or null|The id of the dataset filter which defines which dataset items are included when comparing the quality of the eval configs under this eval. Should consist of dataset items with ratings.|
|eval.train_set_filter_id|one of: string or null|Deprecated, and neither read nor written. It exists only so evals written by a Kiln build that predates `splits` still load: on load its value is migrated into splits['train'] once, and the field is then cleared. It is always saved as null. Read splits['train'] instead.|
|eval.splits|object|The eval's dataset splits, keyed by split name ('test', 'train', 'val'), and the only place they are stored. Each split names the store its items come from and the filter that selects them. Keys this build doesn't know are preserved but not exposed. 'golden' is not a split and does not belong here: the golden set must be dataset (TaskRun) based, because human ratings only exist on dataset items, so it is stored in eval_configs_filter_id instead. Nothing reads splits['golden'] — writing it is accepted and silently ignored. In Python, prefer Eval.set_split() to assigning into this dict: it refuses to mutate a readonly (cached) eval, and marks the field as set so exclude_unset dumps keep it.|
|eval.output_scores|array of EvalOutputScore|The scores this evaluator should produce.|
|eval.favourite|boolean|Whether this eval is a favourite of the user. Rendered as a star icon in the UI.|
|eval.priority|one of: integer or null|The priority of the eval. None on evals created before priority lived on evals; read through resolved_priority(), which falls back to the associated spec.|
|eval.status|one of: string or null|The status of the eval. None on evals created before status lived on evals; read through resolved_status(), which falls back to the associated spec.|
|eval.template_properties|one of: object or null|Properties to be used to execute the eval. This is template_type specific and should serialize to a json dict.|
|eval.evaluation_data_type|one of: string or null|The output of the task run to evaluate. Can be final answer, full trace, or None for V2 evals.|
|eval.model_type|string||
|eval_config.v|integer|Schema version for migration support.|
|eval_config.id|one of: string or null|Unique identifier for this record.|
|eval_config.path|one of: string or null|File system path where the record is stored.|
|eval_config.created_at|string|Timestamp when the model was created. Timezone-aware; stores the writer's local offset. Format: date-time|
|eval_config.created_by|string|User ID of the creator.|
|eval_config.name|string|The name of the eval config. 1-120 chars|
|eval_config.model_name|one of: string or null|The name of the model to use for this eval config. Required for legacy configs, None for V2.|
|eval_config.model_provider|one of: string or null|The provider of the model to use for this eval config. Required for legacy configs, None for V2.|
|eval_config.config_type|string|The type of eval configuration, determining how scores are generated. One of: g_eval, llm_as_judge, v2|
|eval_config.properties|one of: object, LlmJudgeProperties, ExactMatchProperties, PatternMatchProperties, SetCheckProperties, ToolCallCheckProperties, ContainsProperties, StepCountCheckProperties, CodeEvalProperties or null|Properties to be used to execute the eval config. Legacy configs use a dict; V2 configs use typed properties.|
|eval_config.provenance|one of: KilnArtifactProvenance or null|Why this artifact exists and what it was derived from.|
|eval_config.model_type|string||
|run_config.v|integer|Schema version for migration support.|
|run_config.id|one of: string or null|Unique identifier for this record.|
|run_config.path|one of: string or null|File system path where the record is stored.|
|run_config.created_at|string|Timestamp when the model was created. Timezone-aware; stores the writer's local offset. Format: date-time|
|run_config.created_by|string|User ID of the creator.|
|run_config.name|string|The name of the task run config. 1-120 chars|
|run_config.description|one of: string or null|The description of the task run config.|
|run_config.run_config_properties|one of: KilnAgentRunConfigProperties, McpRunConfigProperties|The run config properties to use for this task run.|
|run_config.prompt|one of: BasePrompt or null|A prompt to use for run config.|
|run_config.starred|boolean|Whether this run config is starred/favourited by the user.|
|run_config.provenance|one of: KilnArtifactProvenance or null|Why this artifact exists and what it was derived from.|
|run_config.model_type|string||

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### Usage

Token usage, cost, and aggregate LLM latency for a per-run accumulator.

Extends :class:`MessageUsage` with ``total_llm_latency_ms``, which is
only meaningful while a single run is in flight (its model calls run
sequentially in real time). For per-message records and full-trace
sums use :class:`MessageUsage` — those values would mix latencies
from different points in time, so the field doesn't apply.

|Field|Type|Required|Description|
|-|-|-|-|
|input_tokens|one of: integer or null|No|The number of input tokens used.|
|output_tokens|one of: integer or null|No|The number of output tokens used.|
|total_tokens|one of: integer or null|No|The total number of tokens used.|
|cost|one of: number or null|No|The cost in US dollars, saved at runtime (prices can change over time).|
|cached_tokens|one of: integer or null|No|Number of tokens served from prompt cache. None if not reported.|
|cache_write_tokens|one of: integer or null|No|Number of input tokens written to the prompt cache, which providers bill above the normal input price. None if not reported.|
|total_llm_latency_ms|one of: integer or null|No|Total time spent waiting on LLM API calls in milliseconds. Sum of per-call latencies, excludes tool execution time.|

### EvalRunWithTrace

An eval's scores for one item, plus the trace those scores were computed over.

Where the trace lives depends on the record: on a TaskRun named by `scored_run_id`,
inline on the EvalRun for records written before the trace/score split, or nowhere at
all for a run that was skipped before anything was generated. This resolves whichever
applies - falling back to the dataset item for the input whenever the record
itself has none - so callers see one shape regardless of which it is.

|Field|Type|Required|Description|
|-|-|-|-|
|eval_run.v|integer|No|Schema version for migration support.|
|eval_run.id|one of: string or null|No|Unique identifier for this record.|
|eval_run.path|one of: string or null|No|File system path where the record is stored.|
|eval_run.created_at|string|No|Timestamp when the model was created. Timezone-aware; stores the writer's local offset. Format: date-time|
|eval_run.created_by|string|No|User ID of the creator.|
|eval_run.dataset_id|one of: string or null|No|The ID of the dataset item (TaskRun) that was used for this run. Mutually exclusive with eval_input_id.|
|eval_run.scored_run_id|one of: string or null|No|The ID of the TaskRun this score was computed over. None for legacy records that carry their trace inline. A dangling reference is tolerated: the score still renders and still aggregates, only the trace drill-through is unavailable.|
|eval_run.task_run_config_id|one of: string or null|Yes|The ID of the TaskRunConfig that was run, if this eval run was based on a task run. Must belong to the same Task as this eval. Can be None if this eval run is based on an eval config.|
|eval_run.eval_config_eval|boolean|No|Whether this eval run to evaluate the parent eval config (evaluating the config using an existing dataset item). If true, task_run_config_id must be None, as we're not running the task.|
|eval_run.input|one of: string or null|No|DEPRECATED: the trace now lives on the TaskRun named by scored_run_id; read TaskRun.input instead. The input to the task. JSON formatted for structured input, plaintext for unstructured input. Required on legacy records (those with neither a scored_run_id nor a skipped_reason), never set on new ones.|
|eval_run.output|one of: string or null|No|DEPRECATED: the trace now lives on the TaskRun named by scored_run_id; read TaskRun.output.output instead. The output of the task. None for skipped-before-execution runs.|
|eval_run.reference_answer|one of: string or null|No|DEPRECATED: the trace now lives on the TaskRun named by scored_run_id. The reference answer for the input. JSON formatted for structured reference answer, plaintext for unstructured reference answer. Used for reference answer evals.|
|eval_run.intermediate_outputs|one of: object or null|No|The intermediate outputs of the task (example, eval thinking).|
|eval_run.task_run_trace|one of: string or null|No|DEPRECATED: the trace now lives on the TaskRun named by scored_run_id; read TaskRun.trace instead. The JSON formatted trace of the task run that produced the output.|
|eval_run.scores|object|No|The output scores of the evaluator (aligning to those required by the grand-parent Eval this object is a child of).|
|eval_run.task_run_usage|one of: Usage or null|No|DEPRECATED: the trace now lives on the TaskRun named by scored_run_id; read TaskRun.usage instead. The usage of the task run that produced this eval run output (not the usage by the evaluation model).|
|eval_run.eval_usage|one of: Usage or null|No|The usage of the evaluation model (judge) that produced this eval run's scores, aggregated across every LLM call the judgment made. Distinct from task_run_usage, which is the evaluated task run's usage. None for non-LLM evals (e.g. code evals) and for records that predate this field.|
|eval_run.judge_trace|one of: array of one of: object, object, object, object, object, object or null|No|The judge's full conversation in OpenAI format: the system prompt, the rendered judge prompt, and every reply. Structured messages, unlike the deprecated JSON-string task_run_trace. None for V1 evals, for evals that call no model (e.g. code evals), and for records that predate this field. Distinct from the evaluated task run's trace.|
|eval_run.eval_input_id|one of: string or null|No|ID of the EvalInput used for this run (V2 evals). Mutually exclusive with dataset_id.|
|eval_run.skipped_reason|one of: string or null|No|If set, this run was skipped. Stored as str for back/forward-compat; conventionally a SkippedReason value.|
|eval_run.skipped_detail|one of: string or null|No|Case-specific detail for skipped runs (e.g. missing key name).|
|eval_run.model_type|string|Yes||
|has_judge_trace|boolean|Yes|Whether the score record saved a non-empty judge_trace.|
|input|one of: string or null|Yes|The input the task was run on. From the scored TaskRun, from the EvalRun itself for legacy records, or from the dataset item whenever neither of those has it (pre-generation skips, and pointer records whose trace is missing).|
|output|one of: string or null|Yes|What the task produced. Always the original output, never a repaired one: a repair can happen after scoring, so it is not what was scored. None when nothing was generated, or when the scored TaskRun is missing.|
|task_run_trace|one of: string or null|Yes|The JSON formatted trace of the task run that produced the output, if it recorded one.|
|task_run_usage|one of: Usage or null|Yes|The usage of the task run that produced the output. Not the judge's own usage, which is on the EvalRun as eval_usage.|

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

### ToolsRunConfig

A config describing which tools are available to a task.

|Field|Type|Required|Description|
|-|-|-|-|
|tools|array of string|Yes|The IDs of the tools available to the task.|

### JinjaInputTransform

Render the task input via a Jinja2 template, producing the first user
message sent to the model. See specs/projects/templates/functional_spec.md
for the full contract.

|Field|Type|Required|Description|
|-|-|-|-|
|type|string|No|One of: jinja|
|template|string|Yes|Jinja2 template source. Validated at save time.|

### KilnAgentRunConfigProperties

A configuration for running a task using a Kiln AI agent.

This includes everything needed to run a task, except the input and task ID. Running the same RunConfig with the same input should make identical calls to the model (output may vary as models are non-deterministic).

|Field|Type|Required|Description|
|-|-|-|-|
|type|string|No|One of: kiln_agent|
|model_name|string|Yes|The model to use for this run config.|
|model_provider_name|string|Yes|Enumeration of supported AI model providers. One of: openai, groq, amazon_bedrock, ollama, openrouter, fireworks_ai, kiln_fine_tune, kiln_custom_registry, openai_compatible, anthropic, gemini_api, azure_openai, huggingface, vertex, together_ai, siliconflow_cn, cerebras, docker_model_runner, featherless_ai, cloudflare, typesafe|
|prompt_id|string|Yes|The prompt to use for this run config. Defaults to building a simple prompt from the task if not provided.|
|top_p|number|No|The top-p value to use for this run config. Defaults to 1.0.|
|temperature|number|No|The temperature to use for this run config. Defaults to 1.0.|
|structured_output_mode|string|Yes|Enumeration of supported structured output modes.

- json_schema: request json using API capabilities for json_schema
- function_calling: request json using API capabilities for function calling
- json_mode: request json using API's JSON mode, which should return valid JSON, but isn't checking/passing the schema
- json_instructions: append instructions to the prompt to request json matching the schema. No API capabilities are used. You should have a custom parser on these models as they will be returning strings.
- json_instruction_and_object: append instructions to the prompt to request json matching the schema. Also request the response as json_mode via API capabilities (returning dictionaries).
- json_custom_instructions: The model should output JSON, but custom instructions are already included in the system prompt. Don't append additional JSON instructions.
- default: let the adapter decide (legacy, do not use for new use cases)
- unknown: used for cases where the structured output mode is not known (on old models where it wasn't saved). Should lookup best option at runtime. One of: default, json_schema, function_calling_weak, function_calling, json_mode, json_instructions, json_instruction_and_object, json_custom_instructions, unknown|
|thinking_level|one of: string or null|No|The thinking level to use for this run config. If None, defaults may apply.|
|tools_config|one of: ToolsRunConfig or null|No|The tools config to use for this run config, defining which tools are available to the model.|
|input_transform|one of: JinjaInputTransform or null|No|Optional transform applied to the task input at run time, producing the first user message sent to the model. Default None preserves the identity path.|

### McpRunConfigProperties

A configuration for running a task via an MCP tool.

|Field|Type|Required|Description|
|-|-|-|-|
|type|string|No|One of: mcp|
|tool_reference.tool_id|string|Yes|The MCP tool ID to call (mcp::local|remote::<server_id>::<tool_name>).|
|tool_reference.tool_server_id|one of: string or null|No|The MCP tool server ID.|
|tool_reference.tool_name|one of: string or null|No|The MCP tool name.|
|tool_reference.input_schema|one of: object or null|No|Snapshot of the MCP tool input schema.|
|tool_reference.output_schema|one of: object or null|No|Snapshot of the MCP tool output schema.|

### BasePrompt

A prompt for a task. This is the basic data storage format which can be used throughout a project.

The "Prompt" model name is reserved for the custom prompts parented by a task.

|Field|Type|Required|Description|
|-|-|-|-|
|name|string|Yes|The name of the prompt. 1-120 chars|
|description|one of: string or null|No|A more detailed description of the prompt.|
|generator_id|one of: string or null|No|The id of the generator that created this prompt.|
|prompt|string|Yes|The prompt for the task. >=1 chars|
|chain_of_thought_instructions|one of: string or null|No|Instructions for the model 'thinking' about the requirement prior to answering. Used for chain of thought style prompting. COT will not be used unless this is provided.|

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
