# Generate Batch

**POST /api/copilot/generate_batch**

**Tags:** Copilot

## Request

### Request Body

**Content Type:** `application/json`

|Field|Type|Required|Description|
|-|-|-|-|
|target_task_info.task_prompt|string|Yes|The task's prompt.|
|target_task_info.task_input_schema|string|Yes|The task's input JSON schema.|
|target_task_info.task_output_schema|string|Yes|The task's output JSON schema.|
|target_task_info.task_tools|one of: array of TaskToolInfoApi or null|No|Tools available to the task. Omit if not collected; send [] if the task has none.|
|target_task_info.task_skills|one of: array of TaskToolInfoApi or null|No|Skills available to the task. Omit if not collected; send [] if the task has none.|
|target_specification|string|Yes||
|num_samples_per_topic|integer|Yes||
|num_topics|integer|Yes||
|sdg_session_config.topic_generation_config.task_metadata|TaskMetadataApi|Yes|Metadata about the model used for a task.|
|sdg_session_config.topic_generation_config.prompt|string|Yes||
|sdg_session_config.input_generation_config.task_metadata|TaskMetadataApi|Yes|Metadata about the model used for a task.|
|sdg_session_config.input_generation_config.prompt|string|Yes||
|sdg_session_config.output_generation_config.task_metadata|TaskMetadataApi|Yes|Metadata about the model used for a task.|
|sdg_session_config.output_generation_config.prompt|string|Yes||

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|data_by_topic|object||

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### TaskToolInfoApi

A tool the target task can call. Name and description only.

|Field|Type|Required|Description|
|-|-|-|-|
|name|string|Yes|The tool's name, as the model sees it.|
|description|string|Yes|What the tool does. Never its parameter schema.|

### TaskMetadataApi

Metadata about the model used for a task.

|Field|Type|Required|Description|
|-|-|-|-|
|model_name|string|Yes|The name of the AI model used.|
|model_provider_name|string|Yes|Enumeration of supported AI model providers. One of: openai, groq, amazon_bedrock, ollama, openrouter, fireworks_ai, kiln_fine_tune, kiln_custom_registry, openai_compatible, anthropic, gemini_api, azure_openai, huggingface, vertex, together_ai, siliconflow_cn, cerebras, docker_model_runner, featherless_ai, cloudflare, typesafe|

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
