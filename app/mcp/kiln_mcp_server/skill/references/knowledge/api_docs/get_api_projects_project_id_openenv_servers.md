# List OpenEnv Servers

**GET /api/projects/{project_id}/openenv_servers**

**Tags:** OpenEnv Servers

List the project's OpenEnv servers.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|

## Responses

### 200 OK

Successful Response

**Body:** array of OpenEnvServerResponse

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### OpenEnvServerResponse

An OpenEnv server: Kiln's saved pointer to a running OpenEnv environment.

|Field|Type|Required|Description|
|-|-|-|-|
|id|one of: string or null|No|The OpenEnv server's id.|
|name|string|Yes|User-facing display name.|
|description|one of: string or null|No|User-facing notes about the OpenEnv server.|
|url|one of: string or null|No|Base URL of an OpenEnv server that is already running (e.g. http://127.0.0.1:8000). Kiln connects to it; it never starts one. Evals run in this OpenEnv server send their tool calls to it.|
|created_at|one of: string or null|No|When the OpenEnv server was created.|
|created_by|one of: string or null|No|Who created the OpenEnv server.|

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
