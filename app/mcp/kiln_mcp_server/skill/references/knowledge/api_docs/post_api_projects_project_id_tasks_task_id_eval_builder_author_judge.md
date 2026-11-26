# Author Judge

**POST /api/projects/{project_id}/tasks/{task_id}/eval_builder/author_judge**

**Tags:** Eval Builder

Author a spec-tailored judge prompt for the review — both arms.

Returns the PROMPT only — the judge model is the user's pick. Both
arms judge a transcript, so both rubrics are authored against one:
the rubric arrives knowing the role labels and tool-call blocks its
judge will meet, whatever the task's turn mode.
Authoring is a REQUIRED step of the drive: an error here stops the
drive on a retryable error client-side. There is no fallback judge.

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
|target_specification|string|Yes|>=1 chars|
|target_task_prompt|string|Yes||
|run_config_id|one of: string or null|No|The task run config the eval is written against. Its tools and skills are what the rubric grades tool and skill use over. Omit to use the task's default run config.|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|judge_prompt|string||

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
