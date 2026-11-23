# Create Job

**POST /api/jobs/{type}**

**Tags:** Jobs

Start a background job of a registered type. Returns at once, or with
wait=true when the job ends.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|type|string|Yes|The registered job type to run.|

### Query Parameters

|Name|Type|Required|Default|Description|
|-|-|-|-|-|
|wait|boolean|No|False|When true, block until the job reaches a terminal state and return the full JobRecord instead of CreateJobResponse.|
|timeout|one of: number or null|No||Seconds to wait when wait=true (504 on timeout). Omit to wait indefinitely.|

### Request Body

**Content Type:** `application/json`

|Field|Type|Required|Description|
|-|-|-|-|
|params|object|No|Type-specific job parameters, validated against the type's params model.|
|project_id|one of: string or null|No|Project to scope this job to (for filtering/visibility). Falls back to the params' project_id when omitted.|
|metadata|one of: object or null|No|Free-form pass-through attribution, stored verbatim.|

## Responses

### 201 Created

Successful Response

|Field|Type|Description|
|-|-|-|
|value|one of: CreateJobResponse, JobRecord||

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### CreateJobResponse

Response returned when a job is created.

|Field|Type|Required|Description|
|-|-|-|-|
|job_id|string|Yes|The id of the job: a new job, or an existing identical job.|
|status|string|Yes|One of: pending, running, paused, succeeded, failed, cancelled|

### JobError

Small failure summary stamped on the record. Detail lives in the error log.

|Field|Type|Required|Description|
|-|-|-|-|
|error|one of: string or null|No|Short human-readable summary of why the job failed.|
|detail|one of: object or null|No|Optional structured context for the failure. Fuller detail lives in the error log.|

### JobRecord

Ephemeral, in-memory bookkeeping for a single job. Never persisted to disk.

|Field|Type|Required|Description|
|-|-|-|-|
|id|string|Yes|Unique identifier for this job.|
|type|string|Yes|Registered job type name, determining which worker runs it.|
|status|string|Yes|One of: pending, running, paused, succeeded, failed, cancelled|
|run_id|one of: string or null|No|Identifier of the current (or most recent) run attempt, used to locate its error log. Null before the job first starts.|
|progress.total|one of: integer or null|No|Total number of items to process, or null when the size is not yet known.|
|progress.success|integer|No|Number of items processed successfully so far.|
|progress.error|integer|No|Number of items that failed so far. A count only — the actual messages live in the per-run error log.|
|progress.message|one of: string or null|No|Optional human-readable status line describing the current step.|
|progress.updated_at|string|No|UTC timestamp of the most recent progress update. Format: date-time|
|progress_detail|one of: object or null|No|Optional typed, worker-specific progress detail (validated against the worker's progress_model). Null for workers whose generic count progress is enough.|
|properties|one of: object or null|No|Optional static, worker-published descriptive properties for this job (validated against the worker's properties_model). Derived once from params at create time and unchanged over the run.|
|params|object|No|The validated parameters this job was created with.|
|result|one of: object or null|No|The job's output, present only once it has succeeded. Null otherwise.|
|error|one of: JobError or null|No|Failure summary, present only when the job has failed. Null otherwise.|
|metadata|object|No|Free-form attribution passed in at creation, stored verbatim.|
|project_id|one of: string or null|No|Project this job is scoped to, used for filtering and visibility.|
|supports_pause|boolean|No|Whether this job type can be paused and resumed.|
|created_at|string|No|UTC timestamp of when the job was created. Format: date-time|
|updated_at|string|No|UTC timestamp of the most recent change to the job record. Format: date-time|
|started_at|one of: string or null|No|UTC timestamp of when the job first started running. Null until it starts.|
|ended_at|one of: string or null|No|UTC timestamp of when the job reached a terminal state. Null until it ends.|

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
