# Delete Memory

**DELETE /api/projects/{project_id}/memories/{memory_id}**

**Tags:** Memory

Hard-delete a memory. For junk, wrong, or obsolete memories; use update
instead if the memory should be corrected rather than removed.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|memory_id|string|Yes|The unique identifier of the memory.|

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
