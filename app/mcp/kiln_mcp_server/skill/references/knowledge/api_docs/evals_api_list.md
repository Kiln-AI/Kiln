# Evals API

Create and run evaluations for tasks.

|Endpoint|Method|Name|Description|Details File|
|-|-|-|-|-|
|`/api/projects/{project_id}/tasks/{task_id}/create_evaluator`|POST|Create Evaluator||post_api_projects_project_id_tasks_task_id_create_evaluator.md|
|`/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}`|GET|Get Eval||get_api_projects_project_id_tasks_task_id_evals_eval_id.md|
|`/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}`|PATCH|Update Eval||patch_api_projects_project_id_tasks_task_id_evals_eval_id.md|
|`/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}`|DELETE|Delete Eval||delete_api_projects_project_id_tasks_task_id_evals_eval_id.md|
|`/api/projects/{project_id}/tasks/{task_id}/evals`|GET|List Evals|List all evals for a task.|get_api_projects_project_id_tasks_task_id_evals.md|
|`/api/projects/{project_id}/tasks/{task_id}/eval_default_judge_types`|GET|Get Default Judge Types|Map of eval ID to its default judge's type discriminator.  V2 configs report their properties type (...|get_api_projects_project_id_tasks_task_id_eval_default_judge_types.md|
|`/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/eval_configs`|GET|List Eval Configs||get_api_projects_project_id_tasks_task_id_evals_eval_id_eval_configs.md|
|`/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/eval_config/{eval_config_id}`|GET|Get Eval Config||get_api_projects_project_id_tasks_task_id_evals_eval_id_eval_config_eval_config_id.md|
|`/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/create_eval_config`|POST|Create Eval Config||post_api_projects_project_id_tasks_task_id_evals_eval_id_create_eval_config.md|
|`/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/create_llm_judge_config`|POST|Create LLM Judge Eval Config||post_api_projects_project_id_tasks_task_id_evals_eval_id_create_llm_judge_config.md|
|`/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/default_llm_judge_prompt`|GET|Get Default LLM Judge Prompt||get_api_projects_project_id_tasks_task_id_evals_eval_id_default_llm_judge_prompt.md|
|`/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/test_v2_eval`|POST|Test V2 Eval Config||post_api_projects_project_id_tasks_task_id_evals_eval_id_test_v2_eval.md|
|`/api/projects/{project_id}/tasks/{task_id}/test_v2_eval_draft`|POST|Test V2 Eval Config Draft|Test a judge config for an eval that hasn't been created yet.  Builds a transient in-memory eval fro...|post_api_projects_project_id_tasks_task_id_test_v2_eval_draft.md|
|`/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/eval_config/{eval_config_id}/run_comparison`|GET|Run Run Config Comparison|Run a specific eval config against one or more run configs and stream progress via SSE. Executes mod...|get_api_projects_project_id_tasks_task_id_evals_eval_id_eval_config_eval_config_id_run_comparison.md|
|`/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/set_current_eval_config/{eval_config_id}`|POST|Set Default Eval Config||post_api_projects_project_id_tasks_task_id_evals_eval_id_set_current_eval_config_eval_config_id.md|
|`/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/run_calibration`|GET|Run Calibration|Run all eval configs against each other for calibration and stream progress via SSE. Used to check t...|get_api_projects_project_id_tasks_task_id_evals_eval_id_run_calibration.md|
|`/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/eval_config/{eval_config_id}/run_config/{run_config_id}/results`|GET|Get Eval Run Results|Results for one run config, scoped to one of the eval's splits.|get_api_projects_project_id_tasks_task_id_evals_eval_id_eval_config_eval_config_id_run_config_run_config_id_results.md|
|`/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/eval_config/{eval_config_id}/eval_run/{eval_run_id}/judge_trace`|GET|Get Eval Run Judge Trace|The judge's full conversation for one eval run: the system prompt, the rendered judge prompt, and ev...|get_api_projects_project_id_tasks_task_id_evals_eval_id_eval_config_eval_config_id_eval_run_eval_run_id_judge_trace.md|
|`/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/progress`|GET|Get Eval Progress||get_api_projects_project_id_tasks_task_id_evals_eval_id_progress.md|
|`/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/eval_config/{eval_config_id}/score_summary`|GET|Get Run Config Score Summary||get_api_projects_project_id_tasks_task_id_evals_eval_id_eval_config_eval_config_id_score_summary.md|
|`/api/projects/{project_id}/tasks/{task_id}/eval_results_summary`|GET|Get Eval Results Summary||get_api_projects_project_id_tasks_task_id_eval_results_summary.md|
|`/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/eval_configs_score_summary`|GET|Get Eval Config Comparison Summary||get_api_projects_project_id_tasks_task_id_evals_eval_id_eval_configs_score_summary.md|
|`/api/projects/{project_id}/add_code_trust`|GET|Check code trust for a project||get_api_projects_project_id_add_code_trust.md|
|`/api/projects/{project_id}/add_code_trust`|POST|Add code trust for a project||post_api_projects_project_id_add_code_trust.md|
