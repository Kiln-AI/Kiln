# Delete OpenEnv Server

**DELETE /api/projects/{project_id}/openenv_servers/{openenv_server_id}**

**Tags:** OpenEnv Servers

Delete an OpenEnv server, if no saved eval input still resets into it.

409 when one does. An eval input names its OpenEnv server by id, so a delete
that went through would leave every eval run on it failing to resolve the
OpenEnv server. Traces made on the server keep their own copy of the episode,
and stay readable.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|openenv_server_id|string|Yes|The unique identifier of the OpenEnv server.|

## Responses

### 200 OK

Successful Response

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
