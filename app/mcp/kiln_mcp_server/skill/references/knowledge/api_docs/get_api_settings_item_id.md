# Get Setting Item

**GET /api/settings/{item_id}**

**Tags:** Settings & Utilities

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|item_id|string|Yes|The setting item key to retrieve.|

## Responses

### 200 OK

Successful Response

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
