# Test Code Tool

**POST /api/projects/{project_id}/test_code_tool**

**Tags:** Code Tools

Run a code tool's code once on test arguments without saving it, and
return its output or error. While the project's code is not trusted,
it runs nothing and returns `not_trusted: true`. Only the user can grant
code trust: explain what the code will run and that it runs with no
sandbox, give them the link
http://localhost:8757/settings/trust_code/{project_id}, and ask them to
tell you when they have approved. Then confirm with
GET /api/projects/{project_id}/add_code_trust and run the test.

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
|not_trusted|boolean|True when the project's code is not trusted, so nothing ran and nothing was saved. Only the user can grant code trust, in the Kiln app at http://localhost:8757/settings/trust_code/{project_id}. Explain what the code will run and that it runs with no sandbox, give the user that link, and ask them to tell you when they have approved. Then confirm with GET /api/projects/{project_id}/add_code_trust and call again.|
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

One nested tool call that a code tool or code eval made during a test run,
as reported to a test pane.

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
