# Connect Docker Model Runner

**POST /api/provider/docker_model_runner/connect**

**Tags:** Providers & Models

Connect to a running Docker Model Runner and list its models. Uses the
default address unless a custom URL is set.

## Request

### Query Parameters

|Name|Type|Required|Default|Description|
|-|-|-|-|-|
|docker_model_runner_custom_url|one of: string or null|No||Custom URL for the Docker Model Runner.|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|message|string||
|version|one of: string or null||
|supported_models|array of string||
|untested_models|array of string||

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
