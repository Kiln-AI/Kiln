# Run Multi-Turn Pipeline

**POST /api/projects/{project_id}/tasks/{task_id}/eval_builder/multi_turn_pipeline**

**Tags:** Eval Builder

The merged multi-turn stream: [drive → judge] per case.

Emits (all frames `type`-discriminated; errors carry {code, message}):
  - batch_started   { batch_tag, total_cases }
  - turn_completed  { case_index, turns_completed, total_turns }
  - case_driven     { case_index, leaf_run_id }
  - case_judged     { case_index, leaf_run_id, raw_input, raw_output,
                      judge_score, judge_reasoning, total_cost }
  - case_failed     { case_index, stage, code, message, error_type }
                      (batch continues)
  - batch_completed { judged, failed, batch_tag, total_cost }
  - batch_aborted   { error, stage }  (in place of batch_completed:
                      a config-scoped judge failure aborted the whole
                      batch; results already streamed remain valid)
  - batch_failed    { code, message }  (in place of batch_completed:
                      an orchestration-level crash ended the stream;
                      results already streamed remain valid)
Terminated by `data: complete`. Claims are built afterwards, per
opened trace, via build_claims.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|task_id|string|Yes|The unique identifier of the task.|

### Request Body

**Content Type:** `application/json`

|Field|Type|Required|Description|
|-|-|-|-|
|replace_batch_tags|array of string|No|Batch tags of previous drives this one supersedes (aborted re-drives can leave several behind). Their runs are deleted once this drive has produced replacements (delete-on-redrive), so abandoned batches don't accumulate on disk — and a wholesale drive failure never destroys the only batch the user has.|
|target_run_config|one of: KilnAgentRunConfigProperties, McpRunConfigProperties or null|No|Inline run config for the target task, used verbatim — the same full properties shape a manual run sends, tools included. For driving a config that isn't worth saving (ad-hoc experiments, scripting). Must be a Kiln agent config. Exactly one of target_run_config / target_run_config_id is required.|
|target_run_config_id|one of: string or null|No|ID of one of the target task's saved run configs. The drive uses the saved config verbatim — model, prompt, sampling, and tools — so the agent under test behaves exactly like a manual run, and driven runs attribute back to the config. Exactly one of target_run_config / target_run_config_id is required.|
|cases|array of object|Yes|Cases as returned by /generate_cases, optionally edited. A SyntheticUserCase. Shape: {seed_prompt: str, synthetic_user_info: str, scenario_index?: int | null}. The synthetic_user_info value is an XML-tagged blob: <persona>...</persona><goal>...</goal><behavior_guidance>...</behavior_guidance>. Parsed client-side by kiln_ai.synthetic_user.parser. scenario_index maps the case back to its plan prompt.|
|turns|integer|No|Ceiling on the assistant turns produced per case. 1.0-20.0|
|su_driver.model_name|string|Yes|>=1 chars|
|su_driver.model_provider|string|Yes|Enumeration of supported AI model providers. One of: openai, groq, amazon_bedrock, ollama, openrouter, fireworks_ai, kiln_fine_tune, kiln_custom_registry, openai_compatible, anthropic, gemini_api, azure_openai, huggingface, vertex, together_ai, siliconflow_cn, cerebras, docker_model_runner, featherless_ai, cloudflare, typesafe|
|batch_tag|one of: string or null|No|Optional user-supplied batch label. Constrained to [A-Za-z0-9_-]{1,64} so it can safely be used as a tag on leaf TaskRuns. Auto-generated if not provided.|
|judge.prompt|string|Yes||
|judge.model_name|string|Yes||
|judge.model_provider|string|Yes|Enumeration of supported AI model providers. One of: openai, groq, amazon_bedrock, ollama, openrouter, fireworks_ai, kiln_fine_tune, kiln_custom_registry, openai_compatible, anthropic, gemini_api, azure_openai, huggingface, vertex, together_ai, siliconflow_cn, cerebras, docker_model_runner, featherless_ai, cloudflare, typesafe|

## Responses

### 200 OK

Successful Response

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

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

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
