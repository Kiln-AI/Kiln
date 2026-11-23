# Jobs API

Run, monitor, and control background jobs, and stream their events.

|Endpoint|Method|Name|Description|Details File|
|-|-|-|-|-|
|`/api/jobs`|GET|List Jobs|List background jobs, newest first, with filters for status, type, project and time.|get_api_jobs.md|
|`/api/jobs/wait`|POST|Wait For Jobs|Block until ALL the given jobs reach a terminal state, then return their records in the order given....|post_api_jobs_wait.md|
|`/api/jobs/evals/run`|POST|Run Eval Job|Start a background job that runs one split of an eval against one run config, and return at once. It...|post_api_jobs_evals_run.md|
|`/api/jobs/{type}`|POST|Create Job|Start a background job of a registered type. Returns at once, or with wait=true when the job ends.|post_api_jobs_type.md|
|`/api/jobs/{id}`|GET|Get Job|Get a background job's record: status, progress and result.|get_api_jobs_id.md|
|`/api/jobs/{id}`|DELETE|Delete Job|Delete the record of a background job that has ended (succeeded, failed or cancelled).|delete_api_jobs_id.md|
|`/api/jobs/{id}/result`|GET|Get Job Result|Get the result of a finished background job.|get_api_jobs_id_result.md|
|`/api/jobs/{id}/wait`|GET|Wait For Job|Block until the job reaches a terminal state, then return its record.  A pure observer: waiting neve...|get_api_jobs_id_wait.md|
|`/api/jobs/{id}/errors`|GET|Get Job Errors|Get the errors a background job logged for its items. Empty when the job is unknown or had none.|get_api_jobs_id_errors.md|
|`/api/jobs/{id}/pause`|POST|Pause Job|Pause a running background job. Resume it later with Resume Job.|post_api_jobs_id_pause.md|
|`/api/jobs/{id}/resume`|POST|Resume Job|Resume a paused background job.|post_api_jobs_id_resume.md|
|`/api/jobs/{id}/cancel`|POST|Cancel Job|Cancel a background job.|post_api_jobs_id_cancel.md|
