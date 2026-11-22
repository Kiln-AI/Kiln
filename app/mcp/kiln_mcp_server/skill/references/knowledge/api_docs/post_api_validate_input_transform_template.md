# Validate Input Transform Template

**POST /api/validate_input_transform_template**

**Tags:** Run Configs

## Request

### Request Body

**Content Type:** `application/json`

|Field|Type|Required|Description|
|-|-|-|-|
|template|string|Yes|The Jinja2 template source to validate.|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|valid|boolean|Whether the template is valid Jinja2.|
|error|one of: string or null|The compile error message, if invalid.|

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
