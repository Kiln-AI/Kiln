# Copilot API

AI copilot for spec generation, refinement, and data generation.

|Endpoint|Method|Name|Description|Details File|
|-|-|-|-|-|
|`/api/copilot/clarify_spec`|POST|Clarify Spec|Generate example inputs and outputs that test a draft spec, for the user to judge (needs Kiln Pro). ...|post_api_copilot_clarify_spec.md|
|`/api/copilot/refine_spec`|POST|Refine Spec|Propose edits to a spec's fields from the user's feedback on examples (needs Kiln Pro). Saves nothin...|post_api_copilot_refine_spec.md|
|`/api/copilot/generate_batch`|POST|Generate Batch|Generate a batch of synthetic inputs for a spec, grouped by topic (needs Kiln Pro). Saves nothing.|post_api_copilot_generate_batch.md|
|`/api/copilot/question_spec`|POST|Question Spec|Generate clarifying questions about a draft spec for the user to answer (needs Kiln Pro).|post_api_copilot_question_spec.md|
|`/api/copilot/refine_spec_with_question_answers`|POST|Submit Question Answers|Propose spec edits and an eval name from the user's answers to Question Spec (needs Kiln Pro). Saves...|post_api_copilot_refine_spec_with_question_answers.md|
|`/api/projects/{project_id}/tasks/{task_id}/copilot/data_guide_job/start`|POST|Start Data Guide Job|Kick off the input data guide draft job on kiln_server and return its job id. The job summarizes and...|post_api_projects_project_id_tasks_task_id_copilot_data_guide_job_start.md|
|`/api/projects/{project_id}/tasks/{task_id}/copilot/parse_import_file`|POST|Parse Import File|Parse an uploaded bulk-import file of input examples for the data guide, server-side.  Both task typ...|post_api_projects_project_id_tasks_task_id_copilot_parse_import_file.md|
|`/api/projects/{project_id}/tasks/{task_id}/copilot/data_guide_job/{job_id}/status`|GET|Data Guide Job Status|Return the current status of a data guide draft job (e.g. running, succeeded, failed, cancelled). Th...|get_api_projects_project_id_tasks_task_id_copilot_data_guide_job_job_id_status.md|
|`/api/projects/{project_id}/tasks/{task_id}/copilot/data_guide_job/{job_id}/result`|GET|Data Guide Job Result|Return the draft guide markdown produced by a completed data guide draft job. The web UI calls this ...|get_api_projects_project_id_tasks_task_id_copilot_data_guide_job_job_id_result.md|
|`/api/projects/{project_id}/tasks/{task_id}/spec_with_copilot`|POST|Create Spec With Copilot|Create a spec using Kiln Copilot.  This endpoint uses Kiln Copilot to create: 1. An Eval for the spe...|post_api_projects_project_id_tasks_task_id_spec_with_copilot.md|
|`/api/projects/{project_id}/tasks/{task_id}/copilot/batch_plan`|POST|Batch Plan|Plan a synthetic batch: one tailored prompt per input, from the user's guidance.  Turns the guidance...|post_api_projects_project_id_tasks_task_id_copilot_batch_plan.md|
|`/api/chat/version_policy`|GET|Client version policy|Check whether this app version must or should upgrade for the Kiln Assistant.  Proxies Kiln Copilot'...|get_api_chat_version_policy.md|
|`/api/chat/sessions`|GET|List chat sessions|List the user's Kiln Assistant chat sessions (needs Kiln Pro).  Proxies Kiln Copilot's ``GET /v1/cha...|get_api_chat_sessions.md|
|`/api/chat/sessions/{session_id}`|GET|Get chat session|Get one Kiln Assistant chat session with its messages (needs Kiln Pro).  Proxies Kiln Copilot's ``GE...|get_api_chat_sessions_session_id.md|
|`/api/chat/sessions/{session_id}`|DELETE|Delete chat session|Delete one Kiln Assistant chat session (needs Kiln Pro).  Proxies Kiln Copilot's ``DELETE /v1/chat/s...|delete_api_chat_sessions_session_id.md|
