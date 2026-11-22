# Copilot API

AI copilot for spec generation, refinement, and data generation.

|Endpoint|Method|Name|Description|Details File|
|-|-|-|-|-|
|`/api/copilot/clarify_spec`|POST|Clarify Spec||post_api_copilot_clarify_spec.md|
|`/api/copilot/refine_spec`|POST|Refine Spec||post_api_copilot_refine_spec.md|
|`/api/copilot/generate_batch`|POST|Generate Batch||post_api_copilot_generate_batch.md|
|`/api/copilot/question_spec`|POST|Question Spec||post_api_copilot_question_spec.md|
|`/api/copilot/refine_spec_with_question_answers`|POST|Submit Question Answers||post_api_copilot_refine_spec_with_question_answers.md|
|`/api/projects/{project_id}/tasks/{task_id}/copilot/data_guide_job/start`|POST|Start Data Guide Job|Kick off the input data guide draft job on kiln_server and return its job id. The job summarizes and...|post_api_projects_project_id_tasks_task_id_copilot_data_guide_job_start.md|
|`/api/projects/{project_id}/tasks/{task_id}/copilot/parse_import_file`|POST|Parse Import File|Parse an uploaded bulk-import file of input examples for the data guide, server-side.  Both task typ...|post_api_projects_project_id_tasks_task_id_copilot_parse_import_file.md|
|`/api/projects/{project_id}/tasks/{task_id}/copilot/data_guide_job/{job_id}/status`|GET|Data Guide Job Status|Return the current status of a data guide draft job (e.g. running, succeeded, failed, cancelled). Th...|get_api_projects_project_id_tasks_task_id_copilot_data_guide_job_job_id_status.md|
|`/api/projects/{project_id}/tasks/{task_id}/copilot/data_guide_job/{job_id}/result`|GET|Data Guide Job Result|Return the draft guide markdown produced by a completed data guide draft job. The web UI calls this ...|get_api_projects_project_id_tasks_task_id_copilot_data_guide_job_job_id_result.md|
|`/api/projects/{project_id}/tasks/{task_id}/spec_with_copilot`|POST|Create Spec With Copilot|Create a spec using Kiln Copilot.  This endpoint uses Kiln Copilot to create: 1. An Eval for the spe...|post_api_projects_project_id_tasks_task_id_spec_with_copilot.md|
|`/api/projects/{project_id}/tasks/{task_id}/copilot/batch_plan`|POST|Batch Plan|Plan a synthetic batch: turn the user's guidance + count into one tailored prompt per input (plus a ...|post_api_projects_project_id_tasks_task_id_copilot_batch_plan.md|
|`/api/chat/version_policy`|GET|Client version policy|Proxy to Kiln Copilot ``GET /v1/chat/version_policy``.  Lets the assistant page show the upgrade ban...|get_api_chat_version_policy.md|
|`/api/chat/sessions`|GET|List chat sessions|Proxy to Kiln Copilot ``GET /v1/chat/sessions``.|get_api_chat_sessions.md|
|`/api/chat/sessions/{session_id}`|GET|Get chat session|Proxy to Kiln Copilot ``GET /v1/chat/sessions/{session_id}``.|get_api_chat_sessions_session_id.md|
|`/api/chat/sessions/{session_id}`|DELETE|Delete chat session|Proxy to Kiln Copilot ``DELETE /v1/chat/sessions/{session_id}``.|delete_api_chat_sessions_session_id.md|
