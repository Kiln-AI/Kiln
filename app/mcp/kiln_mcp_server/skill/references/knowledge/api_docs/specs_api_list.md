# Specs API

Create and manage Kiln Specs: AI guided evaluation generation.

|Endpoint|Method|Name|Description|Details File|
|-|-|-|-|-|
|`/api/projects/{project_id}/tasks/{task_id}/available_spec_name`|GET|Resolve an Available Spec Name|Suggest a free spec name: the candidate itself, or the nearest suffixed one.  The candidate is check...|get_api_projects_project_id_tasks_task_id_available_spec_name.md|
|`/api/projects/{project_id}/tasks/{task_id}/specs`|GET|List Specs|List the task's specs.|get_api_projects_project_id_tasks_task_id_specs.md|
|`/api/projects/{project_id}/tasks/{task_id}/specs`|POST|Create Spec|Create a spec: a requirement for the task's output, with the eval that measures it.|post_api_projects_project_id_tasks_task_id_specs.md|
|`/api/projects/{project_id}/tasks/{task_id}/specs/{spec_id}`|GET|Get Spec|Get one spec.|get_api_projects_project_id_tasks_task_id_specs_spec_id.md|
|`/api/projects/{project_id}/tasks/{task_id}/specs/{spec_id}`|PATCH|Update Spec|Change a spec's name, definition, properties, priority, status or tags.|patch_api_projects_project_id_tasks_task_id_specs_spec_id.md|
|`/api/projects/{project_id}/tasks/{task_id}/specs/{spec_id}`|DELETE|Delete Spec|Delete a spec.|delete_api_projects_project_id_tasks_task_id_specs_spec_id.md|
