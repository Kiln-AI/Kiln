# Get Tool Definition

**GET /api/projects/{project_id}/tasks/{task_id}/tools/{tool_id}/definition**

**Tags:** Tools & MCP

Get the actual OpenAI tool definition for a specific tool ID.

This returns the real function name and parameters that would be used
in OpenAI function calls, not the display names from ToolSetApiDescription.

Args:
    project_id: The project ID
    task_id: The task ID for tools that require task context
    tool_id: The tool ID to get the definition for

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|task_id|string|Yes|The unique identifier of the task within the project.|
|tool_id|string|Yes|The unique identifier of the tool.|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|tool_id|string||
|function_name|string||
|description|string||
|parameters|object||

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
