# Import Project

**POST /api/import_project**

**Tags:** Projects

Add an existing project to Kiln from the path of its project.kiln file.

## Request

### Query Parameters

|Name|Type|Required|Default|Description|
|-|-|-|-|-|
|project_path|string|Yes||File path to the project.kiln file to import.|
|remove_conflicting_id|boolean|No|False|When true and a duplicate project ID conflict is detected, remove the existing project registration before importing.|
|trusted|boolean|No|False|Must be true to import. Set it only after the user confirms they trust the project: Kiln projects can contain code that runs on your machine. It is the importer's confirmation; it grants no code trust.|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|v|integer|Schema version for migration support.|
|id|one of: string or null|Unique identifier for this record.|
|path|one of: string or null|File system path where the record is stored.|
|created_at|string|Timestamp when the model was created. Timezone-aware; stores the writer's local offset. Format: date-time|
|created_by|string|User ID of the creator.|
|name|string|The name of the project. 1-120 chars|
|description|one of: string or null|A description of the project for you and your team. Will not be used in prompts/training/validation.|
|model_type|string||

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
