# Question Spec

**POST /api/copilot/question_spec**

**Tags:** Copilot

Generate clarifying questions about a draft spec for the user to answer
(needs Kiln Pro).

## Request

### Request Body

**Content Type:** `application/json`

|Field|Type|Required|Description|
|-|-|-|-|
|project_id|one of: string or null|No|The project holding the target task. Pair with task_id to have the server attach the task's tools and skills.|
|task_id|one of: string or null|No|The target task. Pair with project_id to have the server attach the task's tools and skills.|
|run_config_id|one of: string or null|No|The task run config whose tools and skills to attach — the one this request is about, such as the run config an eval is being written against. Omit to use the task's default run config.|
|target_task_info.task_prompt|string|Yes|The task's prompt.|
|target_task_info.task_input_schema|string|Yes|The task's input JSON schema.|
|target_task_info.task_output_schema|string|Yes|The task's output JSON schema.|
|target_task_info.task_tools|one of: array of TaskToolInfoApi or null|No|Tools available to the task. Omit if not collected; send [] if the task has none.|
|target_task_info.task_skills|one of: array of TaskToolInfoApi or null|No|Skills available to the task. Omit if not collected; send [] if the task has none.|
|target_specification|string|Yes|The specification to analyze|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|questions|array of Question|A set of questions to ask about the specification|

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

### AnswerOption

|Field|Type|Required|Description|
|-|-|-|-|
|answer_title|string|Yes|A short title describing this answer option|
|answer_description|string|Yes|A description of this answer|

### Question

|Field|Type|Required|Description|
|-|-|-|-|
|question_title|string|Yes|A short title for this question|
|question_body|string|Yes|The full question text|
|answer_options|array of AnswerOption|Yes|A list of possible answers to this question for the user to select from|

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
