# Check Entitlements

**GET /api/check_entitlements**

**Tags:** Settings & Utilities

Check whether the authenticated user has the given entitlements.

The feature_codes parameter should be a comma-separated list of entitlement feature codes to check.
Returns a dict mapping each feature code to a boolean indicating if the user has that entitlement.

## Request

### Query Parameters

|Name|Type|Required|Default|Description|
|-|-|-|-|-|
|feature_codes|string|Yes||Comma-separated list of entitlement feature codes to check.|

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
