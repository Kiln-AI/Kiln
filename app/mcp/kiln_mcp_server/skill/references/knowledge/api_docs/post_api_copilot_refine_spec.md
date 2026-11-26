# Refine Spec

**POST /api/copilot/refine_spec**

**Tags:** Copilot

Propose edits to a spec's fields from the user's feedback on examples (needs
Kiln Pro). Saves nothing.

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
|target_specification.spec_fields|object|Yes||
|target_specification.spec_field_current_values|object|Yes||
|examples_with_feedback|array of ExampleWithFeedbackApi|Yes||

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|new_proposed_spec_edits|array of NewProposedSpecEditApi||
|not_incorporated_feedback|one of: string or null||
|suggested_name|one of: string or null||

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

### ExampleWithFeedbackApi

An example with user feedback for spec refinement.

|Field|Type|Required|Description|
|-|-|-|-|
|user_agrees_with_judge|boolean|Yes||
|input|string|Yes||
|output|string|Yes||
|fails_specification|boolean|Yes||
|user_feedback|one of: string or null|No||

### NewProposedSpecEditApi

A proposed edit to a spec field.

|Field|Type|Required|Description|
|-|-|-|-|
|spec_field_name|string|Yes||
|proposed_edit|string|Yes||
|reason_for_edit|string|Yes||

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
