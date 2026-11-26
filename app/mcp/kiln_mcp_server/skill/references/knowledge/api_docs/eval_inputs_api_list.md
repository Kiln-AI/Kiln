# Eval Inputs API

Author and manage eval input datasets for tasks.

|Endpoint|Method|Name|Description|Details File|
|-|-|-|-|-|
|`/api/projects/{project_id}/tasks/{task_id}/eval_inputs`|GET|List Eval Inputs|List a task's eval input items, optionally restricted to a filter.|get_api_projects_project_id_tasks_task_id_eval_inputs.md|
|`/api/projects/{project_id}/tasks/{task_id}/eval_inputs`|POST|Create Eval Input|Create an eval input item. Evals pick it up via their eval_input_filter_id, so tag it accordingly.|post_api_projects_project_id_tasks_task_id_eval_inputs.md|
|`/api/projects/{project_id}/tasks/{task_id}/eval_inputs/{eval_input_id}`|GET|Get Eval Input|Get one eval input item.|get_api_projects_project_id_tasks_task_id_eval_inputs_eval_input_id.md|
|`/api/projects/{project_id}/tasks/{task_id}/eval_inputs/{eval_input_id}`|PATCH|Update Eval Input|Update an eval input item's tags and/or reference data.  `data` is not editable and sending it is a ...|patch_api_projects_project_id_tasks_task_id_eval_inputs_eval_input_id.md|
|`/api/projects/{project_id}/tasks/{task_id}/eval_inputs/{eval_input_id}`|DELETE|Delete Eval Input|Delete an eval input item, if nothing on disk still points at it.  409 when anything does. Both kind...|delete_api_projects_project_id_tasks_task_id_eval_inputs_eval_input_id.md|
