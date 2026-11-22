# Get Tool Server

**GET /api/projects/{project_id}/tool_servers/{tool_server_id}**

**Tags:** Tools & MCP

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|tool_server_id|string|Yes|The unique identifier of the tool server.|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|id|one of: string or null||
|type|string|Enumeration of supported external tool server types. One of: remote_mcp, local_mcp, kiln_task|
|name|string||
|description|one of: string or null||
|created_at|one of: string or null||
|created_by|one of: string or null||
|properties|one of: LocalServerProperties, RemoteServerProperties, KilnTaskServerProperties||
|available_tools|array of ExternalToolApiDescription||
|missing_secrets|array of string||

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### LocalServerProperties

|Field|Type|Required|Description|
|-|-|-|-|
|command|string|Yes||
|args|array of string|No||
|env_vars|object|No||
|secret_env_var_keys|array of string|No||
|is_archived|boolean|Yes||

### RemoteServerProperties

|Field|Type|Required|Description|
|-|-|-|-|
|server_url|string|Yes||
|headers|object|No||
|secret_header_keys|array of string|No||
|is_archived|boolean|Yes||

### KilnTaskServerProperties

|Field|Type|Required|Description|
|-|-|-|-|
|task_id|string|Yes||
|run_config_id|string|Yes||
|name|string|Yes||
|description|string|Yes||
|is_archived|boolean|Yes||

### ExternalToolApiDescription

This class is a wrapper of MCP's Tool / KilnTaskTool objects to be displayed in the UI under tool_server/[tool_server_id].

|Field|Type|Required|Description|
|-|-|-|-|
|name|string|Yes||
|description|one of: string or null|Yes||
|inputSchema|object|No||
|outputSchema|one of: object or null|No||

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
