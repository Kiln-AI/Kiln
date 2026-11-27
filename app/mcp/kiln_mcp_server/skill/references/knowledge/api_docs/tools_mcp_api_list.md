# Tools & MCP API

Manage tool servers and MCP connections.

|Endpoint|Method|Name|Description|Details File|
|-|-|-|-|-|
|`/api/projects/{project_id}/available_tools`|GET|Get Available Tools|List every tool the project's tasks can use, grouped by kind.  The kinds are built-in tools, MCP ser...|get_api_projects_project_id_available_tools.md|
|`/api/projects/{project_id}/available_tool_servers`|GET|Get Available Tool Servers|List the project's tool servers, with any secrets they are missing.  Tool servers are remote and loc...|get_api_projects_project_id_available_tool_servers.md|
|`/api/projects/{project_id}/kiln_task_tools`|GET|Get Kiln Task Tools|List the Kiln tasks the project offers as tools, with each one's tool name and run config.|get_api_projects_project_id_kiln_task_tools.md|
|`/api/projects/{project_id}/tool_servers/{tool_server_id}`|GET|Get Tool Server|Get one tool server and the tools it serves now. Connects to the server to list them.|get_api_projects_project_id_tool_servers_tool_server_id.md|
|`/api/projects/{project_id}/tool_servers/{tool_server_id}`|DELETE|Delete Tool Server|Delete a tool server from the project.|delete_api_projects_project_id_tool_servers_tool_server_id.md|
|`/api/projects/{project_id}/tool_servers/{tool_server_id}/config`|GET|Get Tool Server Config|Get one tool server's saved settings, without connecting to it.|get_api_projects_project_id_tool_servers_tool_server_id_config.md|
|`/api/projects/{project_id}/connect_remote_mcp`|POST|Connect Remote Mcp|Add a remote MCP server (an HTTP URL) to the project as a tool server.|post_api_projects_project_id_connect_remote_mcp.md|
|`/api/projects/{project_id}/edit_remote_mcp/{tool_server_id}`|PATCH|Edit Remote Mcp|Change a remote MCP tool server's name, description, URL, headers or archived flag.|patch_api_projects_project_id_edit_remote_mcp_tool_server_id.md|
|`/api/projects/{project_id}/connect_local_mcp`|POST|Connect Local Mcp|Add a local MCP server (a command Kiln starts) to the project as a tool server.|post_api_projects_project_id_connect_local_mcp.md|
|`/api/projects/{project_id}/edit_local_mcp/{tool_server_id}`|PATCH|Edit Local Mcp|Change a local MCP tool server's name, description, command, arguments or environment.|patch_api_projects_project_id_edit_local_mcp_tool_server_id.md|
|`/api/projects/{project_id}/tool_servers/{tool_server_id}/archive`|POST|Archive Tool Server|Archive or unarchive a tool server. An archived server is hidden from tool pickers.|post_api_projects_project_id_tool_servers_tool_server_id_archive.md|
|`/api/projects/{project_id}/kiln_task_tool`|POST|Add Kiln Task Tool|Offer a Kiln task as a tool that other tasks' agents can call, through one of its run configs.|post_api_projects_project_id_kiln_task_tool.md|
|`/api/projects/{project_id}/edit_kiln_task_tool/{tool_server_id}`|PATCH|Edit Kiln Task Tool|Change a Kiln task tool's name, description, task or run config.|patch_api_projects_project_id_edit_kiln_task_tool_tool_server_id.md|
|`/api/demo_tools`|GET|Get Demo Tools|Check whether Kiln's demo math tools are turned on.|get_api_demo_tools.md|
|`/api/demo_tools`|POST|Set Demo Tools|Turn Kiln's demo math tools on or off.|post_api_demo_tools.md|
|`/api/projects/{project_id}/search_tools`|GET|Get Search Tools|List the project's search tools: one per RAG config, with its tool name and description.|get_api_projects_project_id_search_tools.md|
|`/api/projects/{project_id}/tasks/{task_id}/tools/{tool_id}/definition`|GET|Get Tool Definition|Get the actual OpenAI tool definition for a specific tool ID.  This returns the real function name a...|get_api_projects_project_id_tasks_task_id_tools_tool_id_definition.md|
