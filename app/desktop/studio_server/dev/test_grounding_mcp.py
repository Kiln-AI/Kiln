"""The grounding MCP server against the test OpenEnv server in `kiln_ai.openenv.testing`."""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from kiln_ai.eval_grounding.session import (
    NO_EPISODE_MESSAGE,
    GroundingLimits,
    GroundingSession,
)
from kiln_ai.openenv.session_manager import (
    OpenEnvSessionManager,
    OpenEnvTransientError,
)
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import TextContent

from app.desktop.studio_server.dev import grounding_mcp
from app.desktop.studio_server.dev.grounding_mcp import (
    GroundingMcpServer,
    GroundingRunLog,
    GroundingSetupError,
    load_openenv_server,
)


@pytest.fixture
async def session_manager():
    manager = OpenEnvSessionManager()
    try:
        yield manager
    finally:
        await manager.shutdown()


@pytest.fixture
async def make_mcp(openenv_server, session_manager, tmp_path):
    sessions: list[GroundingSession] = []

    async def make(limits: GroundingLimits = GroundingLimits()):
        tools = await session_manager.list_tools(openenv_server)
        session = GroundingSession(
            openenv_server,
            session_manager,
            tools,
            limits=limits,
            transient_retry_delays_s=(0, 0),
        )
        sessions.append(session)
        return GroundingMcpServer(session, tmp_path / "run_log.json")

    yield make
    for session in sessions:
        await session.close()


def read_log(tmp_path: Path) -> GroundingRunLog:
    return GroundingRunLog.model_validate_json(
        (tmp_path / "run_log.json").read_text(encoding="utf-8")
    )


def text_of(result) -> str:
    content = result.content[0]
    assert isinstance(content, TextContent)
    return content.text


async def test_lists_the_session_tools_with_their_schemas(make_mcp):
    mcp_server = await make_mcp()
    async with create_connected_server_and_client_session(mcp_server.server) as client:
        tools = (await client.list_tools()).tools

    by_name = {tool.name: tool for tool in tools}
    assert list(by_name)[:2] == ["start_episode", "read_state"]
    assert {"append_note", "read_notes", "explode"} <= set(by_name)
    assert by_name["append_note"].inputSchema["properties"] == {
        "note": {"type": "string"}
    }
    assert by_name["start_episode"].inputSchema["required"] == ["reset_kwargs"]


async def test_a_server_tool_reaches_the_environment(make_mcp, tmp_path):
    mcp_server = await make_mcp()
    async with create_connected_server_and_client_session(mcp_server.server) as client:
        refused = await client.call_tool("append_note", {"note": "early"})
        started = await client.call_tool(
            "start_episode", {"reset_kwargs": {"fixture_id": "alpha"}}
        )
        noted = await client.call_tool("append_note", {"note": "hello"})
        notes = await client.call_tool("read_notes", {})

    assert refused.isError
    assert text_of(refused) == NO_EPISODE_MESSAGE
    assert not started.isError
    assert json.loads(text_of(started))["reset_metadata"]["fixture_id"] == "alpha"
    assert text_of(noted) == "noted:1"
    assert json.loads(text_of(notes)) == ["hello"]

    log = read_log(tmp_path)
    assert [call.tool for call in log.call_log] == [
        "append_note",
        "start_episode",
        "append_note",
        "read_notes",
    ]
    assert log.last_reset is not None
    assert log.last_reset.reset_kwargs == {"fixture_id": "alpha"}
    assert log.stopped is None


async def test_a_rejected_reset_and_a_tool_error_come_back_as_errors(make_mcp):
    mcp_server = await make_mcp()
    async with create_connected_server_and_client_session(mcp_server.server) as client:
        rejected = await client.call_tool(
            "start_episode", {"reset_kwargs": {"fail_reset": True}}
        )
        await client.call_tool("start_episode", {"reset_kwargs": {}})
        unknown = await client.call_tool("no_such_tool", {})

    assert rejected.isError
    assert "rejected these reset arguments" in text_of(rejected)
    assert unknown.isError
    assert text_of(unknown) == "There is no tool named no_such_tool."


async def test_the_hard_stop_after_a_limit_is_logged_and_refuses_later_calls(
    make_mcp, tmp_path
):
    mcp_server = await make_mcp(
        GroundingLimits(max_tool_calls=1, max_resets=5, calls_after_limit=1)
    )
    async with create_connected_server_and_client_session(mcp_server.server) as client:
        await client.call_tool("start_episode", {"reset_kwargs": {}})
        await client.call_tool("read_notes", {})
        told_to_stop = await client.call_tool("read_notes", {})
        stopped = await client.call_tool("read_notes", {})
        after_stop = await client.call_tool("start_episode", {"reset_kwargs": {}})

    assert "return your result now" in text_of(told_to_stop)
    assert stopped.isError
    assert "stopped" in text_of(stopped)
    assert after_stop.isError
    assert "stopped" in text_of(after_stop)
    log = read_log(tmp_path)
    assert log.stopped == "limit"
    assert log.stop_detail is not None
    assert "1 tool calls" in log.stop_detail


async def test_an_environment_error_stops_the_session(
    make_mcp, session_manager, tmp_path
):
    mcp_server = await make_mcp()
    with patch.object(
        session_manager,
        "start_episode",
        AsyncMock(side_effect=OpenEnvTransientError("server went away")),
    ):
        async with create_connected_server_and_client_session(
            mcp_server.server
        ) as client:
            result = await client.call_tool("start_episode", {"reset_kwargs": {}})

    assert result.isError
    log = read_log(tmp_path)
    assert log.stopped == "error"
    assert log.stop_detail is not None
    assert "server went away" in log.stop_detail


def test_load_openenv_server(project, openenv_server, tmp_path):
    assert load_openenv_server(project.path, openenv_server.id).id == openenv_server.id
    with pytest.raises(GroundingSetupError, match="No project file"):
        load_openenv_server(tmp_path / "missing.kiln", "x")
    with pytest.raises(GroundingSetupError, match="no OpenEnv server with id nope"):
        load_openenv_server(project.path, "nope")


async def test_runs_by_file_path_and_releases_the_episode_on_exit(
    project, openenv_server, tmp_path
):
    log_path = tmp_path / "subprocess_log.json"
    params = StdioServerParameters(
        command=sys.executable,
        args=[
            str(grounding_mcp.script_path()),
            "--project",
            str(project.path),
            "--openenv-server-id",
            str(openenv_server.id),
            "--log-out",
            str(log_path),
        ],
        cwd=str(tmp_path),
    )
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as client:
            await client.initialize()
            await client.call_tool(
                "start_episode", {"reset_kwargs": {"fixture_id": "beta"}}
            )
            noted = await client.call_tool("append_note", {"note": "x"})
            assert text_of(noted) == "noted:1"

    log = GroundingRunLog.model_validate_json(log_path.read_text(encoding="utf-8"))
    assert log.last_reset is not None
    assert log.last_reset.reset_kwargs == {"fixture_id": "beta"}
    assert [call.tool for call in log.call_log] == ["start_episode", "append_note"]

    # The server holds one session, so a new episode starts only if the subprocess
    # released its own on exit.
    manager = OpenEnvSessionManager()
    try:
        episode = await manager.start_episode(openenv_server, {})
        await manager.release(episode)
    finally:
        await manager.shutdown()
