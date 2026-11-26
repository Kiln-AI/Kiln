# Parse Import File

**POST /api/projects/{project_id}/tasks/{task_id}/copilot/parse_import_file**

**Tags:** Copilot

Parse an uploaded bulk-import file of input examples for the data
guide, server-side.

Both task types use a single-column CSV (parsed with the stdlib csv
reader). Plaintext tasks take each cell as the raw input; structured
tasks take each cell as a JSON object, validated against the task's input
schema. Returns the parsed example strings plus any whole-file `error` or
partial-skip `warning` so the web UI just renders the result.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|task_id|string|Yes|The unique identifier of the task within the project.|

### Request Body

**Content Type:** `application/json`

|Field|Type|Required|Description|
|-|-|-|-|
|file|string|Yes|The file of input examples to parse and validate.|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|rows|array of string|Parsed example input strings, ready to add. Empty when error is set.|
|error|one of: string or null|Set when the whole file was rejected (invalid format/encoding).|
|warning|one of: string or null|Set when the file was accepted but some examples were skipped.|

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
