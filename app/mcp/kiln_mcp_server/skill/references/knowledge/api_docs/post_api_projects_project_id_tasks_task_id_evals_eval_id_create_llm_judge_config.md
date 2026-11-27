# Create LLM Judge Eval Config

**POST /api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/create_llm_judge_config**

**Tags:** Evals

Create an LLM judge for an eval from a judge prompt and model; Kiln builds
the judge's template.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|task_id|string|Yes|The unique identifier of the task within the project.|
|eval_id|string|Yes|The unique identifier of the eval.|

### Request Body

**Content Type:** `application/json`

|Field|Type|Required|Description|
|-|-|-|-|
|model_name|string|Yes|The LLM model to use as judge.|
|provider|string|Yes|Enumeration of supported AI model providers. One of: openai, groq, amazon_bedrock, ollama, openrouter, fireworks_ai, kiln_fine_tune, kiln_custom_registry, openai_compatible, anthropic, gemini_api, azure_openai, huggingface, vertex, together_ai, siliconflow_cn, cerebras, docker_model_runner, featherless_ai, cloudflare, typesafe|
|g_eval|boolean|Yes|Whether to use G-Eval logprob scoring.|
|judge_prompt|one of: string or null|No|Override the judge prompt template. If unset, the server assembles a rich default from the eval's task and spec.|
|system_prompt|one of: string or null|No|Override the judge system prompt. Defaults to 'You are an evaluator.'|
|judge_instructions|one of: array of string or null|No|User-written evaluation steps, bound to {{ judge_instructions }} when the judge prompt is rendered. Used by evals with no spec or template to derive default steps from.|
|run_config|one of: LlmJudgeRunConfig or null|No|Optional settings for the judge model call (thinking level, temperature, top_p). Each unset field keeps its default.|
|name|one of: string or null|No|The name of the eval config.|
|provenance|one of: KilnArtifactProvenance or null|No|Provenance: why this eval config exists and what it was derived from.|

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
|name|string|The name of the eval config. 1-120 chars|
|model_name|one of: string or null|The name of the model to use for this eval config. Required for legacy configs, None for V2.|
|model_provider|one of: string or null|The provider of the model to use for this eval config. Required for legacy configs, None for V2.|
|config_type|string|The type of eval configuration, determining how scores are generated. One of: g_eval, llm_as_judge, v2|
|properties|one of: object, LlmJudgeProperties, ExactMatchProperties, PatternMatchProperties, SetCheckProperties, ToolCallCheckProperties, ContainsProperties, StepCountCheckProperties, CodeEvalProperties or null|Properties to be used to execute the eval config. Legacy configs use a dict; V2 configs use typed properties.|
|provenance|one of: KilnArtifactProvenance or null|Why this artifact exists and what it was derived from.|
|model_type|string||

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

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
