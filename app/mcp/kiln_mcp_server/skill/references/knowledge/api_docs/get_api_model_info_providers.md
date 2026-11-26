# List Model Info Providers

**GET /api/model_info/providers**

**Tags:** Providers & Models

List the model providers Kiln knows, and whether each one is connected.

Each is marked connected or not_connected, with the number of models ready to
run on it, and Kiln's notes on data retention, rate limits and gotchas.
Connected providers with models come first.

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|sources.kiln_model_list.origin|string|remote_config: Kiln's remote model list was loaded in this process. built_in: the list shipped with the installed app. One of: remote_config, built_in|
|sources.kiln_model_list.loaded_at|one of: string or null|UTC time of the last good remote model list load. Null for built_in.|
|sources.kiln_model_list.age_seconds|one of: integer or null|Seconds since loaded_at. Null for built_in.|
|sources.models_dev.state|string|ok: models.dev data younger than 6 hours. stale: older data is served, because a refresh failed or did not finish in time. unavailable: no models.dev data; every price, limit and date is null. One of: ok, stale, unavailable|
|sources.models_dev.loaded_at|one of: string or null|UTC time the models.dev data was fetched, or last confirmed unchanged.|
|sources.models_dev.age_seconds|one of: integer or null|Seconds since loaded_at.|
|sources.models_dev.detail|one of: string or null|Null when ok. Else why the data is missing or old: turned off, loading, not loaded, refresh running, or the last failure reason.|
|providers|array of ModelInfoProviderRow||

## Schemas

### ModelInfoProviderRow

One model provider: whether it is connected, and how many models are ready on it.

|Field|Type|Required|Description|
|-|-|-|-|
|provider|string|Yes|Kiln provider id.|
|name|one of: string or null|No|The provider's name in Kiln.|
|status|string|Yes|connected: the provider is set up in Kiln. One of: connected, not_connected|
|ready_model_count|integer|No|Models the user can run on this provider now, deprecated and untested ones included.|
|tags|array of string|No|Kiln's provider tags.|
|notes|one of: string or null|No|Kiln's provider notes: data retention, rate limits, gotchas.|
