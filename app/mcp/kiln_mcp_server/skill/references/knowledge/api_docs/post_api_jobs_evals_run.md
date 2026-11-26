# Run Eval Job

**POST /api/jobs/evals/run**

**Tags:** Jobs

Start a background job that runs one split of an eval against one run
config, and return at once. Items that already have a score for this eval
config and run config are skipped. If an identical job (same eval, judge,
run config, split and items) is still pending, running or paused, returns
that job instead of starting a second one that would score the same items
again. A paused job is returned as it is, with `status` `paused`: the
request does not resume it. A wait on a paused job times out (504) until
someone resumes it, so check `status` and call
`POST /api/jobs/{id}/resume` if the job must run. Poll
`GET /api/jobs/{id}` or `POST /api/jobs/wait` for progress and the
result. An item with an `openenv_reset` runs in a fresh episode of its environment
when the run config lists that environment's tools. A 404 means that the eval,
the eval config or the run config does not exist. A 422 means that the
eval has no such split, or that `item_ids` names an item outside it. A 400
means that the job cannot run as requested: a V1 judge on items it cannot
score, multi-turn items that cannot be driven, or, with a V2 judge, items
that the run config's environment tools cannot run, or an environment that the project
does not have while the run config lists tools. Problems that need
the running server fail item by item, in `GET /api/jobs/{id}/errors`:
an environment that cannot be reached or refuses a reset, and a run config
that lists the project's own version of a tool that the environment serves. A
503 means that a project file was not readable, for example while another
job wrote it. Send the request again.

With `judge` false the job drives every selected item again and judges
nothing: read `result.driven_runs` for the task runs, and each task run's
`usage` for the agent's cost and latency. For a multi-turn item, add the task
run's `synthetic_user_usage` for the drive's full model cost. Such a job is never
deduplicated and cannot be paused, and a 400 also means that its eval config
is not a V2 judge.

## Request

### Request Body

**Content Type:** `application/json`

|Field|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|Id of the project the eval belongs to.|
|task_id|string|Yes|Id of the task the eval belongs to.|
|eval_id|string|Yes|Id of the eval to run.|
|eval_config_id|string|Yes|Id of the eval config (judge) to evaluate the run's output with.|
|run_config_id|string|Yes|Id of the task run config whose outputs are being evaluated.|
|concurrency|one of: integer or null|No|Max dataset items evaluated in parallel by the runner, from 1 to 100. Leave null to use the runner's default (25).|
|split|string|Yes|Which of the eval's dataset splits to run: train, val, or test. Required, so a caller never runs the test split by omission. Fails with 422 if the eval has no such split. One of: train, val, test|
|item_ids|one of: array of string or null|No|Restrict the job to these items of the split (EvalInput ids for an EvalInput-backed split, TaskRun ids for a TaskRun-backed one). Fails with 422 if an id is not in the split when the job is created. Progress and completion are measured over the subset. Leave null to run the whole split. Lets a caller trial a run config on a few named items before paying for the full split: the rows it stores are reused by a later full run, which skips scored items.|
|judge|boolean|No|Whether to judge the items. False drives each item exactly as a judged job does (a fresh episode for an item with an openenv_reset, the synthetic user for a multi-turn item) and saves its trace as a task run with its usage, but runs no judge and stores no score. Every item is driven again, scored or not, so the usage is of this job. `result.driven_runs` names the task runs. A later judged job on the same items and run config reuses these traces instead of driving again. For an item in an environment, only while the item's openenv_reset and the environment's version are unchanged: a trace is reused only for the reset and version it ran with. Needs a V2 eval config. A drive-only job is never deduplicated and cannot be paused: each one is a new measurement.|

## Responses

### 201 Created

Successful Response

|Field|Type|Description|
|-|-|-|
|job_id|string|The id of the job: a new job, or an existing identical job.|
|status|string|One of: pending, running, paused, succeeded, failed, cancelled|

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
