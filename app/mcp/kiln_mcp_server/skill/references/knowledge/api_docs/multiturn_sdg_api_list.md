# Multiturn SDG API

Generate multi-turn synthetic-user conversation datasets for eval.

|Endpoint|Method|Name|Description|Details File|
|-|-|-|-|-|
|`/api/projects/{project_id}/tasks/{task_id}/multiturn_sdg/generate_cases`|POST|Generate Multi-Turn SU Cases|Generate synthetic-user cases (persona, goal, first message) for a multi-turn task (needs Kiln Pro)....|post_api_projects_project_id_tasks_task_id_multiturn_sdg_generate_cases.md|
|`/api/projects/{project_id}/tasks/{task_id}/multiturn_sdg/run_cases_batch`|POST|Run Multi-Turn SU Cases Batch|Run one synthetic-user conversation with the task per case, saving the runs.  Streams progress as ev...|post_api_projects_project_id_tasks_task_id_multiturn_sdg_run_cases_batch.md|
