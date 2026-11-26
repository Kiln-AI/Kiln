# List Model Info

**GET /api/model_info/models**

**Tags:** Providers & Models

List Kiln's models, with prices and limits, and whether each can run now.

Prices, limits and release dates come from models.dev; each provider entry has a
status saying whether the user can run it now. By default only entries the user
can run now (status ready, not deprecated) are listed. Rows with no listed entry
are left out. `total` counts the rows after all filters; page with `offset`.

## Request

### Query Parameters

|Name|Type|Required|Default|Description|
|-|-|-|-|-|
|search|one of: string or null|No||Name search on the model id and display name. Forgives case, spaces and punctuation; with no match, returns close names (fuzzy_match is true). Runs after the other filters.|
|featured|one of: boolean or null|No||true: only models Kiln ranks as featured. false: only models without a featured rank.|
|provider|one of: string or null|No||Kiln provider id, for example openrouter or gemini_api. Keeps only that provider's entries.|
|family|one of: string or null|No||Exact match on Kiln's model family.|
|tags|one of: array of string or null|No||A model passes when it has ANY of these tags, on the model or on a listed provider entry. Repeat the parameter for several tags.|
|supports_tools|one of: boolean or null|No||Filter provider entries on tool calls.|
|supports_vision|one of: boolean or null|No||Filter provider entries on image input.|
|has_thinking_levels|one of: boolean or null|No||Filter provider entries on thinking levels a run config can set.|
|reasoning_model|one of: boolean or null|No||Filter models that reason before they answer (models.dev). An unknown value does not pass.|
|open_weights|one of: boolean or null|No||Filter models on open weights (models.dev). An unknown value does not pass.|
|include_not_available|boolean|No|False|Also list provider entries the user cannot run now (status not_offered or not_connected). Use it to look up a model id.|
|include_deprecated|boolean|No|False|Also list deprecated provider entries.|
|include_notes|boolean|No|False|Fill editorial_notes and agent_notes in each row.|
|sort|one of: string or null|No||featured: Kiln's ranking. price: cheapest first, by median input + output price. newest: latest release first. Default: the featured order, or best match first with search.|
|limit|integer|No|25|Page size. 1-200|
|offset|integer|No|0|Rows to skip. >=0|

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
|total|integer|Rows after all filters, the same on every page.|
|fuzzy_match|boolean|True: no model held the search words, and the rows are the closest names.|
|models|array of ModelInfoRow||

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### ModelInfoProviderEntryRow

One provider entry of a model in a list row: status and prices.

|Field|Type|Required|Description|
|-|-|-|-|
|provider|string|Yes|Kiln provider id.|
|status|string|Yes|ready: the user can run the model on this provider now. not_offered: the provider is connected, but does not offer this model (for example an Ollama model that is not installed). not_connected: the provider is not connected in Kiln. One of: ready, not_offered, not_connected|
|input_price|one of: number or null|No|Input price, USD per million tokens. Null: no price data.|
|output_price|one of: number or null|No|Output price, USD per million tokens. Null: no price data.|
|tags|array of string|No|Kiln's tags for this provider entry.|
|deprecated|boolean|No|Kiln marks this provider entry deprecated.|

### ModelInfoRow

One model in a list of models, with its provider entries.

|Field|Type|Required|Description|
|-|-|-|-|
|model|string|Yes|Kiln's model id. Use it in a run config.|
|display_name|string|Yes|The model's name as Kiln shows it.|
|family|one of: string or null|No|Kiln's model family.|
|kiln_featured_rank|one of: integer or null|No|Kiln's ranking, 1 first. Null: not featured.|
|tags|array of string|No|Kiln's model tags, for example current, recommended, top_value.|
|release_date|one of: string or null|No|ISO date, from models.dev.|
|context_window|one of: integer or null|No|Tokens, from models.dev.|
|open_weights|one of: boolean or null|No|From models.dev.|
|reasoning_model|one of: boolean or null|No|The model reasons before it answers, also when that is always on (models.dev).|
|has_thinking_levels|boolean|No|At least one listed provider entry has thinking levels that a run config can set.|
|median_input_price|one of: number or null|No|USD per million tokens: the median price across the providers on models.dev.|
|median_output_price|one of: number or null|No|USD per million tokens: the median price across the providers on models.dev.|
|editorial_notes|one of: string or null|No|Kiln's notes for people. Null unless include_notes is true.|
|agent_notes|one of: string or null|No|Kiln's notes for an agent that chooses or configures the model. Null unless include_notes is true.|
|providers|array of ModelInfoProviderEntryRow|No|The provider entries that pass the filters.|

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
