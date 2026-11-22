# Refine Task Data Guide

**POST /api/projects/{project_id}/tasks/{task_id}/data_gen_guide_refine**

**Tags:** Synthetic Data

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
|current_guide|string|No|Markdown body of the current input data guide — the metaprompter rewrites it wholesale.|
|source|one of: string or null|No|Which flow owns the in-memory guide, so the metaprompter branches correctly during the pre-save refine loop. When omitted, falls back to the persisted guide's source (correct only once the guide is saved).|
|feedback|string|Yes|User feedback on what's wrong with the previewed inputs|
|preview_samples|array of RatedSample|Yes|The previewed inputs the user is giving feedback on, each rated by the user as realistic (true) or needs work (false)|
|run_config_properties.type|string|No|One of: kiln_agent|
|run_config_properties.model_name|string|Yes|The model to use for this run config.|
|run_config_properties.model_provider_name|string|Yes|Enumeration of supported AI model providers. One of: openai, groq, amazon_bedrock, ollama, openrouter, fireworks_ai, kiln_fine_tune, kiln_custom_registry, openai_compatible, anthropic, gemini_api, azure_openai, huggingface, vertex, together_ai, siliconflow_cn, cerebras, docker_model_runner, featherless_ai, cloudflare, typesafe|
|run_config_properties.prompt_id|string|Yes|The prompt to use for this run config. Defaults to building a simple prompt from the task if not provided.|
|run_config_properties.top_p|number|No|The top-p value to use for this run config. Defaults to 1.0.|
|run_config_properties.temperature|number|No|The temperature to use for this run config. Defaults to 1.0.|
|run_config_properties.structured_output_mode|string|Yes|Enumeration of supported structured output modes.

- json_schema: request json using API capabilities for json_schema
- function_calling: request json using API capabilities for function calling
- json_mode: request json using API's JSON mode, which should return valid JSON, but isn't checking/passing the schema
- json_instructions: append instructions to the prompt to request json matching the schema. No API capabilities are used. You should have a custom parser on these models as they will be returning strings.
- json_instruction_and_object: append instructions to the prompt to request json matching the schema. Also request the response as json_mode via API capabilities (returning dictionaries).
- json_custom_instructions: The model should output JSON, but custom instructions are already included in the system prompt. Don't append additional JSON instructions.
- default: let the adapter decide (legacy, do not use for new use cases)
- unknown: used for cases where the structured output mode is not known (on old models where it wasn't saved). Should lookup best option at runtime. One of: default, json_schema, function_calling_weak, function_calling, json_mode, json_instructions, json_instruction_and_object, json_custom_instructions, unknown|
|run_config_properties.thinking_level|one of: string or null|No|The thinking level to use for this run config. If None, defaults may apply.|
|run_config_properties.tools_config|one of: ToolsRunConfig or null|No|The tools config to use for this run config, defining which tools are available to the model.|
|run_config_properties.input_transform|one of: JinjaInputTransform or null|No|Optional transform applied to the task input at run time, producing the first user message sent to the model. Default None preserves the identity path.|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|refined_guide|string|The refined input data guide markdown returned by the metaprompter.|

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### RatedSample

A previewed input sample plus the user's rating, used as feedback input
to the input-data-guide refinement metaprompter. Shared between the API
surface and the prompt builder so callers don't have to flatten into
positional tuples.

|Field|Type|Required|Description|
|-|-|-|-|
|input|string|Yes|Generated sample input|
|looks_good|boolean|Yes|User rating: true if the input looks realistic, false if it needs work|

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

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
