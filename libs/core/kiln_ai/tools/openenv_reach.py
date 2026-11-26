"""Which OpenEnv environments a list of tools can reach.

A run reaches an environment through its own tools, through the allowlists of code
tools it lists (nested to any depth), and through the run configs of Kiln task tools
it lists, whose sub-runs share the parent's session. Every environment tool id names
its environment, so the walk reads only ids from disk and never runs code or contacts
a server.
"""

from collections import deque
from dataclasses import dataclass

from kiln_ai.datamodel.code_tool import CodeTool
from kiln_ai.datamodel.external_tool_server import ExternalToolServer, ToolServerType
from kiln_ai.datamodel.openenv import OpenEnvServer
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.run_config import as_kiln_agent_run_config
from kiln_ai.datamodel.task import Task
from kiln_ai.datamodel.tool_id import (
    CODE_TOOL_ID_PREFIX,
    KILN_TASK_TOOL_ID_PREFIX,
    OPENENV_TOOL_ID_PREFIX,
    code_tool_id_from_tool_id,
    kiln_task_server_id_from_tool_id,
    openenv_and_tool_name_from_id,
)


@dataclass(frozen=True)
class OpenEnvReach:
    openenv_server_id: str
    via: str
    """How the outermost tool in the list reaches it: "directly", "code tool <name>"
    or "Kiln task tool <name>"."""


class OpenEnvReachError(ValueError):
    """The tools reach more than one environment, and a run can only use one.

    `message` is the short text the run page shows. `str(error)` is `detail`, which
    also says how each environment is reached."""

    def __init__(self, openenv_servers: list[tuple[str, list[str]]]) -> None:
        """`openenv_servers` is each environment's name with the ways it's reached."""
        names = [name for name, _ in openenv_servers]
        self.message = (
            f"Your tools use more than one OpenEnv server ({', '.join(names)}). "
            "A run can only use one."
        )
        reached = ", ".join(
            f"{name} ({', '.join(vias)})" for name, vias in openenv_servers
        )
        self.detail = f"{self.message} Reached by: {reached}."
        super().__init__(self.detail)


def openenv_reach(project: Project, tool_ids: list[str]) -> list[OpenEnvReach]:
    """Every environment the tools reach, in the order first reached, once per
    distinct way it's reached. Code tools, tool servers, tasks and run configs that
    can't be found are skipped: other validation reports those."""
    walk = _ReachWalk(project)
    queue: deque[tuple[str, str | None]] = deque((tid, None) for tid in tool_ids)
    # Keyed with the outermost tool too, so a tool listed both directly and inside
    # another still reports both ways it's reached. Still finite: one pass per pair.
    visited: set[tuple[str, str | None]] = set()
    reaches: list[OpenEnvReach] = []

    while queue:
        tool_id, via = queue.popleft()
        if tool_id.startswith(OPENENV_TOOL_ID_PREFIX):
            openenv_server_id = _openenv_server_id_of(tool_id)
            if openenv_server_id is not None:
                reach = OpenEnvReach(openenv_server_id, via or "directly")
                if reach not in reaches:
                    reaches.append(reach)
            continue
        if (tool_id, via) in visited:
            continue
        visited.add((tool_id, via))
        expansion = walk.expand(tool_id)
        if expansion is not None:
            outer_via, child_ids = expansion
            queue.extend((child, via or outer_via) for child in child_ids)

    return reaches


def single_openenv_server_id(project: Project, tool_ids: list[str]) -> str | None:
    """The one environment the tools reach, or None if they reach none.

    Raises OpenEnvReachError naming each environment, and how it's reached, if
    there's more than one."""
    reaches = openenv_reach(project, tool_ids)
    openenv_server_ids = list(dict.fromkeys(r.openenv_server_id for r in reaches))
    if not openenv_server_ids:
        return None
    if len(openenv_server_ids) == 1:
        return openenv_server_ids[0]

    found = OpenEnvServer.from_ids_and_parent_path(
        set(openenv_server_ids), project.path, readonly=True
    )
    raise OpenEnvReachError(
        [
            (
                found[openenv_server_id].name
                if openenv_server_id in found
                else openenv_server_id,
                [r.via for r in reaches if r.openenv_server_id == openenv_server_id],
            )
            for openenv_server_id in openenv_server_ids
        ]
    )


def _openenv_server_id_of(tool_id: str) -> str | None:
    try:
        return openenv_and_tool_name_from_id(tool_id)[0]
    except ValueError:
        return None


class _ReachWalk:
    """Resolves one tool id to what it reaches. Each tool, and the project's tool
    servers, are read from disk at most once per walk."""

    def __init__(self, project: Project) -> None:
        self._project = project
        self._servers: dict[str, ExternalToolServer] | None = None
        self._expanded: dict[str, tuple[str, list[str]] | None] = {}

    def expand(self, tool_id: str) -> tuple[str, list[str]] | None:
        """`(via, child tool ids)` for a tool that can reach further tools."""
        if tool_id not in self._expanded:
            if tool_id.startswith(CODE_TOOL_ID_PREFIX):
                self._expanded[tool_id] = self._code_tool(tool_id)
            elif tool_id.startswith(KILN_TASK_TOOL_ID_PREFIX):
                self._expanded[tool_id] = self._kiln_task_tool(tool_id)
            else:
                self._expanded[tool_id] = None
        return self._expanded[tool_id]

    def _code_tool(self, tool_id: str) -> tuple[str, list[str]] | None:
        try:
            code_tool = CodeTool.from_id_and_parent_path(
                code_tool_id_from_tool_id(tool_id), self._project.path
            )
        except ValueError:
            return None
        if code_tool is None:
            return None
        return f"code tool {code_tool.name}", list(code_tool.tool_allowlist)

    def _kiln_task_tool(self, tool_id: str) -> tuple[str, list[str]] | None:
        try:
            server_id = kiln_task_server_id_from_tool_id(tool_id)
        except ValueError:
            return None
        server = self._server(server_id)
        if server is None or server.type != ToolServerType.kiln_task:
            return None
        name = server.properties.get("name") or server.name
        task = Task.from_id_and_parent_path(
            str(server.properties.get("task_id", "")), self._project.path
        )
        if task is None:
            return None
        run_config_id = server.properties.get("run_config_id")
        run_config = next(
            (rc for rc in task.run_configs(readonly=True) if rc.id == run_config_id),
            None,
        )
        if run_config is None or run_config.run_config_properties.type != "kiln_agent":
            return None
        tools_config = as_kiln_agent_run_config(
            run_config.run_config_properties
        ).tools_config
        tools = list(tools_config.tools) if tools_config and tools_config.tools else []
        return f"Kiln task tool {name}", tools

    def _server(self, server_id: str) -> ExternalToolServer | None:
        if self._servers is None:
            self._servers = {
                s.id: s
                for s in self._project.external_tool_servers(readonly=True)
                if s.id is not None
            }
        return self._servers.get(server_id)
