# Add User Model

**POST /api/settings/user_models**

**Tags:** Providers & Models

Add a user-defined model to the registry.

## Request

### Request Body

**Content Type:** `application/json`

|Field|Type|Required|Description|
|-|-|-|-|
|provider_type|string|Yes|One of: builtin, custom|
|provider_id|string|Yes||
|model_id|string|Yes||
|name|one of: string or null|No||
|overrides|one of: object or null|No||
|id|string|No||

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
