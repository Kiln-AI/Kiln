# Generate Outputs Batch

**POST /api/projects/{project_id}/tasks/{task_id}/generate_outputs_batch**

**Tags:** Synthetic Data

Start an in-process job that runs the task on each input in parallel.
Poll the status endpoint for progress and the resulting (unsaved) runs.

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
|items|array of GenerateOutputsBatchItem|Yes|The inputs to generate outputs for.|
|input_model_name|string|Yes|The model used to generate the inputs (recorded on each run).|
|input_provider|string|Yes|The provider used to generate the inputs (recorded on each run).|
|run_config_properties|one of: KilnAgentRunConfigProperties, McpRunConfigProperties|Yes|The run config properties to use for output generation.|
|guidance|one of: string or null|No|Optional custom guidance for output generation.|
|session_id|one of: string or null|No|Optional session ID to group generated samples.|
|tags|one of: array of string or null|No|Tags to add to each generated sample.|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|job_id|string|Identifier for the started batch job.|

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### GenerateOutputsBatchItem

|Field|Type|Required|Description|
|-|-|-|-|
|index|integer|Yes|Stable index of this item within the batch.|
|input|one of: string, object|Yes|The generated input to run the task on.|

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
