# List Available Providers

**GET /api/settings/available_providers**

**Tags:** Providers & Models

Returns all providers that can have custom models added.

## Responses

### 200 OK

Successful Response

**Body:** array of AvailableProviderInfo

## Schemas

### AvailableProviderInfo

Information about an available AI provider.

|Field|Type|Required|Description|
|-|-|-|-|
|id|string|Yes|The unique provider identifier used in API calls.|
|name|string|Yes|The human-readable display name of the provider.|
|provider_type|string|Yes|Whether the provider is built-in or user-configured. One of: builtin, custom|
