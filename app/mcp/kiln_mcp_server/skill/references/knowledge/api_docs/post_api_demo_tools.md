# Set Demo Tools

**POST /api/demo_tools**

**Tags:** Tools & MCP

Turn Kiln's demo math tools on or off.

## Request

### Query Parameters

|Name|Type|Required|Default|Description|
|-|-|-|-|-|
|enable_demo_tools|boolean|Yes||Whether to enable demo tools.|

## Responses

### 200 OK

Successful Response

**Body:** boolean

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
