# Check code trust for a project

**GET /api/projects/{project_id}/add_code_trust**

**Tags:** Evals

Check whether the project's code is trusted for this app session.
Only the user can grant trust, in the Kiln app at
http://localhost:8757/settings/trust_code/{project_id}.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|trusted|boolean||

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
