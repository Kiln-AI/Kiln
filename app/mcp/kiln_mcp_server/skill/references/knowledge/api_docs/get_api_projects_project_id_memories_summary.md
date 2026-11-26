# Memory Summary

**GET /api/projects/{project_id}/memories/summary**

**Tags:** Memory

Cheap per-scope orientation (counts, newest timestamp, tag cardinalities)
with no record content. Call before targeted list queries.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|

### Query Parameters

|Name|Type|Required|Default|Description|
|-|-|-|-|-|
|scope|one of: string or null|No||Limit to one scope. Omit for all scopes.|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|total|integer||
|scopes|array of ScopeSummary||

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### ScopeSummary

Counts for the memories of one scope: how many, the newest, and per-tag counts.

|Field|Type|Required|Description|
|-|-|-|-|
|scope|string|Yes||
|count|integer|Yes||
|newest|string|Yes|Format: date-time|
|tags|object|Yes||
|untagged|one of: integer or null|No|How many memories in this scope have no tags. Null when none.|

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
