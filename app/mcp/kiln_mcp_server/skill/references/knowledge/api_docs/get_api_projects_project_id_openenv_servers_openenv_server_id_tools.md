# List OpenEnv Server Tools

**GET /api/projects/{project_id}/openenv_servers/{openenv_server_id}/tools**

**Tags:** OpenEnv Servers

The tools the OpenEnv server's environment serves, read fresh from the running server at url.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|openenv_server_id|string|Yes|The unique identifier of the OpenEnv server.|

## Responses

### 200 OK

Successful Response

**Body:** array of OpenEnvToolResponse

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### OpenEnvToolResponse

One tool the OpenEnv server's environment serves.

|Field|Type|Required|Description|
|-|-|-|-|
|tool_id|string|Yes|The id a run config uses to list this tool directly: kiln_tool::openenv::<openenv_server_id>::<tool_name>.|
|name|string|Yes|The tool's function name, as the model sees it.|
|description|string|No|The tool's description, as the model sees it.|
|input_schema|object|No|JSON schema of the tool's arguments.|

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
