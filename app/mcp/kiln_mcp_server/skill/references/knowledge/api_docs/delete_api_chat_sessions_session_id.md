# Delete chat session

**DELETE /api/chat/sessions/{session_id}**

**Tags:** Copilot

Proxy to Kiln Copilot ``DELETE /v1/chat/sessions/{session_id}``.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|session_id|string|Yes|Chat session id to delete.|

## Responses

### 204 No Content

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
