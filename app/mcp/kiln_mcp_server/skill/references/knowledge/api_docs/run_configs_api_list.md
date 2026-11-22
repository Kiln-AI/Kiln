# Run Configs API

Manage run configurations for tasks and evals.

|Endpoint|Method|Name|Description|Details File|
|-|-|-|-|-|
|`/api/projects/{project_id}/tasks/{task_id}/run_configs`|GET|List Run Configs||get_api_projects_project_id_tasks_task_id_run_configs.md|
|`/api/projects/{project_id}/tasks/{task_id}/run_configs`|POST|Create Run Config||post_api_projects_project_id_tasks_task_id_run_configs.md|
|`/api/projects/{project_id}/tasks/{task_id}/run_configs/{run_config_id}`|PATCH|Update Run Config||patch_api_projects_project_id_tasks_task_id_run_configs_run_config_id.md|
|`/api/projects/{project_id}/tasks/{task_id}/run_configs/{run_config_id}/eval_scores`|GET|Get Run Config Eval Scores||get_api_projects_project_id_tasks_task_id_run_configs_run_config_id_eval_scores.md|
|`/api/projects/{project_id}/tasks/{task_id}/run_configs/eval_scores`|GET|List Eval Scores For All Run Configs|Eval scores for every run config of the task, keyed by run config id. Each value matches the per-run...|get_api_projects_project_id_tasks_task_id_run_configs_eval_scores.md|
|`/api/validate_input_transform_template`|POST|Validate Input Transform Template||post_api_validate_input_transform_template.md|
|`/api/projects/{project_id}/tasks/{task_id}/mcp_run_config`|POST|Create Mcp Run Config||post_api_projects_project_id_tasks_task_id_mcp_run_config.md|
