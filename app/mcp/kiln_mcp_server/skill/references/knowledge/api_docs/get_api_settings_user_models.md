# List User Models

**GET /api/settings/user_models**

**Tags:** Providers & Models

Returns all user-defined models (new registry + legacy combined).

Includes both user_model_registry entries and legacy custom_models
(converted to UserModelEntry for display). Legacy models can be
deleted via the tuple method (provider_type/provider_id/model_id).

## Responses

### 200 OK

Successful Response

**Body:** array of UserModelEntry

## Schemas

### UserModelEntry

A user-defined custom model entry.

Attributes:
    id: Unique identifier for this entry (auto-generated if not provided)
    provider_type: "builtin" for ModelProviderName enum providers, "custom" for openai_compatible
    provider_id: For builtin: enum value like "openai". For custom: the custom provider name
    model_id: The model ID to use with the provider's API
    name: Display name (optional, defaults to model_id)
    overrides: Property overrides from KilnModelProvider (optional)

Note on overrides:
    The overrides field accepts any keys for forward compatibility. When a UserModelEntry
    is converted to a KilnModelProvider via user_model_to_provider(), only valid
    KilnModelProvider fields are applied. Unknown fields are silently ignored.
    This allows new fields to be added to KilnModelProvider without breaking existing
    UserModelEntry data.

|Field|Type|Required|Description|
|-|-|-|-|
|provider_type|string|Yes|One of: builtin, custom|
|provider_id|string|Yes||
|model_id|string|Yes||
|name|one of: string or null|No||
|overrides|one of: object or null|No||
|id|string|No||
