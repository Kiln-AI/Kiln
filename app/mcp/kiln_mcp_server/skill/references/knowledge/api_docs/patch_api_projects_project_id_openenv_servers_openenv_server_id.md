# Update OpenEnv Server

**PATCH /api/projects/{project_id}/openenv_servers/{openenv_server_id}**

**Tags:** OpenEnv Servers

Change an OpenEnv server's name, description or URL.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|openenv_server_id|string|Yes|The unique identifier of the OpenEnv server.|

### Request Body

**Content Type:** `application/json`

|Field|Type|Required|Description|
|-|-|-|-|
|name|one of: string or null|No|User-facing display name.|
|description|one of: string or null|No|User-facing notes about the OpenEnv server.|
|url|one of: string or null|No|Base URL of an OpenEnv server that is already running (e.g. http://127.0.0.1:8000). Kiln connects to it; it never starts one. Evals run in this OpenEnv server send their tool calls to it.|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|id|one of: string or null|The OpenEnv server's id.|
|name|string|User-facing display name.|
|description|one of: string or null|User-facing notes about the OpenEnv server.|
|url|one of: string or null|Base URL of an OpenEnv server that is already running (e.g. http://127.0.0.1:8000). Kiln connects to it; it never starts one. Evals run in this OpenEnv server send their tool calls to it.|
|created_at|one of: string or null|When the OpenEnv server was created.|
|created_by|one of: string or null|Who created the OpenEnv server.|

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
