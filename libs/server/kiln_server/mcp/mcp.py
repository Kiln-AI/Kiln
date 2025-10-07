"""CLI entry point for the Kiln MCP server."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Sequence

from kiln_ai.datamodel.external_tool_server import ToolServerType
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.tool_id import build_kiln_task_tool_id, build_rag_tool_id

from .mcp_server_tool_utils import prepare_tool_contexts
from .runtime import Transport, create_fastmcp_server, run_transport
from .tool_selection import collect_project_tools

logger = logging.getLogger(__name__)


def _parse_tool_ids(raw: str | None) -> list[str] | None:
    if raw is None or raw.strip() == "":
        return None
    return [token.strip() for token in raw.split(",") if token.strip()]


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Kiln MCP server for a project."
    )
    parser.add_argument("project", type=Path, help="Path to the project.kiln file")
    parser.add_argument(
        "--tool-ids",
        dest="tool_ids",
        default=None,
        help="Comma-separated list of tool IDs to expose. Defaults to all project tools. Use the --list-tools flag to list all available tool IDs for a project.",
    )
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="List all available tool IDs.",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="Transport mechanism for the MCP server.",
    )
    parser.add_argument(
        "--host", default="127.0.0.1", help="Host for network transports."
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="Port for network transports."
    )
    parser.add_argument(
        "--mount-path",
        default=None,
        help="Optional mount path for SSE or streamable HTTP transports.",
    )
    parser.add_argument(
        "--log-level",
        default="info",
        help="Log level for the server when using network transports.",
    )
    return parser


async def _async_main(
    *,
    project_path: Path,
    tool_ids: Sequence[str] | None,
    transport: Transport,
    host: str,
    port: int,
    mount_path: str | None,
    log_level: str,
) -> None:
    project = Project.load_from_file(project_path)
    project_name = project.name

    tool_resolutions = collect_project_tools(project, tool_ids)
    if not tool_resolutions:
        raise ValueError("No eligible tools found in the project.")

    tool_contexts = await prepare_tool_contexts(tool_resolutions)
    server = create_fastmcp_server(
        tool_contexts,
        project_name=project_name,
        host=host,
        port=port,
        log_level=log_level,
        transport=transport,
        mount_path=mount_path,
    )

    await run_transport(server, transport, mount_path)


def _list_tools(project_path: Path) -> None:
    project = Project.load_from_file(project_path)

    stdout = sys.stdout
    stdout.write("Listing all available tools\n\n")
    stdout.write("Search Tools / RAG (ID -- name -- description):\n")
    has_rag_tools = False
    for rag_config in project.rag_configs(readonly=True):
        stdout.write(
            f"{build_rag_tool_id(rag_config.id)} -- {rag_config.tool_name} -- {rag_config.tool_description}\n"
        )
        has_rag_tools = True
    if not has_rag_tools:
        stdout.write("No RAG tools found.\n")

    stdout.write("\nKiln Task Tools (ID -- name  -- description):\n")
    has_kiln_task_tools = False
    for tool_server in project.external_tool_servers(readonly=True):
        if (
            tool_server.type == ToolServerType.kiln_task
            and not tool_server.properties.get("is_archived", False)
        ):
            stdout.write(
                f"{build_kiln_task_tool_id(tool_server.id)} -- {tool_server.name} -- {tool_server.description or 'No description'}\n"
            )
            has_kiln_task_tools = True
    if not has_kiln_task_tools:
        stdout.write("No Kiln task tools found.\n")


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    tool_ids = _parse_tool_ids(args.tool_ids)

    if not args.project.exists():
        parser.error(f"Project file not found: {args.project}")
    if not args.project.is_file():
        parser.error(f"Project file parameter is not a file: {args.project}")

    if args.list_tools:
        _list_tools(args.project)
        return

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))

    asyncio.run(
        _async_main(
            project_path=args.project,
            tool_ids=tool_ids,
            transport=args.transport,
            host=args.host,
            port=args.port,
            mount_path=args.mount_path,
            log_level=args.log_level,
        )
    )


if __name__ == "__main__":
    main()
