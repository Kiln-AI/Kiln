# Get Search Tools

**GET /api/projects/{project_id}/search_tools**

**Tags:** Tools & MCP

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|

## Responses

### 200 OK

Successful Response

**Body:** array of SearchToolApiDescription

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### SearchToolApiDescription

|Field|Type|Required|Description|
|-|-|-|-|
|id|one of: string or null|Yes||
|tool_name|string|Yes||
|name|string|Yes||
|description|one of: string or null|Yes||

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
