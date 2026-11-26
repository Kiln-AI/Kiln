# Runs API

Execute tasks. View and manage the task run datastore.

|Endpoint|Method|Name|Description|Details File|
|-|-|-|-|-|
|`/api/projects/{project_id}/tasks/{task_id}/runs/{run_id}`|GET|Get Run|Get one run (dataset item): input, output, ratings, tags and trace.|get_api_projects_project_id_tasks_task_id_runs_run_id.md|
|`/api/projects/{project_id}/tasks/{task_id}/runs/{run_id}`|PATCH|Update Run|Change fields of a run, such as its rating, tags or repaired output.|patch_api_projects_project_id_tasks_task_id_runs_run_id.md|
|`/api/projects/{project_id}/tasks/{task_id}/runs/{run_id}`|DELETE|Delete Run|Delete one run from the task's dataset.|delete_api_projects_project_id_tasks_task_id_runs_run_id.md|
|`/api/projects/{project_id}/tasks/{task_id}/runs/{run_id}/chain`|GET|Get Run Chain|Get the chain of runs of a multi-turn conversation, from the first turn to the given run.|get_api_projects_project_id_tasks_task_id_runs_run_id_chain.md|
|`/api/projects/{project_id}/tasks/{task_id}/runs`|GET|List Runs|List the task's runs (its dataset items), in full. For multi-turn tasks, only leaf TaskRuns (those t...|get_api_projects_project_id_tasks_task_id_runs.md|
|`/api/projects/{project_id}/tasks/{task_id}/runs`|POST|Create Run|Create a TaskRun directly without running a model.|post_api_projects_project_id_tasks_task_id_runs.md|
|`/api/projects/{project_id}/tasks/{task_id}/runs_summaries`|GET|List Run Summaries|List short summaries of the task's runs, lighter than List Runs. For multi-turn tasks, only leaf Tas...|get_api_projects_project_id_tasks_task_id_runs_summaries.md|
|`/api/projects/{project_id}/tasks/{task_id}/runs/delete`|POST|Delete Runs|Delete several runs from the task's dataset. Reports the ones it could not delete.|post_api_projects_project_id_tasks_task_id_runs_delete.md|
|`/api/projects/{project_id}/tasks/{task_id}/run`|POST|Execute Run|Invoke an AI model on a task and return the result. Unlike 'Create Run', this actually executes the ...|post_api_projects_project_id_tasks_task_id_run.md|
|`/api/projects/{project_id}/tasks/{task_id}/runs/edit_tags`|POST|Edit Run Tags|Add tags to, or remove tags from, several runs at once.|post_api_projects_project_id_tasks_task_id_runs_edit_tags.md|
|`/api/projects/{project_id}/tasks/{task_id}/runs/bulk_upload`|POST|Bulk Upload Runs|Import runs into the task's dataset from a CSV file, as multipart form data.|post_api_projects_project_id_tasks_task_id_runs_bulk_upload.md|
|`/api/projects/{project_id}/tasks/{task_id}/tags`|GET|List Run Tags|Count the task's runs for each tag. Counts only include tags from leaf TaskRuns. For multi-turn task...|get_api_projects_project_id_tasks_task_id_tags.md|
|`/api/projects/{project_id}/tasks/{task_id}/runs/{run_id}/generate_repair`|POST|Generate Repair|Invoke an AI model to generate a repaired output for a task run based on evaluator feedback. Returns...|post_api_projects_project_id_tasks_task_id_runs_run_id_generate_repair.md|
|`/api/projects/{project_id}/tasks/{task_id}/runs/{run_id}/save_repair`|POST|Save Repair|Persist a repaired output for a task run. Use after reviewing the result from Generate Repair or cre...|post_api_projects_project_id_tasks_task_id_runs_run_id_save_repair.md|
