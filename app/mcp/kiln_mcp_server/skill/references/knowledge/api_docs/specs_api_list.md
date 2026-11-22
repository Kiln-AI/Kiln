# Specs API

Create and manage Kiln Specs: AI guided evaluation generation.

|Endpoint|Method|Name|Description|Details File|
|-|-|-|-|-|
|`/api/projects/{project_id}/tasks/{task_id}/available_spec_name`|GET|Resolve an Available Spec Name|Check a candidate spec name against the task's existing specs and return an available one — the cand...|get_api_projects_project_id_tasks_task_id_available_spec_name.md|
|`/api/projects/{project_id}/tasks/{task_id}/specs`|GET|List Specs||get_api_projects_project_id_tasks_task_id_specs.md|
|`/api/projects/{project_id}/tasks/{task_id}/specs`|POST|Create Spec||post_api_projects_project_id_tasks_task_id_specs.md|
|`/api/projects/{project_id}/tasks/{task_id}/specs/{spec_id}`|GET|Get Spec||get_api_projects_project_id_tasks_task_id_specs_spec_id.md|
|`/api/projects/{project_id}/tasks/{task_id}/specs/{spec_id}`|PATCH|Update Spec||patch_api_projects_project_id_tasks_task_id_specs_spec_id.md|
|`/api/projects/{project_id}/tasks/{task_id}/specs/{spec_id}`|DELETE|Delete Spec||delete_api_projects_project_id_tasks_task_id_specs_spec_id.md|
