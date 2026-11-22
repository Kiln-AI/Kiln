# Tasks API

Create and manage tasks within projects.

|Endpoint|Method|Name|Description|Details File|
|-|-|-|-|-|
|`/api/projects/{project_id}/tasks`|GET|List Tasks||get_api_projects_project_id_tasks.md|
|`/api/projects/{project_id}/tasks`|POST|Create Task||post_api_projects_project_id_tasks.md|
|`/api/projects/{project_id}/tasks/{task_id}`|GET|Get Task||get_api_projects_project_id_tasks_task_id.md|
|`/api/projects/{project_id}/tasks/{task_id}`|PATCH|Update Task||patch_api_projects_project_id_tasks_task_id.md|
|`/api/projects/{project_id}/tasks/{task_id}`|DELETE|Delete Task||delete_api_projects_project_id_tasks_task_id.md|
|`/api/projects/{project_id}/tasks/{task_id}/rating_options`|GET|Get Rating Options|Determines which rating options should be shown for a given dataset item.|get_api_projects_project_id_tasks_task_id_rating_options.md|
|`/api/task_summaries`|GET|Task Summaries (agent-tuned)|Return a workspace-wide list of projects and their tasks, with truncated task.instruction values. Un...|get_api_task_summaries.md|
|`/api/projects/{project_id}/tasks_compatible_with_tool`|GET|Tasks Compatible With Tool||get_api_projects_project_id_tasks_compatible_with_tool.md|
|`/api/projects/{project_id}/create_task_from_tool`|POST|Create Task From Tool||post_api_projects_project_id_create_task_from_tool.md|
