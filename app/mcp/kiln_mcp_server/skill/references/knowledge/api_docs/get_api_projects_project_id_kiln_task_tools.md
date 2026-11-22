# Get Kiln Task Tools

**GET /api/projects/{project_id}/kiln_task_tools**

**Tags:** Tools & MCP

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|

## Responses

### 200 OK

Successful Response

**Body:** array of KilnTaskToolDescription

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### KilnTaskToolDescription

This class is used to describe Kiln Task tools with their associated task information.

|Field|Type|Required|Description|
|-|-|-|-|
|tool_server_id|string|Yes||
|tool_name|string|Yes||
|tool_description|one of: string or null|Yes||
|task_id|string|Yes||
|task_name|string|Yes||
|task_description|one of: string or null|Yes||
|is_archived|boolean|Yes||
|created_at|string|Yes|Format: date-time|

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
