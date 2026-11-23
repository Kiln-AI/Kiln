# List Projects

**GET /api/projects**

**Tags:** Projects

List the projects Kiln knows, with their IDs.

## Responses

### 200 OK

Successful Response

**Body:** array of Project-Output

## Schemas

### Project-Output

A collection of related tasks.

Projects organize tasks into logical groups and provide high-level descriptions
of the overall goals.

|Field|Type|Required|Description|
|-|-|-|-|
|v|integer|No|Schema version for migration support.|
|id|one of: string or null|No|Unique identifier for this record.|
|path|one of: string or null|No|File system path where the record is stored.|
|created_at|string|No|Timestamp when the model was created. Timezone-aware; stores the writer's local offset. Format: date-time|
|created_by|string|No|User ID of the creator.|
|name|string|Yes|The name of the project. 1-120 chars|
|description|one of: string or null|No|A description of the project for you and your team. Will not be used in prompts/training/validation.|
|model_type|string|Yes||
