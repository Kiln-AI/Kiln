"""A stdio MCP server that serves one grounding session's tools, for `claude -p`.

`ground_cases ground --engine claude` starts one per case through `claude`'s MCP config.
It serves `start_episode`, `read_state` and one tool per OpenEnv server tool, with the
session's limits, and keeps a run log (the call log, the last reset, and whether the
session stopped) in a JSON file that `ground` reads when the case ends.

It imports only `kiln_ai` and `mcp`, so `claude` can start it by file path from any
working directory:

    python grounding_mcp.py --project <project.kiln> --openenv-server-id <id> --log-out <file>
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from kiln_ai.datamodel.openenv import OpenEnvReset, OpenEnvServer
from kiln_ai.datamodel.project import Project
from kiln_ai.eval_grounding.models import LoggedCall
from kiln_ai.eval_grounding.session import GroundingLimitReached, GroundingSession
from kiln_ai.openenv.session_manager import OpenEnvSessionManager
from kiln_ai.tools.base_tool import KilnToolInterface, ToolCallError
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from pydantic import BaseModel, Field

MCP_SERVER_NAME = "grounding"
"""The server's name in `claude`'s MCP config; its tools are `mcp__grounding__<tool>`."""

STOPPED_MESSAGE = (
    "The grounding session has stopped: {detail} Stop calling tools and return your "
    "result now."
)


def script_path() -> Path:
    """This file, for an MCP config that starts the server by path."""
    return Path(__file__).resolve()


class GroundingSetupError(Exception):
    """The project or OpenEnv server named on the command line can't be loaded."""


class GroundingRunLog(BaseModel):
    """What one case's grounding session did, as `ground` reads it after the case."""

    call_log: list[LoggedCall] = Field(default_factory=list)
    last_reset: OpenEnvReset | None = Field(
        default=None,
        description="The reset of the last episode that started: the saved case's reset.",
    )
    stopped: Literal["limit", "error"] | None = Field(
        default=None,
        description="Why the session stopped serving tools. `limit`: the agent kept calling "
        "tools past a limit. `error`: a failure that is not the case's fault, such as an "
        "unreachable server.",
    )
    stop_detail: str | None = None


def load_openenv_server(project_path: Path, openenv_server_id: str) -> OpenEnvServer:
    """The saved OpenEnv server with this id in the project at `project_path`."""
    if not project_path.is_file():
        raise GroundingSetupError(f"No project file at {project_path}.")
    project = Project.load_from_file(project_path)
    server = OpenEnvServer.from_id_and_parent_path(openenv_server_id, project.path)
    if server is None:
        raise GroundingSetupError(
            f"Project {project.name} has no OpenEnv server with id {openenv_server_id}."
        )
    return server


class GroundingMcpServer:
    """Serves a `GroundingSession`'s tools over MCP and keeps its run log on disk.

    The log file is rewritten after every call, so it is current even when `claude` is
    killed before this process exits."""

    def __init__(self, session: GroundingSession, log_path: Path) -> None:
        self._session = session
        self._log_path = log_path
        self._tools_by_name: dict[str, KilnToolInterface] = {}
        self._stopped: Literal["limit", "error"] | None = None
        self._stop_detail: str | None = None
        self._write_lock = asyncio.Lock()
        self.server: Server[Any] = Server(MCP_SERVER_NAME)
        self.server.list_tools()(self._list_tools)
        self.server.call_tool(validate_input=False)(self._call_tool)

    def run_log(self) -> GroundingRunLog:
        return GroundingRunLog(
            call_log=self._session.call_log,
            last_reset=self._session.last_reset,
            stopped=self._stopped,
            stop_detail=self._stop_detail,
        )

    async def write_log(self) -> None:
        text = self.run_log().model_dump_json(indent=2)
        async with self._write_lock:
            await asyncio.to_thread(_write_atomically, self._log_path, text)

    async def _list_tools(self) -> list[types.Tool]:
        tools: list[types.Tool] = []
        for tool in self._session.tools():
            definition = (await tool.toolcall_definition())["function"]
            self._tools_by_name[definition["name"]] = tool
            tools.append(
                types.Tool(
                    name=definition["name"],
                    description=definition["description"],
                    inputSchema=definition["parameters"],
                )
            )
        return tools

    async def _call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> types.CallToolResult:
        try:
            return await self._run_tool(name, arguments)
        finally:
            await self.write_log()

    async def _run_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> types.CallToolResult:
        if self._stopped is not None:
            return _error_result(STOPPED_MESSAGE.format(detail=self._stop_detail))
        if not self._tools_by_name:
            await self._list_tools()
        tool = self._tools_by_name.get(name)
        if tool is None:
            return _error_result(f"There is no tool named {name}.")
        try:
            result = await tool.run(None, **arguments)
        except ToolCallError as e:
            return _error_result(str(e))
        except GroundingLimitReached as e:
            return self._stop("limit", str(e))
        # Anything else (an unreachable server, a dropped session) is not the case's
        # fault: `ground` fails the case instead of reading the agent's answer.
        except Exception as e:
            return self._stop("error", f"{type(e).__name__}: {e}")
        if result.is_error:
            return _error_result(result.output)
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=result.output)]
        )

    def _stop(
        self, reason: Literal["limit", "error"], detail: str
    ) -> types.CallToolResult:
        self._stopped = reason
        self._stop_detail = detail
        return _error_result(STOPPED_MESSAGE.format(detail=detail))


async def serve(project_path: Path, openenv_server_id: str, log_path: Path) -> None:
    """Serve one grounding session over stdio until the client disconnects, then release
    its episode and write the final run log."""
    openenv_server = load_openenv_server(project_path, openenv_server_id)
    session_manager = OpenEnvSessionManager()
    try:
        server_tools = await session_manager.list_tools(openenv_server)
        session = GroundingSession(openenv_server, session_manager, server_tools)
        mcp_server = GroundingMcpServer(session, log_path)
        await mcp_server.write_log()
        try:
            async with stdio_server() as (read_stream, write_stream):
                await mcp_server.server.run(
                    read_stream,
                    write_stream,
                    mcp_server.server.create_initialization_options(),
                )
        finally:
            await session.close()
            await mcp_server.write_log()
    finally:
        await session_manager.shutdown()


def _error_result(message: str) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=message)], isError=True
    )


def _write_atomically(path: Path, text: str) -> None:
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Serve one grounding session's tools over stdio MCP."
    )
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--openenv-server-id", required=True)
    parser.add_argument(
        "--log-out",
        type=Path,
        required=True,
        help="JSON file for the run log: the call log, the last reset, and any stop.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_argument_parser().parse_args(argv)
    asyncio.run(serve(args.project, args.openenv_server_id, args.log_out))


if __name__ == "__main__":
    main()
