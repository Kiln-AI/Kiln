# Projects API

Create, read, update, delete, and import projects.

|Endpoint|Method|Name|Description|Details File|
|-|-|-|-|-|
|`/api/projects`|GET|List Projects|List the projects Kiln knows, with their IDs.|get_api_projects.md|
|`/api/projects`|POST|Create Project|Create a project in the default Kiln Projects folder.|post_api_projects.md|
|`/api/projects/{project_id}`|GET|Get Project|Get one project.|get_api_projects_project_id.md|
|`/api/projects/{project_id}`|PATCH|Update Project|Change a project's name or description.|patch_api_projects_project_id.md|
|`/api/import_project`|POST|Import Project|Add an existing project to Kiln from the path of its project.kiln file.|post_api_import_project.md|
|`/api/delete_project/{project_id}`|DELETE|Delete Project|Removes the project from Kiln but does not delete the files from disk.|delete_api_delete_project_project_id.md|
