# Projects API

Create, read, update, delete, and import projects.

|Endpoint|Method|Name|Description|Details File|
|-|-|-|-|-|
|`/api/projects`|GET|List Projects||get_api_projects.md|
|`/api/projects`|POST|Create Project||post_api_projects.md|
|`/api/projects/{project_id}`|GET|Get Project||get_api_projects_project_id.md|
|`/api/projects/{project_id}`|PATCH|Update Project||patch_api_projects_project_id.md|
|`/api/import_project`|POST|Import Project||post_api_import_project.md|
|`/api/delete_project/{project_id}`|DELETE|Delete Project|Removes the project from Kiln but does not delete the files from disk.|delete_api_delete_project_project_id.md|
