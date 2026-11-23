# Create Run Config

**POST /api/projects/{project_id}/tasks/{task_id}/run_configs**

**Tags:** Run Configs

Create a run config for the task: the model, prompt, tools and settings to
run it with.

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
|name|one of: string or null|No|The name of the run config.|
|description|one of: string or null|No|The description of the run config.|
|run_config_properties|one of: KilnAgentRunConfigProperties, McpRunConfigProperties|Yes|The run configuration properties.|
|provenance|one of: KilnArtifactProvenance or null|No|Provenance: why this run config exists and what it was derived from.|

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
|name|string|The name of the task run config. 1-120 chars|
|description|one of: string or null|The description of the task run config.|
|run_config_properties|one of: KilnAgentRunConfigProperties, McpRunConfigProperties|The run config properties to use for this task run.|
|prompt|one of: BasePrompt or null|A prompt to use for run config.|
|starred|boolean|Whether this run config is starred/favourited by the user.|
|provenance|one of: KilnArtifactProvenance or null|Why this artifact exists and what it was derived from.|
|model_type|string||

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
