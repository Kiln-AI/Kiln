"""The tools a run config lists, read without running it.

An OpenEnv tool resolves through the registry only while an episode of its server is
active. Code that only needs to describe a run config's tools (its names, descriptions
and schemas) reads them from the server's tool list instead, which needs no episode.
"""

from __future__ import annotations

from collections.abc import Iterable

from kiln_ai.datamodel.openenv import OpenEnvServer, OpenEnvTool
from kiln_ai.datamodel.task import Task
from kiln_ai.datamodel.tool_id import (
    OPENENV_TOOL_ID_PREFIX,
    SKILL_TOOL_ID_PREFIX,
    openenv_and_tool_name_from_id,
)
from kiln_ai.openenv.session_manager import OpenEnvSessionManager
from kiln_ai.tools.base_tool import ToolCallDefinition
from kiln_ai.tools.openenv_tool import openenv_toolcall_definition
from kiln_ai.tools.tool_registry import tool_from_id


async def served_openenv_tools(
    task: Task,
    tool_ids: Iterable[str],
    session_manager: OpenEnvSessionManager,
) -> dict[str, OpenEnvTool]:
    """Each OpenEnv tool id in `tool_ids`, mapped to the tool its server lists under that
    name. Other ids are ignored. Each server's tools are listed once, without an episode.

    Raises ValueError when an id names a server the task's project doesn't have, or a
    tool its server doesn't serve. Raises OpenEnvError when a server can't be reached."""
    names_by_server: dict[str, list[tuple[str, str]]] = {}
    for tool_id in tool_ids:
        if not tool_id.startswith(OPENENV_TOOL_ID_PREFIX):
            continue
        openenv_server_id, tool_name = openenv_and_tool_name_from_id(tool_id)
        names_by_server.setdefault(openenv_server_id, []).append((tool_id, tool_name))
    if not names_by_server:
        return {}

    project = task.parent_project()
    if project is None:
        raise ValueError("The task has no parent project.")
    servers = OpenEnvServer.from_ids_and_parent_path(
        set(names_by_server), project.path, readonly=True
    )
    served: dict[str, OpenEnvTool] = {}
    for openenv_server_id, wanted in names_by_server.items():
        server = servers.get(openenv_server_id)
        if server is None:
            raise ValueError(f"OpenEnv server {openenv_server_id} wasn't found.")
        tools = {tool.name: tool for tool in await session_manager.list_tools(server)}
        for tool_id, tool_name in wanted:
            tool = tools.get(tool_name)
            if tool is None:
                raise ValueError(
                    f"OpenEnv server '{server.name}' does not serve a tool named "
                    f"'{tool_name}' (for {tool_id}); it serves {sorted(tools)}"
                )
            served[tool_id] = tool
    return served


async def tool_definitions_without_episode(
    task: Task,
    tool_ids: Iterable[str],
    session_manager: OpenEnvSessionManager,
) -> list[ToolCallDefinition]:
    """The function definitions a model running with `tool_ids` would see, in order.

    Skills are left out: the adapter presents them its own way. MCP tools are read from
    their servers, so callers wrap this in `mcp_session_scope` to share one session per
    server. Raises as `served_openenv_tools` does, and as `tool_from_id` does for any
    other tool."""
    ids = [
        tool_id for tool_id in tool_ids if not tool_id.startswith(SKILL_TOOL_ID_PREFIX)
    ]
    openenv_tools = await served_openenv_tools(task, ids, session_manager)
    definitions: list[ToolCallDefinition] = []
    for tool_id in ids:
        openenv_tool = openenv_tools.get(tool_id)
        if openenv_tool is not None:
            definitions.append(openenv_toolcall_definition(openenv_tool))
        else:
            definitions.append(await tool_from_id(tool_id, task).toolcall_definition())
    return definitions
