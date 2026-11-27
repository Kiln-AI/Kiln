# Run Configs API

Manage run configurations for tasks and evals.

|Endpoint|Method|Name|Description|Details File|
|-|-|-|-|-|
|`/api/projects/{project_id}/tasks/{task_id}/run_configs`|GET|List Run Configs|List the task's saved run configs, and a run config for each completed fine-tune.|get_api_projects_project_id_tasks_task_id_run_configs.md|
|`/api/projects/{project_id}/tasks/{task_id}/run_configs`|POST|Create Run Config|Create a run config for the task: the model, prompt, tools and settings to run it with.|post_api_projects_project_id_tasks_task_id_run_configs.md|
|`/api/projects/{project_id}/tasks/{task_id}/run_configs/{run_config_id}`|PATCH|Update Run Config|Change a run config's name, starred flag or prompt name. What it runs can't change: create a new run...|patch_api_projects_project_id_tasks_task_id_run_configs_run_config_id.md|
|`/api/projects/{project_id}/tasks/{task_id}/run_configs/{run_config_id}/eval_scores`|GET|Get Run Config Eval Scores|Get one run config's scores on every eval of the task.|get_api_projects_project_id_tasks_task_id_run_configs_run_config_id_eval_scores.md|
|`/api/projects/{project_id}/tasks/{task_id}/run_configs/eval_scores`|GET|List Eval Scores For All Run Configs|Eval scores for every run config of the task, keyed by run config id. Each value matches the per-run...|get_api_projects_project_id_tasks_task_id_run_configs_eval_scores.md|
|`/api/validate_input_transform_template`|POST|Validate Input Transform Template|Check that an input transform template is valid Jinja2, and return the error when it is not.|post_api_validate_input_transform_template.md|
|`/api/projects/{project_id}/tasks/{task_id}/mcp_run_config`|POST|Create Mcp Run Config|Create a run config that runs the task by calling a tool on an MCP server, in place of a model.|post_api_projects_project_id_tasks_task_id_mcp_run_config.md|
