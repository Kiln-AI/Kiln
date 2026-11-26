# Resolve an Available Spec Name

**GET /api/projects/{project_id}/tasks/{task_id}/available_spec_name**

**Tags:** Specs

Suggest a free spec name: the candidate itself, or the nearest suffixed one.

The candidate is checked against the task's existing specs.

The check uses the derived-tag comparison the spec-save guard
enforces (case/spacing-insensitive), so a name this endpoint returns
will not 409 at save. Callers prefill suggested names through this
(the suggester is deterministic over similar inputs, so second evals
on a task collide otherwise) and validate typed names early, where a
collision costs nothing instead of surfacing after generation and
review.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|task_id|string|Yes|The unique identifier of the task within the project.|

### Query Parameters

|Name|Type|Required|Default|Description|
|-|-|-|-|-|
|name|string|Yes||The candidate spec name to check. 1-32 chars|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|name|string|The candidate itself when free, else the nearest available suffixed variant.|
|was_taken|boolean|Whether the candidate collided with an existing spec (and `name` is therefore a suffixed variant).|

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
