# Test Code Tool

**POST /api/projects/{project_id}/test_code_tool**

**Tags:** Code Tools

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|

### Request Body

**Content Type:** `application/json`

|Field|Type|Required|Description|
|-|-|-|-|
|tool_function_name|string|Yes||
|tool_description|string|No||
|parameters_schema|object|Yes||
|code|string|Yes||
|timeout_seconds|integer|No||
|tool_allowlist|array of string|No||
|params|object|Yes|Invocation arguments for the test.|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|result|one of: string or null||
|error|one of: string or null||
|traceback|one of: string or null||
|not_trusted|boolean||
|stdout|string||
|stderr|string||
|tool_call_log|array of ToolCallLogEntryResponse||
|duration_ms|integer||

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### ToolCallLogEntryResponse

One nested tool call a sandboxed run made, as reported to a test pane.

|Field|Type|Required|Description|
|-|-|-|-|
|tool_name|string|Yes||
|arguments|object|Yes||
|output_preview|string|Yes||
|is_error|boolean|Yes||
|duration_ms|integer|Yes||

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
