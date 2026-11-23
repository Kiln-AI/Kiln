# Get Model Info Details

**GET /api/model_info/model_details**

**Tags:** Providers & Models

Get the full record of one model by its Kiln model ID, for every provider.

Every provider entry has its status, prices, limits, capabilities, thinking
levels, default output mode and what Kiln suggests the model for. Read the entry
of the provider you will use before you write a run config. 404 when the model,
or its entry for `provider`, does not exist.

## Request

### Query Parameters

|Name|Type|Required|Default|Description|
|-|-|-|-|-|
|model_id|string|Yes||Kiln model id, as GET /api/model_info/models lists it. A query parameter, because ids of custom and fine-tuned models hold '/' and '::'. 1-200 chars|
|provider|one of: string or null|No||Kiln provider id, for example openrouter or gemini_api. Keeps only that provider's entry.|

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
|model|string|Kiln's model id. Use it in a run config.|
|display_name|string|The model's name as Kiln shows it.|
|family|one of: string or null|Kiln's model family.|
|kiln_featured_rank|one of: integer or null|Kiln's ranking, 1 first. Null: not featured.|
|tags|array of string|Kiln's model tags.|
|release_date|one of: string or null|ISO date, from models.dev.|
|release_date_estimated|boolean|True: the date came from a match on the model's name only.|
|knowledge_cutoff|one of: string or null|As models.dev writes it.|
|context_window|one of: integer or null|Tokens, from models.dev.|
|max_output_tokens|one of: integer or null|Tokens, from models.dev.|
|open_weights|one of: boolean or null|From models.dev.|
|reasoning_model|one of: boolean or null|The model reasons before it answers, also when that is always on (models.dev).|
|has_thinking_levels|boolean|At least one listed provider entry has thinking levels that a run config can set.|
|median_input_price|one of: number or null|USD per million tokens: the median price across the providers on models.dev.|
|median_output_price|one of: number or null|USD per million tokens: the median price across the providers on models.dev.|
|editorial_notes|one of: string or null|Kiln's notes for people.|
|agent_notes|one of: string or null|Kiln's notes for an agent that chooses or configures the model.|
|providers|array of ModelInfoProviderEntryDetails|Every provider entry, also deprecated and not available ones.|

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### ModelInfoProviderEntryDetails

The full record of one provider entry of a model.

|Field|Type|Required|Description|
|-|-|-|-|
|provider|string|Yes|Kiln provider id.|
|status|string|Yes|ready: the user can run the model on this provider now. not_offered: the provider is connected, but does not offer this model (for example an Ollama model that is not installed). not_connected: the provider is not connected in Kiln. One of: ready, not_offered, not_connected|
|provider_model_id|one of: string or null|No|The provider's own id for the model. Null for a model Kiln only knows from the user's setup.|
|deprecated|boolean|No|Kiln marks this provider entry deprecated.|
|untested|boolean|No|Kiln has not tested this model, usually one a user added. The supports_* fields do not apply.|
|input_price|one of: number or null|No|Input price, USD per million tokens. Null: no price data.|
|output_price|one of: number or null|No|Output price, USD per million tokens. Null: no price data.|
|cache_read_price|one of: number or null|No|Cache read price, USD per million tokens. Null: no price data.|
|cache_write_price|one of: number or null|No|Cache write price, USD per million tokens. Null: no price data.|
|context_window|one of: integer or null|No|This provider's context window in tokens, from models.dev.|
|max_output_tokens|one of: integer or null|No|This provider's output limit in tokens, from models.dev.|
|tags|array of string|No|Kiln's tags for this provider entry.|
|supports_tools|one of: boolean or null|No|Kiln's flag: tool calls work on this pair.|
|supports_structured_output|one of: boolean or null|No|Kiln's flag: structured output works on this pair.|
|supports_vision|one of: boolean or null|No|Kiln's flag: image input works on this pair.|
|supports_temperature|one of: boolean or null|No|From models.dev.|
|thinking_levels|array of string|No|The thinking levels a run config can set, in Kiln's order.|
|default_thinking_level|one of: string or null|No|Kiln's suggested default thinking level for the pair. Null when Kiln suggests none.|
|default_structured_output_mode|one of: string or null|No|Kiln's suggested default output mode for the pair.|
|kiln_suggested_for|array of string|No|Uses that Kiln suggests the model for: eval_judge, synthetic_data, document_extraction, synthetic_user.|

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
