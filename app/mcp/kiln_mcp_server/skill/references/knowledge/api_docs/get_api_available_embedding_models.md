# List Available Embedding Models

**GET /api/available_embedding_models**

**Tags:** Providers & Models

List the embedding models the user can run now, grouped by connected
provider.

## Responses

### 200 OK

Successful Response

**Body:** array of EmbeddingProvider

## Schemas

### EmbeddingModelDetails

|Field|Type|Required|Description|
|-|-|-|-|
|id|string|Yes||
|name|string|Yes||
|n_dimensions|integer|Yes||
|max_input_tokens|one of: integer or null|Yes||
|supports_custom_dimensions|boolean|Yes||
|suggested_for_chunk_embedding|boolean|Yes||
|deprecated|boolean|No||

### EmbeddingProvider

|Field|Type|Required|Description|
|-|-|-|-|
|provider_name|string|Yes||
|provider_id|string|Yes||
|models|array of EmbeddingModelDetails|Yes||
