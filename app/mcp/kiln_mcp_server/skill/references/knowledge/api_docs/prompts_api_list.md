# Prompts API

Create and manage prompts for tasks.

|Endpoint|Method|Name|Description|Details File|
|-|-|-|-|-|
|`/api/projects/{project_id}/tasks/{task_id}/prompts`|GET|List Prompts||get_api_projects_project_id_tasks_task_id_prompts.md|
|`/api/projects/{project_id}/tasks/{task_id}/prompts`|POST|Create Prompt||post_api_projects_project_id_tasks_task_id_prompts.md|
|`/api/projects/{project_id}/tasks/{task_id}/prompts/{prompt_id}`|PATCH|Update Prompt||patch_api_projects_project_id_tasks_task_id_prompts_prompt_id.md|
|`/api/projects/{project_id}/tasks/{task_id}/prompts/{prompt_id}`|DELETE|Delete Prompt||delete_api_projects_project_id_tasks_task_id_prompts_prompt_id.md|
|`/api/projects/{project_id}/tasks/{task_id}/build_prompt_with_examples`|POST|Build Prompt With Examples|Build a prompt with the task's prompt, requirements, and optional custom examples.  Uses the same fo...|post_api_projects_project_id_tasks_task_id_build_prompt_with_examples.md|
|`/api/projects/{project_id}/tasks/{task_id}/gen_prompt/{prompt_id}`|GET|Generate Prompt||get_api_projects_project_id_tasks_task_id_gen_prompt_prompt_id.md|
