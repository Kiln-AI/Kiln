# Get chat session

**GET /api/chat/sessions/{session_id}**

**Tags:** Copilot

Proxy to Kiln Copilot ``GET /v1/chat/sessions/{session_id}``.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|session_id|string|Yes|Chat session id (same as trace id for continuation).|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|id|string||
|task_run.trace|one of: array of TraceMessage or null||

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### TraceToolCall

|Field|Type|Required|Description|
|-|-|-|-|
|id|string|Yes||
|type|string|No||
|function.name|string|Yes||
|function.arguments|string|Yes||

### TraceMessage

|Field|Type|Required|Description|
|-|-|-|-|
|role|string|Yes||
|content|one of: string, array of object or null|No||
|tool_calls|one of: array of TraceToolCall or null|No||
|tool_call_id|one of: string or null|No||
|reasoning_content|one of: string or null|No||
|is_error|one of: boolean or null|No||
|error_message|one of: string or null|No||

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
