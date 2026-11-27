# Tasks Compatible With Tool

**GET /api/projects/{project_id}/tasks_compatible_with_tool**

**Tags:** Tasks

List the project's tasks, each marked whether its input and output fit an MCP
tool's schemas.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|

### Query Parameters

|Name|Type|Required|Default|Description|
|-|-|-|-|-|
|tool_id|string|Yes||The unique identifier of the tool.|

## Responses

### 200 OK

Successful Response

**Body:** array of TaskToolCompatibility

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### TaskToolCompatibility

Whether a task is compatible with a specific tool.

|Field|Type|Required|Description|
|-|-|-|-|
|task_id|string|Yes|The unique identifier of the task.|
|task_name|string|Yes|The human-readable name of the task.|
|compatible|boolean|Yes|Whether the task is compatible with the tool.|
|incompatibility_reason|one of: string or null|No|Why the task is incompatible, if applicable.|

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
