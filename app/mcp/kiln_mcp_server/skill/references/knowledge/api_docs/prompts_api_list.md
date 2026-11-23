# Prompts API

Create and manage prompts for tasks.

|Endpoint|Method|Name|Description|Details File|
|-|-|-|-|-|
|`/api/projects/{project_id}/tasks/{task_id}/prompts`|GET|List Prompts|List the task's prompts and prompt generators, with the ID to use for each.  Includes saved prompts ...|get_api_projects_project_id_tasks_task_id_prompts.md|
|`/api/projects/{project_id}/tasks/{task_id}/prompts`|POST|Create Prompt|Save a custom prompt for the task. Its ID, id::<prompt_id>, can be used in run configs.|post_api_projects_project_id_tasks_task_id_prompts.md|
|`/api/projects/{project_id}/tasks/{task_id}/prompts/{prompt_id}`|PATCH|Update Prompt|Change a custom prompt's name or description. Its text can't change: save a new prompt.|patch_api_projects_project_id_tasks_task_id_prompts_prompt_id.md|
|`/api/projects/{project_id}/tasks/{task_id}/prompts/{prompt_id}`|DELETE|Delete Prompt|Delete a custom prompt.|delete_api_projects_project_id_tasks_task_id_prompts_prompt_id.md|
|`/api/projects/{project_id}/tasks/{task_id}/build_prompt_with_examples`|POST|Build Prompt With Examples|Build a prompt with the task's prompt, requirements, and optional custom examples.  Uses the same fo...|post_api_projects_project_id_tasks_task_id_build_prompt_with_examples.md|
|`/api/projects/{project_id}/tasks/{task_id}/gen_prompt/{prompt_id}`|GET|Generate Prompt|Render the full prompt text that a prompt ID gives for the task, as the model would see it.|get_api_projects_project_id_tasks_task_id_gen_prompt_prompt_id.md|
