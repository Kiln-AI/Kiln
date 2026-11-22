# OpenEnv Servers API

Manage OpenEnv servers: Kiln's saved pointers to running OpenEnv environments that play an agent's tool set, and the tools they serve.

|Endpoint|Method|Name|Description|Details File|
|-|-|-|-|-|
|`/api/projects/{project_id}/openenv_servers`|GET|List OpenEnv Servers||get_api_projects_project_id_openenv_servers.md|
|`/api/projects/{project_id}/openenv_servers`|POST|Create OpenEnv Server||post_api_projects_project_id_openenv_servers.md|
|`/api/projects/{project_id}/openenv_servers/{openenv_server_id}`|GET|Get OpenEnv Server||get_api_projects_project_id_openenv_servers_openenv_server_id.md|
|`/api/projects/{project_id}/openenv_servers/{openenv_server_id}`|PATCH|Update OpenEnv Server||patch_api_projects_project_id_openenv_servers_openenv_server_id.md|
|`/api/projects/{project_id}/openenv_servers/{openenv_server_id}`|DELETE|Delete OpenEnv Server|Delete an OpenEnv server, if no saved eval input still resets into it.  409 when one does. An eval i...|delete_api_projects_project_id_openenv_servers_openenv_server_id.md|
|`/api/projects/{project_id}/openenv_servers/{openenv_server_id}/tools`|GET|List OpenEnv Server Tools|The tools the OpenEnv server's environment serves, read fresh from the running server at url.|get_api_projects_project_id_openenv_servers_openenv_server_id_tools.md|
