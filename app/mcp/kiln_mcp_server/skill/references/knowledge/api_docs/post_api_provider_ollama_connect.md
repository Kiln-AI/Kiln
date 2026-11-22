# Connect Ollama

**POST /api/provider/ollama/connect**

**Tags:** Providers & Models

## Request

### Query Parameters

|Name|Type|Required|Default|Description|
|-|-|-|-|-|
|custom_ollama_url|one of: string or null|No||Custom URL for the Ollama server.|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|message|string||
|version|one of: string or null||
|supported_models|array of string||
|untested_models|array of string||
|supported_embedding_models|array of string||

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
