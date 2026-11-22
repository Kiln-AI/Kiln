# Tools & MCP API

Manage tool servers and MCP connections.

|Endpoint|Method|Name|Description|Details File|
|-|-|-|-|-|
|`/api/projects/{project_id}/available_tools`|GET|Get Available Tools||get_api_projects_project_id_available_tools.md|
|`/api/projects/{project_id}/available_tool_servers`|GET|Get Available Tool Servers||get_api_projects_project_id_available_tool_servers.md|
|`/api/projects/{project_id}/kiln_task_tools`|GET|Get Kiln Task Tools||get_api_projects_project_id_kiln_task_tools.md|
|`/api/projects/{project_id}/tool_servers/{tool_server_id}`|GET|Get Tool Server||get_api_projects_project_id_tool_servers_tool_server_id.md|
|`/api/projects/{project_id}/tool_servers/{tool_server_id}`|DELETE|Delete Tool Server||delete_api_projects_project_id_tool_servers_tool_server_id.md|
|`/api/projects/{project_id}/tool_servers/{tool_server_id}/config`|GET|Get Tool Server Config||get_api_projects_project_id_tool_servers_tool_server_id_config.md|
|`/api/projects/{project_id}/connect_remote_mcp`|POST|Connect Remote Mcp||post_api_projects_project_id_connect_remote_mcp.md|
|`/api/projects/{project_id}/edit_remote_mcp/{tool_server_id}`|PATCH|Edit Remote Mcp||patch_api_projects_project_id_edit_remote_mcp_tool_server_id.md|
|`/api/projects/{project_id}/connect_local_mcp`|POST|Connect Local Mcp||post_api_projects_project_id_connect_local_mcp.md|
|`/api/projects/{project_id}/edit_local_mcp/{tool_server_id}`|PATCH|Edit Local Mcp||patch_api_projects_project_id_edit_local_mcp_tool_server_id.md|
|`/api/projects/{project_id}/tool_servers/{tool_server_id}/archive`|POST|Archive Tool Server||post_api_projects_project_id_tool_servers_tool_server_id_archive.md|
|`/api/projects/{project_id}/kiln_task_tool`|POST|Add Kiln Task Tool||post_api_projects_project_id_kiln_task_tool.md|
|`/api/projects/{project_id}/edit_kiln_task_tool/{tool_server_id}`|PATCH|Edit Kiln Task Tool||patch_api_projects_project_id_edit_kiln_task_tool_tool_server_id.md|
|`/api/demo_tools`|GET|Get Demo Tools||get_api_demo_tools.md|
|`/api/demo_tools`|POST|Set Demo Tools||post_api_demo_tools.md|
|`/api/projects/{project_id}/search_tools`|GET|Get Search Tools||get_api_projects_project_id_search_tools.md|
|`/api/projects/{project_id}/tasks/{task_id}/tools/{tool_id}/definition`|GET|Get Tool Definition|Get the actual OpenAI tool definition for a specific tool ID.  This returns the real function name a...|get_api_projects_project_id_tasks_task_id_tools_tool_id_definition.md|
