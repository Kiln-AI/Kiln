# Get Job

**GET /api/jobs/{id}**

**Tags:** Jobs

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|id|string|Yes|The job id.|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|id|string|Unique identifier for this job.|
|type|string|Registered job type name, determining which worker runs it.|
|status|string|One of: pending, running, paused, succeeded, failed, cancelled|
|run_id|one of: string or null|Identifier of the current (or most recent) run attempt, used to locate its error log. Null before the job first starts.|
|progress.total|one of: integer or null|Total number of items to process, or null when the size is not yet known.|
|progress.success|integer|Number of items processed successfully so far.|
|progress.error|integer|Number of items that failed so far. A count only — the actual messages live in the per-run error log.|
|progress.message|one of: string or null|Optional human-readable status line describing the current step.|
|progress.updated_at|string|UTC timestamp of the most recent progress update. Format: date-time|
|progress_detail|one of: object or null|Optional typed, worker-specific progress detail (validated against the worker's progress_model). Null for workers whose generic count progress is enough.|
|properties|one of: object or null|Optional static, worker-published descriptive properties for this job (validated against the worker's properties_model). Derived once from params at create time and unchanged over the run.|
|params|object|The validated parameters this job was created with.|
|result|one of: object or null|The job's output, present only once it has succeeded. Null otherwise.|
|error|one of: JobError or null|Failure summary, present only when the job has failed. Null otherwise.|
|metadata|object|Free-form attribution passed in at creation, stored verbatim.|
|project_id|one of: string or null|Project this job is scoped to, used for filtering and visibility.|
|supports_pause|boolean|Whether this job type can be paused and resumed.|
|created_at|string|UTC timestamp of when the job was created. Format: date-time|
|updated_at|string|UTC timestamp of the most recent change to the job record. Format: date-time|
|started_at|one of: string or null|UTC timestamp of when the job first started running. Null until it starts.|
|ended_at|one of: string or null|UTC timestamp of when the job reached a terminal state. Null until it ends.|

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### JobError

Small failure summary stamped on the record. Detail lives in the error log.

|Field|Type|Required|Description|
|-|-|-|-|
|error|one of: string or null|No|Short human-readable summary of why the job failed.|
|detail|one of: object or null|No|Optional structured context for the failure. Fuller detail lives in the error log.|

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
