# List Available Reranker Models

**GET /api/available_reranker_models**

**Tags:** Providers & Models

## Responses

### 200 OK

Successful Response

**Body:** array of RerankerProvider

## Schemas

### RerankerModelDetails

|Field|Type|Required|Description|
|-|-|-|-|
|id|string|Yes||
|name|string|Yes||
|deprecated|boolean|No||

### RerankerProvider

|Field|Type|Required|Description|
|-|-|-|-|
|provider_name|string|Yes||
|provider_id|string|Yes||
|models|array of RerankerModelDetails|Yes||
