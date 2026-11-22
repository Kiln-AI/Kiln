# List Available Models

**GET /api/available_models**

**Tags:** Providers & Models

## Responses

### 200 OK

Successful Response

**Body:** array of AvailableModels

## Schemas

### ModelDetails

|Field|Type|Required|Description|
|-|-|-|-|
|id|string|Yes||
|name|string|Yes||
|supports_structured_output|boolean|Yes||
|supports_data_gen|boolean|Yes||
|suggested_for_data_gen|boolean|Yes||
|supports_logprobs|boolean|Yes||
|suggested_for_evals|boolean|Yes||
|suggested_for_synthetic_user|boolean|Yes||
|supports_function_calling|boolean|Yes||
|uncensored|boolean|Yes||
|suggested_for_uncensored_data_gen|boolean|Yes||
|supports_vision|boolean|Yes||
|supports_doc_extraction|boolean|Yes||
|suggested_for_doc_extraction|boolean|Yes||
|multimodal_capable|boolean|No||
|multimodal_mime_types|one of: array of string or null|No||
|structured_output_mode|string|Yes|Enumeration of supported structured output modes.

- json_schema: request json using API capabilities for json_schema
- function_calling: request json using API capabilities for function calling
- json_mode: request json using API's JSON mode, which should return valid JSON, but isn't checking/passing the schema
- json_instructions: append instructions to the prompt to request json matching the schema. No API capabilities are used. You should have a custom parser on these models as they will be returning strings.
- json_instruction_and_object: append instructions to the prompt to request json matching the schema. Also request the response as json_mode via API capabilities (returning dictionaries).
- json_custom_instructions: The model should output JSON, but custom instructions are already included in the system prompt. Don't append additional JSON instructions.
- default: let the adapter decide (legacy, do not use for new use cases)
- unknown: used for cases where the structured output mode is not known (on old models where it wasn't saved). Should lookup best option at runtime. One of: default, json_schema, function_calling_weak, function_calling, json_mode, json_instructions, json_instruction_and_object, json_custom_instructions, unknown|
|available_thinking_levels|one of: object or null|No||
|default_thinking_level|one of: string or null|No||
|untested_model|boolean|No||
|task_filter|one of: array of string or null|No||
|model_specific_run_config|one of: string or null|No||
|deprecated|boolean|No||

### AvailableModels

|Field|Type|Required|Description|
|-|-|-|-|
|provider_name|string|Yes||
|provider_id|string|Yes||
|models|array of ModelDetails|Yes||
