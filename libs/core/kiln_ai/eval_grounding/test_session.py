"""GroundingSession against the test OpenEnv server in `kiln_ai.openenv.testing`."""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from kiln_ai.datamodel.openenv import OpenEnvServer, OpenEnvTool
from kiln_ai.datamodel.project import Project
from kiln_ai.eval_grounding.session import (
    CLOSED_EPISODE_MESSAGE,
    NO_EPISODE_MESSAGE,
    GroundingLimitReached,
    GroundingLimits,
    GroundingSession,
)
from kiln_ai.openenv.session_manager import (
    OpenEnvCapacityError,
    OpenEnvRejectedError,
    OpenEnvSessionLostError,
    OpenEnvSessionManager,
    OpenEnvTransientError,
)
from kiln_ai.openenv.testing import serve_in_thread
from kiln_ai.tools.base_tool import ToolCallError


@pytest.fixture
def project(tmp_path):
    p = Project(name="proj", path=tmp_path / "proj" / "project.kiln")
    p.path.parent.mkdir(parents=True)
    p.save_to_file()
    return p


@pytest.fixture
def one_session_url():
    """A server that holds one session, so a leaked episode blocks the next reset."""
    with serve_in_thread(max_sessions=1) as base_url:
        yield base_url


@pytest.fixture
def openenv_server(project, one_session_url):
    server = OpenEnvServer(name="counter", parent=project, url=one_session_url)
    server.save_to_file()
    return server


@pytest.fixture
async def session_manager():
    manager = OpenEnvSessionManager()
    try:
        yield manager
    finally:
        await manager.shutdown()


@pytest.fixture
async def make_session(openenv_server, session_manager):
    sessions: list[GroundingSession] = []

    async def make(**kwargs) -> GroundingSession:
        tools = await session_manager.list_tools(openenv_server)
        session = GroundingSession(
            openenv_server,
            session_manager,
            kwargs.pop("server_tools", tools),
            transient_retry_delays_s=kwargs.pop("transient_retry_delays_s", (0, 0)),
            **kwargs,
        )
        sessions.append(session)
        return session

    yield make
    for session in sessions:
        await session.close()


async def call(session: GroundingSession, tool_name: str, **kwargs):
    for tool in session.tools():
        if await tool.name() == tool_name:
            return await tool.run(None, **kwargs)
    raise AssertionError(f"no tool {tool_name}")


async def assert_server_is_free(openenv_server):
    """The one-session server accepts a new episode only if no episode was left open."""
    manager = OpenEnvSessionManager()
    try:
        episode = await manager.start_episode(openenv_server, {})
        await manager.release(episode)
    finally:
        await manager.shutdown()


class TestTools:
    async def test_session_tools_then_server_tools(self, make_session):
        session = await make_session()
        definitions = [await t.toolcall_definition() for t in session.tools()]
        assert [d["function"]["name"] for d in definitions] == [
            "start_episode",
            "read_state",
            "append_note",
            "read_notes",
            "explode",
            "sleep",
        ]
        assert definitions[0]["function"]["parameters"]["required"] == ["reset_kwargs"]
        assert definitions[2]["function"]["description"] == (
            "Append a note to the episode's notebook."
        )
        assert definitions[2]["function"]["parameters"]["required"] == ["note"]
        assert [await t.id() for t in session.tools()][:2] == [
            "kiln_unmanaged::grounding_start_episode",
            "kiln_unmanaged::grounding_read_state",
        ]

    async def test_colliding_server_tool_is_renamed(self, make_session):
        session = await make_session(
            server_tools=[
                OpenEnvTool(name="start_episode", description="server's own"),
                OpenEnvTool(name="env_start_episode", description="another"),
                OpenEnvTool(name="read_state", input_schema={"type": "object"}),
            ]
        )
        definitions = [await t.toolcall_definition() for t in session.tools()]
        assert [d["function"]["name"] for d in definitions] == [
            "start_episode",
            "read_state",
            "env_start_episode",
            "env_env_start_episode",
            "env_read_state",
        ]
        assert definitions[4]["function"]["parameters"] == {
            "type": "object",
            "properties": {},
        }

    async def test_renamed_tool_calls_the_server_name(
        self, make_session, session_manager
    ):
        session = await make_session(
            server_tools=[OpenEnvTool(name="read_state", description="notes")]
        )
        await call(session, "start_episode", reset_kwargs={})
        with patch.object(
            session_manager, "call_tool", wraps=session_manager.call_tool
        ) as spy:
            await call(session, "env_read_state")
        assert spy.call_args.args[1] == "read_state"


class TestEpisodes:
    @pytest.mark.parametrize("tool_name", ["read_notes", "read_state"])
    async def test_calls_before_start_episode_are_refused(
        self, make_session, tool_name
    ):
        session = await make_session()
        with pytest.raises(ToolCallError, match=NO_EPISODE_MESSAGE):
            await call(session, tool_name)

    async def test_start_episode_reports_the_reset(self, make_session, openenv_server):
        session = await make_session()
        result = await call(session, "start_episode", reset_kwargs={"fixture_id": "a"})
        assert json.loads(result.output) == {
            "reset_metadata": {"fixture_id": "a", "frozen_time": None},
            "resets_left": 9,
            "tool_calls_left": 40,
        }
        assert session.last_reset is not None
        assert session.last_reset.openenv_server_id == openenv_server.id
        assert session.last_reset.reset_kwargs == {"fixture_id": "a"}

    async def test_start_episode_releases_the_previous_episode(self, make_session):
        session = await make_session()
        await call(session, "start_episode", reset_kwargs={"fixture_id": "a"})
        await call(session, "append_note", note="kept in a")
        # The server holds one session: this reset only works if the first was released.
        await call(session, "start_episode", reset_kwargs={"fixture_id": "b"})
        notes = await call(session, "read_notes")
        assert notes.output == "[]"
        assert session.last_reset is not None
        assert session.last_reset.reset_kwargs == {"fixture_id": "b"}

    async def test_rejected_reset_is_a_tool_error(self, make_session):
        session = await make_session()
        await call(session, "start_episode", reset_kwargs={"fixture_id": "a"})
        with pytest.raises(
            ToolCallError,
            match="The server rejected these reset arguments: reset refused",
        ):
            await call(session, "start_episode", reset_kwargs={"fail_reset": True})
        assert session.last_reset is not None
        assert session.last_reset.reset_kwargs == {"fixture_id": "a"}
        with pytest.raises(ToolCallError, match=NO_EPISODE_MESSAGE):
            await call(session, "read_notes")

    async def test_non_object_reset_kwargs_refused_without_spending_a_reset(
        self, make_session
    ):
        session = await make_session(limits=GroundingLimits(max_resets=1))
        with pytest.raises(ToolCallError, match="must be a JSON object"):
            await call(session, "start_episode", reset_kwargs=["fixture"])
        result = await call(session, "start_episode", reset_kwargs={})
        assert json.loads(result.output)["resets_left"] == 0
        assert json.loads(result.output)["tool_calls_left"] == 39

    async def test_server_tool_results_and_errors(self, make_session):
        session = await make_session()
        await call(session, "start_episode", reset_kwargs={})
        noted = await call(session, "append_note", note="hello")
        assert noted.output == "noted:1" and not noted.is_error
        boom = await call(session, "explode")
        assert boom.is_error
        assert json.loads(boom.output) == {
            "error": {"code": "execution_error", "message": "boom", "details": None}
        }

    async def test_read_state(self, make_session):
        session = await make_session()
        await call(session, "start_episode", reset_kwargs={"fixture_id": "f"})
        await call(session, "append_note", note="hello")
        state = json.loads((await call(session, "read_state")).output)
        assert state["notes"] == ["hello"]
        assert state["fixture_id"] == "f"

    async def test_close_releases_and_is_idempotent(self, make_session, openenv_server):
        session = await make_session()
        await call(session, "start_episode", reset_kwargs={})
        await session.close()
        await session.close()
        await assert_server_is_free(openenv_server)
        with pytest.raises(ToolCallError, match=NO_EPISODE_MESSAGE):
            await call(session, "read_notes")

    async def test_concurrent_calls_run_one_at_a_time(
        self, make_session, openenv_server
    ):
        session = await make_session()
        await call(session, "start_episode", reset_kwargs={"fixture_id": "a"})
        results = await asyncio.gather(
            call(session, "sleep", seconds=0.1),
            call(session, "start_episode", reset_kwargs={"fixture_id": "b"}),
            call(session, "read_notes"),
        )
        assert [r.is_error for r in results] == [False, False, False]
        await session.close()
        await assert_server_is_free(openenv_server)


class TestFailures:
    async def test_transient_reset_retried_then_succeeds(
        self, make_session, session_manager
    ):
        session = await make_session()
        real_start = session_manager.start_episode
        failures = [OpenEnvTransientError("dropped"), OpenEnvCapacityError("full")]
        attempts = 0

        async def flaky_start(server, reset_kwargs):
            nonlocal attempts
            attempts += 1
            if failures:
                raise failures.pop(0)
            return await real_start(server, reset_kwargs)

        with patch.object(session_manager, "start_episode", side_effect=flaky_start):
            result = await call(session, "start_episode", reset_kwargs={})
        assert not result.is_error
        assert attempts == 3

    async def test_capacity_retried_twice_then_raised(
        self, make_session, openenv_server, session_manager
    ):
        session = await make_session()
        holder = OpenEnvSessionManager()
        held = await holder.start_episode(openenv_server, {})
        try:
            with patch.object(
                session_manager, "start_episode", wraps=session_manager.start_episode
            ) as spy:
                with pytest.raises(OpenEnvCapacityError):
                    await call(session, "start_episode", reset_kwargs={})
            assert spy.await_count == 3
            assert session.call_log[-1].is_error
        finally:
            await holder.release(held)
            await holder.shutdown()

    async def test_transient_tool_error_clears_the_episode_and_raises(
        self, project, one_session_url
    ):
        openenv_server = OpenEnvServer(name="slow", parent=project, url=one_session_url)
        openenv_server.save_to_file()
        manager = OpenEnvSessionManager(step_timeout_s=0.2)
        try:
            tools = await manager.list_tools(openenv_server)
            session = GroundingSession(openenv_server, manager, tools)
            await call(session, "start_episode", reset_kwargs={})
            with pytest.raises(OpenEnvTransientError, match="did not answer"):
                await call(session, "sleep", seconds=1)
            with pytest.raises(ToolCallError, match=CLOSED_EPISODE_MESSAGE):
                await call(session, "read_notes")
            assert session.call_log[-2].tool == "sleep"
            assert session.call_log[-2].episode_id is not None
            await session.close()
        finally:
            await manager.shutdown()

    async def test_session_ending_error_asks_for_a_new_episode(
        self, make_session, session_manager
    ):
        session = await make_session()
        await call(session, "start_episode", reset_kwargs={})
        with patch.object(
            session_manager,
            "call_tool",
            AsyncMock(side_effect=OpenEnvSessionLostError("the socket broke")),
        ):
            with pytest.raises(
                ToolCallError, match=f"the socket broke {CLOSED_EPISODE_MESSAGE}"
            ):
                await call(session, "read_notes")
        with pytest.raises(ToolCallError, match=CLOSED_EPISODE_MESSAGE):
            await call(session, "read_state")
        await call(session, "start_episode", reset_kwargs={})
        assert not (await call(session, "read_notes")).is_error

    async def test_rejected_tool_call_keeps_the_episode(
        self, make_session, session_manager
    ):
        session = await make_session()
        await call(session, "start_episode", reset_kwargs={})
        with patch.object(
            session_manager,
            "call_tool",
            AsyncMock(side_effect=OpenEnvRejectedError("bad arguments", "bad")),
        ):
            with pytest.raises(ToolCallError, match="bad arguments"):
                await call(session, "append_note", note="x")
        assert not (await call(session, "read_notes")).is_error


class TestLimits:
    async def test_tool_call_limit(self, make_session):
        session = await make_session(
            limits=GroundingLimits(max_tool_calls=2, calls_after_limit=2)
        )
        await call(session, "start_episode", reset_kwargs={})
        await call(session, "read_notes")
        await call(session, "read_state")
        for tool_name in ("read_notes", "start_episode"):
            with pytest.raises(ToolCallError, match="used up your 2 tool calls"):
                await call(session, tool_name, reset_kwargs={})
        assert session.limit_reached
        with pytest.raises(GroundingLimitReached, match="2 tool calls"):
            await call(session, "read_notes")

    async def test_reset_limit(self, make_session):
        session = await make_session(
            limits=GroundingLimits(max_resets=2, calls_after_limit=1)
        )
        await call(session, "start_episode", reset_kwargs={})
        with pytest.raises(ToolCallError):
            await call(session, "start_episode", reset_kwargs={"fail_reset": True})
        with pytest.raises(ToolCallError, match="used up your 2 resets"):
            await call(session, "start_episode", reset_kwargs={})
        with pytest.raises(GroundingLimitReached, match="2 resets"):
            await call(session, "read_notes")

    async def test_resets_left_do_not_stop_tool_calls(self, make_session):
        session = await make_session(limits=GroundingLimits(max_resets=1))
        await call(session, "start_episode", reset_kwargs={})
        assert not (await call(session, "read_notes")).is_error
        assert not session.limit_reached

    async def test_refused_calls_count_toward_the_limit(self, make_session):
        session = await make_session(
            limits=GroundingLimits(max_tool_calls=1, calls_after_limit=0)
        )
        with pytest.raises(ToolCallError, match=NO_EPISODE_MESSAGE):
            await call(session, "read_notes")
        with pytest.raises(GroundingLimitReached):
            await call(session, "read_notes")


class TestCallLog:
    async def test_every_call_is_logged(self, make_session):
        session = await make_session()
        with pytest.raises(ToolCallError):
            await call(session, "read_notes")
        await call(session, "start_episode", reset_kwargs={"fixture_id": "a"})
        await call(session, "append_note", note="hi")
        await call(session, "explode")
        log = session.call_log
        assert [(c.tool, c.args, c.is_error) for c in log] == [
            ("read_notes", {}, True),
            ("start_episode", {"reset_kwargs": {"fixture_id": "a"}}, False),
            ("append_note", {"note": "hi"}, False),
            ("explode", {}, True),
        ]
        assert log[0].output == NO_EPISODE_MESSAGE
        assert log[0].episode_id is None
        assert log[2].output == "noted:1"
        assert log[1].episode_id is not None
        assert log[1].episode_id == log[2].episode_id == log[3].episode_id

    async def test_call_log_is_a_copy(self, make_session):
        session = await make_session()
        await call(session, "start_episode", reset_kwargs={})
        session.call_log.clear()
        assert len(session.call_log) == 1
