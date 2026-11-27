# Build Prompt With Examples

**POST /api/projects/{project_id}/tasks/{task_id}/build_prompt_with_examples**

**Tags:** Prompts

Build a prompt with the task's prompt, requirements, and optional custom examples.

Uses the same formatting as the FewShotPromptBuilder but with user-provided examples.
When the task has a default run config, that run config's prompt is used as the base
(so synthetic data reflects the production prompt) instead of the task instruction.

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
|examples|array of FewShotExample|No|Few-shot examples to include in the prompt.|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|prompt|string|The generated prompt text.|

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### FewShotExample

An input/output example for few-shot prompting.

|Field|Type|Required|Description|
|-|-|-|-|
|input|string|Yes|The example input.|
|output|string|Yes|The example output.|

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
