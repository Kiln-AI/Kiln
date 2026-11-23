# Connect Local Mcp

**POST /api/projects/{project_id}/connect_local_mcp**

**Tags:** Tools & MCP

Add a local MCP server (a command Kiln starts) to the project as a tool
server.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|

### Request Body

**Content Type:** `application/json`

|Field|Type|Required|Description|
|-|-|-|-|
|name|string|Yes|The name of the tool server.|
|description|one of: string or null|No|A description of the tool server.|
|command|string|Yes|The command to start the local MCP server.|
|args|array of string|No|Command-line arguments for the server.|
|env_vars|object|No|Environment variables for the server.|
|secret_env_var_keys|array of string|No|Environment variable keys whose values are stored as secrets.|
|is_archived|boolean|Yes|Whether the tool server is archived.|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|v|integer|Schema version for migration support.|
|id|one of: string or null|Unique identifier for this record.|
|path|one of: string or null|File system path where the record is stored.|
|created_at|string|Timestamp when the model was created. Timezone-aware; stores the writer's local offset. Format: date-time|
|created_by|string|User ID of the creator.|
|name|string|The name of the external tool. 1-120 chars|
|type|string|Enumeration of supported external tool server types. One of: remote_mcp, local_mcp, kiln_task|
|description|one of: string or null|A description of the external tool for you and your team. Will not be used in prompts/training/validation.|
|properties|one of: LocalServerProperties, RemoteServerProperties, KilnTaskServerProperties|Configuration properties specific to the tool type.|
|model_type|string||

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

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
