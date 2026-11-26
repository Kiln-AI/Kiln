# Generate Multi-Turn SU Cases

**POST /api/projects/{project_id}/tasks/{task_id}/multiturn_sdg/generate_cases**

**Tags:** Multiturn SDG

Generate synthetic-user cases (persona, goal, first message) for a multi-turn
task (needs Kiln Pro). Saves nothing.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|ID of the project containing the target task.|
|task_id|string|Yes|ID of the target task. Must be a multi-turn task.|

### Request Body

**Content Type:** `application/json`

|Field|Type|Required|Description|
|-|-|-|-|
|target_specification|string|Yes|>=1 chars|
|case_prompts|array of string|Yes|One scenario prompt per case (e.g. from an approved batch plan). A case that fails to generate is dropped, so the response can hold fewer cases than prompts; scenario_index maps each case to its prompt.|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|cases|array of object|A SyntheticUserCase. Shape: {seed_prompt: str, synthetic_user_info: str, scenario_index?: int | null}. The synthetic_user_info value is an XML-tagged blob: <persona>...</persona><goal>...</goal><behavior_guidance>...</behavior_guidance>. Parsed client-side by kiln_ai.synthetic_user.parser. scenario_index maps the case back to its plan prompt.|

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
