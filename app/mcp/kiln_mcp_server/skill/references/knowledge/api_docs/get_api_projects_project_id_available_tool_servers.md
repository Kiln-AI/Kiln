# Get Available Tool Servers

**GET /api/projects/{project_id}/available_tool_servers**

**Tags:** Tools & MCP

List the project's tool servers, with any secrets they are missing.

Tool servers are remote and local MCP servers and Kiln task tools.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|

## Responses

### 200 OK

Successful Response

**Body:** array of KilnToolServerDescription

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### KilnToolServerDescription

This class is used to describe the external tool server under Settings -> Manage Tools UI.

|Field|Type|Required|Description|
|-|-|-|-|
|name|string|Yes||
|id|one of: string or null|Yes||
|type|string|Yes|Enumeration of supported external tool server types. One of: remote_mcp, local_mcp, kiln_task|
|description|one of: string or null|Yes||
|missing_secrets|array of string|Yes||
|is_archived|boolean|Yes||

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
