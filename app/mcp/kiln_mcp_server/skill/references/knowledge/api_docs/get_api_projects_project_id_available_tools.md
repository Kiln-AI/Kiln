# Get Available Tools

**GET /api/projects/{project_id}/available_tools**

**Tags:** Tools & MCP

List every tool the project's tasks can use, grouped by kind.

The kinds are built-in tools, MCP servers, search tools, Kiln task tools
and code tools.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|

## Responses

### 200 OK

Successful Response

**Body:** array of ToolSetApiDescription

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### ToolApiDescription

A tool as shown in pickers: name is the user-facing display name,
function_name the callable name the model sees (they often coincide).

|Field|Type|Required|Description|
|-|-|-|-|
|id|string|Yes||
|name|string|Yes||
|description|one of: string or null|Yes||
|function_name|one of: string or null|No||

### ToolSetApiDescription

|Field|Type|Required|Description|
|-|-|-|-|
|type|string|Yes|One of: search, mcp, kiln_task, demo, skill, builtin, code, sandbox_code|
|set_name|string|Yes||
|tools|array of ToolApiDescription|Yes||

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
