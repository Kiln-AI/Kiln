# Build Claims

**POST /api/projects/{project_id}/tasks/{task_id}/eval_builder/build_claims**

**Tags:** Eval Builder

Claims-only primitive: build claims for one trace given a known verdict.

The multi-turn review's claims path: the pipeline stream stops at the
judge, and the client calls this per trace the reviewer opens (under
subset review most traces are never opened). Also used by the refine
loop to regenerate claims without re-running the judge.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|task_id|string|Yes|The unique identifier of the task.|

### Request Body

**Content Type:** `application/json`

|Field|Type|Required|Description|
|-|-|-|-|
|raw_input|string|Yes||
|raw_output|string|Yes||
|eval_rubric|string|Yes||
|judge_reasoning|string|Yes||
|judge_score|string|Yes|One of: pass, fail|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|overview.text|string||
|overview.citations|array of CitationApi||
|claims|array of ClaimApi||

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### CitationApi

A start+end anchor into the trace; the UI highlights from `from` to `to`.

`from` is a Python keyword, so the field is `from_` with an alias — the
serialized key MUST stay `from` (the UI greps that literal JSON key).

|Field|Type|Required|Description|
|-|-|-|-|
|marker|integer|Yes||
|source|string|Yes|One of: input, output|
|from|string|Yes||
|to|string|Yes||

### ClaimApi

One decision the judge made, written so the reviewer can vote on it.

`text` carries the claim, its evidence and its [n] markers in one string;
every marker resolves through `citations`. Grades have one direction:
agree means the judge got this decision right, disagree means it got it
wrong.

`is_verdict` marks the claim that states the overall pass/fail. The claim
builder may omit it, and only the LAST claim can be one, so the UI needs a
flag rather than a guess: it decides whether to derive the reviewer's
overall call from that claim's grade or to ask for it outright. The studio
sets the flag from the builder's own convention (the verdict claim opens
"It passes" or "It fails", and no other claim may) so the UI never
pattern-matches prose.

|Field|Type|Required|Description|
|-|-|-|-|
|text|string|Yes||
|citations|array of CitationApi|Yes||
|is_verdict|boolean|Yes||

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
