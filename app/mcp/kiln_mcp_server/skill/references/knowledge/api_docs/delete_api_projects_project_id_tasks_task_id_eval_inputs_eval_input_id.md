# Delete Eval Input

**DELETE /api/projects/{project_id}/tasks/{task_id}/eval_inputs/{eval_input_id}**

**Tags:** Eval Inputs

Delete an eval input item, if nothing on disk still points at it.

409 when anything does. Both kinds of reference name the item by id and hold no
copy of it, so a delete that went through would leave records describing content
that no longer exists — an eval trace whose scenario is gone, or a score whose
input can't be read back. To take a referenced item out of an eval's scope,
retag it with PATCH instead; to correct its ground truth, PATCH its reference.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|task_id|string|Yes|The unique identifier of the task within the project.|
|eval_input_id|string|Yes|The unique identifier of the eval input.|

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
