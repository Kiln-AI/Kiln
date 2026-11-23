# Code Tools API

Create, test, and manage user-authored Python code tools.

|Endpoint|Method|Name|Description|Details File|
|-|-|-|-|-|
|`/api/projects/{project_id}/code_tools`|GET|List Code Tools|List the project's code tools, archived ones last.|get_api_projects_project_id_code_tools.md|
|`/api/projects/{project_id}/code_tools`|POST|Create Code Tool|Create a code tool: Python code the project's agents can call as a tool. Until the project's code is...|post_api_projects_project_id_code_tools.md|
|`/api/projects/{project_id}/test_code_tool`|POST|Test Code Tool|Run a code tool's code once on test arguments, without saving the tool. Returns its output or error,...|post_api_projects_project_id_test_code_tool.md|
|`/api/projects/{project_id}/code_tools/{code_tool_id}`|GET|Get Code Tool|Get one code tool, with its code and parameter schema.|get_api_projects_project_id_code_tools_code_tool_id.md|
|`/api/projects/{project_id}/code_tools/{code_tool_id}`|PATCH|Update Code Tool Metadata|Change a code tool's name or description. Its code and tool interface can't be edited: create a new ...|patch_api_projects_project_id_code_tools_code_tool_id.md|
|`/api/projects/{project_id}/code_tools/{code_tool_id}`|DELETE|Delete Code Tool|Delete a code tool from the project.|delete_api_projects_project_id_code_tools_code_tool_id.md|
|`/api/projects/{project_id}/code_tools/{code_tool_id}/archive`|POST|Archive/Unarchive Code Tool|Archive or unarchive a code tool.|post_api_projects_project_id_code_tools_code_tool_id_archive.md|
