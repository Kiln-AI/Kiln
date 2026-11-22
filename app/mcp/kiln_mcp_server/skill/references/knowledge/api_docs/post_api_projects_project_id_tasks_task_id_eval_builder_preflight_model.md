# Preflight a Model Lane

**POST /api/projects/{project_id}/tasks/{task_id}/eval_builder/preflight_model**

**Tags:** Eval Builder

One cheap completion through the SAME adapter model/provider
resolution a real run uses (that resolution is where a dead model
surfaces), on the user's same keys. Catches key/billing/deprecation/
unreachable failures for a lane BEFORE the drive commits the
plan/SU-gen minutes and the batch's model spend. Explicitly does NOT
validate tools/MCP or mid-run rate limits. Nothing persists:
allow_saving=False, so no TaskRun lands in the dataset — same as
the transient review judge.

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
|model_name|string|Yes|The model to verify.|
|model_provider|string|Yes|Enumeration of supported AI model providers. One of: openai, groq, amazon_bedrock, ollama, openrouter, fireworks_ai, kiln_fine_tune, kiln_custom_registry, openai_compatible, anthropic, gemini_api, azure_openai, huggingface, vertex, together_ai, siliconflow_cn, cerebras, docker_model_runner, featherless_ai, cloudflare, typesafe|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|ok|boolean|One of: True|

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
