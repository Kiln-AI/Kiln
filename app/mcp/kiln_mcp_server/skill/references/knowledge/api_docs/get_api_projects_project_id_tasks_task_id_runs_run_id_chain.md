# Get Run Chain

**GET /api/projects/{project_id}/tasks/{task_id}/runs/{run_id}/chain**

**Tags:** Runs

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|task_id|string|Yes|The unique identifier of the task within the project.|
|run_id|string|Yes|The unique identifier of the task run whose chain to return.|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|chain|array of RunChainEntry|Ordered root-to-leaf, includes the requested run itself as the final entry. If chain_broken is true, the list contains only the intact suffix from the leaf back to (and excluding) the break point.|
|chain_broken|boolean|True if while walking parents we encountered a parent_task_run_id that could not be loaded, a cycle, the depth guard, or a run whose trace does not extend its parent's (so it can't be positioned in the leaf's trace).|
|has_children|boolean|True if at least one other TaskRun in the task references the requested run via parent_task_run_id (i.e. the requested run is an intermediate node in the chain, not a leaf). Used by the UI to warn that sending a new message from this run will create a new branch rather than extending an existing one.|

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### RunChainEntry

A single entry in a multi-turn run's conversation chain.

|Field|Type|Required|Description|
|-|-|-|-|
|run_id|one of: string or null|Yes|The TaskRun id at this turn position in the chain.|
|turn_index|integer|Yes|1-based turn index within the returned chain (turn 1 = first entry, turn N = leaf). For an unbroken chain this is the absolute turn number in the conversation; for a broken chain it is relative to the returned suffix, since absolute positions are unknowable when ancestors are missing.|
|trace_start_index|one of: integer or null|Yes|Index into the leaf run's trace where this turn's messages begin. A run's trace is its parent's trace plus its own turn, so this is the parent run's trace length (0 for the conversation root). None when the boundary is unknowable (first entry of a broken chain).|

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
