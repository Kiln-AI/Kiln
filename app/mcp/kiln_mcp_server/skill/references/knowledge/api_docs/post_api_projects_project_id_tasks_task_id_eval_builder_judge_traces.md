# Judge Saved Eval-Builder Results

**POST /api/projects/{project_id}/tasks/{task_id}/eval_builder/judge_traces**

**Tags:** Eval Builder

Re-judge saved eval builder results with a new judge prompt, as an event stream.

[reload → judge] per case.

The judge calibration loop's re-score stream, both arms: after a
refine produces a new judge prompt, this scores the SAME saved
results again. Each run is reloaded from disk by id; multi-turn
judges the chain leaf's stored trace, single-turn the run's own —
either way the judge input matches what the saved eval will judge.
Nothing is driven and nothing is written.

Emits (all frames `type`-discriminated; errors carry {code, message}):
  - batch_started   { batch_tag: "", total_cases }
  - case_judged     { case_index, leaf_run_id, raw_input, raw_output,
                      judge_score, judge_reasoning, total_cost: 0,
                      trace }
  - case_failed     { case_index, stage: "judge", code, message,
                      error_type }
                      (batch continues; a run that cannot be
                      reloaded fails with code trace_not_found,
                      missing_trace, or missing_output)
  - batch_completed { judged, failed, batch_tag: "", total_cost: 0 }
  - batch_aborted   { error, stage: "judge" }  (in place of
                      batch_completed: a config-scoped judge failure
                      aborted the whole batch; results already
                      streamed remain valid)
  - batch_failed    { code, message }  (in place of batch_completed:
                      an orchestration-level crash ended the stream;
                      results already streamed remain valid)
Terminated by `data: complete`. case_index is the position in
leaf_run_ids; no drive or turn frames appear on this stream. Claims
are built afterwards, per opened trace, via build_claims.

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
|leaf_run_ids|array of string|Yes|TaskRun ids of the driven results to judge: chain-leaf ids on a multi-turn task, the pipeline's run ids on a single-turn one. Frames reference each case by its position in this list (case_index).|
|judge.prompt|string|Yes||
|judge.model_name|string|Yes||
|judge.model_provider|string|Yes|Enumeration of supported AI model providers. One of: openai, groq, amazon_bedrock, ollama, openrouter, fireworks_ai, kiln_fine_tune, kiln_custom_registry, openai_compatible, anthropic, gemini_api, azure_openai, huggingface, vertex, together_ai, siliconflow_cn, cerebras, docker_model_runner, featherless_ai, cloudflare, typesafe|

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
