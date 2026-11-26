# Delete User Model

**DELETE /api/settings/user_models**

**Tags:** Providers & Models

Delete a user-defined model from the registry.

Supports two deletion methods:
1. By ID (new): Pass `id` parameter to delete from user_model_registry
2. By tuple (legacy): Pass provider_type, provider_id, model_id to delete from
   user_model_registry by matching those fields, or from legacy custom_models

Legacy models in custom_models don't have IDs and must use the tuple method.

## Request

### Query Parameters

|Name|Type|Required|Default|Description|
|-|-|-|-|-|
|provider_type|one of: string or null|No||Provider type: 'builtin' for built-in providers, 'custom' for OpenAI-compatible.|
|provider_id|one of: string or null|No||The provider identifier (e.g., 'openai', 'anthropic', or custom provider name).|
|model_id|one of: string or null|No||The model identifier to delete.|
|id|one of: string or null|No||Unique ID of the model entry in user_model_registry (preferred deletion method).|

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
