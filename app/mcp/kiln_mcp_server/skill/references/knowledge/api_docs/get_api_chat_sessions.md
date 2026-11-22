# List chat sessions

**GET /api/chat/sessions**

**Tags:** Copilot

Proxy to Kiln Copilot ``GET /v1/chat/sessions``.

## Request

### Query Parameters

|Name|Type|Required|Default|Description|
|-|-|-|-|-|
|limit|integer|No|50|Maximum number of sessions to return|
|offset|integer|No|0|Number of sessions to skip|

## Responses

### 200 OK

Successful Response

**Body:** array of ChatSessionListItem

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### ChatSessionListItem

|Field|Type|Required|Description|
|-|-|-|-|
|id|string|Yes||
|title|one of: string or null|No||
|updated_at|one of: string or null|No||

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
