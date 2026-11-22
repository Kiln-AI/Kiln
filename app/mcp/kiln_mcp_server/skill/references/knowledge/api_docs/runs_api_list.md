# Runs API

Execute tasks. View and manage the task run datastore.

|Endpoint|Method|Name|Description|Details File|
|-|-|-|-|-|
|`/api/projects/{project_id}/tasks/{task_id}/runs/{run_id}`|GET|Get Run||get_api_projects_project_id_tasks_task_id_runs_run_id.md|
|`/api/projects/{project_id}/tasks/{task_id}/runs/{run_id}`|PATCH|Update Run||patch_api_projects_project_id_tasks_task_id_runs_run_id.md|
|`/api/projects/{project_id}/tasks/{task_id}/runs/{run_id}`|DELETE|Delete Run||delete_api_projects_project_id_tasks_task_id_runs_run_id.md|
|`/api/projects/{project_id}/tasks/{task_id}/runs/{run_id}/chain`|GET|Get Run Chain||get_api_projects_project_id_tasks_task_id_runs_run_id_chain.md|
|`/api/projects/{project_id}/tasks/{task_id}/runs`|GET|List Runs|For multi-turn tasks, only leaf TaskRuns (those that are not the parent of another run via parent_ta...|get_api_projects_project_id_tasks_task_id_runs.md|
|`/api/projects/{project_id}/tasks/{task_id}/runs`|POST|Create Run|Create a TaskRun directly without running a model.|post_api_projects_project_id_tasks_task_id_runs.md|
|`/api/projects/{project_id}/tasks/{task_id}/runs_summaries`|GET|List Run Summaries|For multi-turn tasks, only leaf TaskRuns (those that are not the parent of another run via parent_ta...|get_api_projects_project_id_tasks_task_id_runs_summaries.md|
|`/api/projects/{project_id}/tasks/{task_id}/runs/delete`|POST|Delete Runs||post_api_projects_project_id_tasks_task_id_runs_delete.md|
|`/api/projects/{project_id}/tasks/{task_id}/run`|POST|Execute Run|Invoke an AI model on a task and return the result. Unlike 'Create Run', this actually executes the ...|post_api_projects_project_id_tasks_task_id_run.md|
|`/api/projects/{project_id}/tasks/{task_id}/runs/edit_tags`|POST|Edit Run Tags||post_api_projects_project_id_tasks_task_id_runs_edit_tags.md|
|`/api/projects/{project_id}/tasks/{task_id}/runs/bulk_upload`|POST|Bulk Upload Runs||post_api_projects_project_id_tasks_task_id_runs_bulk_upload.md|
|`/api/projects/{project_id}/tasks/{task_id}/tags`|GET|List Run Tags|Counts only include tags from leaf TaskRuns. For multi-turn tasks, tags attached to intermediate run...|get_api_projects_project_id_tasks_task_id_tags.md|
|`/api/projects/{project_id}/tasks/{task_id}/runs/{run_id}/generate_repair`|POST|Generate Repair|Invoke an AI model to generate a repaired output for a task run based on evaluator feedback. Returns...|post_api_projects_project_id_tasks_task_id_runs_run_id_generate_repair.md|
|`/api/projects/{project_id}/tasks/{task_id}/runs/{run_id}/save_repair`|POST|Save Repair|Persist a repaired output for a task run. Use after reviewing the result from Generate Repair or cre...|post_api_projects_project_id_tasks_task_id_runs_run_id_save_repair.md|
