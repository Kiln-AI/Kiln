# Jobs API

Run, monitor, and control background jobs, and stream their events.

|Endpoint|Method|Name|Description|Details File|
|-|-|-|-|-|
|`/api/jobs`|GET|List Jobs||get_api_jobs.md|
|`/api/jobs/wait`|POST|Wait For Jobs|Block until ALL the given jobs reach a terminal state, then return their records in the order given....|post_api_jobs_wait.md|
|`/api/jobs/evals/run`|POST|Run Eval Job|Start a background job that runs one split of an eval against one run config, and return at once. It...|post_api_jobs_evals_run.md|
|`/api/jobs/{type}`|POST|Create Job||post_api_jobs_type.md|
|`/api/jobs/{id}`|GET|Get Job||get_api_jobs_id.md|
|`/api/jobs/{id}`|DELETE|Delete Job||delete_api_jobs_id.md|
|`/api/jobs/{id}/result`|GET|Get Job Result||get_api_jobs_id_result.md|
|`/api/jobs/{id}/wait`|GET|Wait For Job|Block until the job reaches a terminal state, then return its record.  A pure observer: waiting neve...|get_api_jobs_id_wait.md|
|`/api/jobs/{id}/errors`|GET|Get Job Errors||get_api_jobs_id_errors.md|
|`/api/jobs/{id}/pause`|POST|Pause Job||post_api_jobs_id_pause.md|
|`/api/jobs/{id}/resume`|POST|Resume Job||post_api_jobs_id_resume.md|
|`/api/jobs/{id}/cancel`|POST|Cancel Job||post_api_jobs_id_cancel.md|
