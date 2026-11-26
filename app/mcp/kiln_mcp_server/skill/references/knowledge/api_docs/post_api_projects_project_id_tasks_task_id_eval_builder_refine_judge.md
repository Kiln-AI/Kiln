# Refine Judge

**POST /api/projects/{project_id}/tasks/{task_id}/eval_builder/refine_judge**

**Tags:** Eval Builder

Propose a judge-prompt revision from the human's per-claim grades.

The refined prompt is a PROPOSAL — the UI validates it and shows the
changes for approval; it is never auto-applied.

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
|judge_prompt|string|Yes|>=1 chars|
|graded_traces|array of GradedTraceApi|Yes||

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|refined_judge_prompt|string||
|changes|array of RefineJudgeChangeApi||
|not_incorporated_feedback|one of: string or null||

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### GradedClaim

One claim with a human grade on it.

A claim is one decision the judge made, written so the reviewer can vote
on it from the card alone. Grades have one direction on every claim:
agree means the judge got that decision right, disagree means it got it
wrong. The claim text carries its own evidence and citation markers.

|Field|Type|Required|Description|
|-|-|-|-|
|text|string|Yes|The claim as shown to the reviewer.|
|human_grade|string|Yes|The human's grade on this claim. One of: agree, disagree|
|human_feedback|one of: string or null|No|Optional plaintext reason for the grade.|

### GradedTraceApi

One human-reviewed trace's grades, shaped to feed judge refinement.

Mirrors the persisted ClaimReview (judge verdict, the overview, every
claim with its agree/disagree and optional why, and the reviewer's
overall call) plus a `trace_label` the refine model cites in its change
rationales.

|Field|Type|Required|Description|
|-|-|-|-|
|trace_label|string|Yes|A label for the trace the refine model cites in its rationales; derived UI-side from the run id (often opaque).|
|judge_score|string|Yes|One of: pass, fail|
|judge_reasoning|string|Yes||
|overview|string|Yes||
|claims|array of GradedClaim|Yes||
|human_verdict|string|Yes|One of: pass, fail|

### RefineJudgeChangeApi

One edit the refine model made to the judge prompt, with its rationale.

|Field|Type|Required|Description|
|-|-|-|-|
|change|string|Yes||
|rationale|string|Yes||

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
