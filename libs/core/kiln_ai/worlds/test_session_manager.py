"""Tests for the OpenEnv session manager against the test environment server. Kiln only
connects to a running server named by `env_url`; it never starts one."""

import hashlib

import pytest

from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.world import World
from kiln_ai.worlds import session_manager as session_manager_module
from kiln_ai.worlds.session_manager import (
    PING_INTERVAL_S,
    PING_TIMEOUT_S,
    OpenEnvError,
    OpenEnvSessionManager,
    ToolCallOutcome,
)
from kiln_ai.worlds.testing import (
    ENV_NAME,
    ControlledCounterEnv,
    free_port,
    serve_in_thread,
)


@pytest.fixture
def project(tmp_path):
    p = Project(name="proj", path=tmp_path / "proj" / "project.kiln")
    p.path.parent.mkdir(parents=True)
    p.save_to_file()
    return p


@pytest.fixture
def server_url():
    with serve_in_thread() as base_url:
        yield base_url


@pytest.fixture
def remote_world(project, server_url):
    w = World(name="remote", parent=project, env_url=server_url)
    w.save_to_file()
    return w


@pytest.fixture
def controlled_url():
    with serve_in_thread(env_factory=ControlledCounterEnv) as base_url:
        yield base_url


@pytest.fixture
def controlled_world(project, controlled_url):
    """A world whose environment speaks coded errors and serves control tools."""
    w = World(name="controlled", parent=project, env_url=controlled_url)
    w.save_to_file()
    return w


@pytest.fixture
async def session_manager():
    session_manager = OpenEnvSessionManager()
    try:
        yield session_manager
    finally:
        await session_manager.shutdown()


class TestRemoteSessions:
    async def test_list_tools_and_content_version(self, session_manager, remote_world):
        tools = await session_manager.list_tools(remote_world)
        assert [t.name for t in tools] == ["append_note", "read_notes", "explode"]
        assert tools[0].input_schema["required"] == ["note"]
        assert tools[0].toolcall_definition()["function"]["name"] == "append_note"
        # Cached per server: a second call does not open a session.
        assert await session_manager.list_tools(remote_world) is tools
        version = await session_manager.world_version(remote_world, {})
        assert version == f"{ENV_NAME}@1.0.0"
        assert await session_manager.world_version(remote_world, {"x": 1}) == version

    async def test_start_episode_records_the_reset(self, session_manager, remote_world):
        episode = await session_manager.start_episode(
            remote_world, {"fixture_id": "boxr", "frozen_time": "2026-07-14"}
        )
        assert episode.reset.world_id == remote_world.id
        assert episode.world_version == f"{ENV_NAME}@1.0.0"
        assert episode.reset.reset_kwargs == {
            "fixture_id": "boxr",
            "frozen_time": "2026-07-14",
        }
        # Only what the environment reported: no Kiln-added keys.
        assert episode.reset_facts == {
            "fixture_id": "boxr",
            "frozen_time": "2026-07-14",
        }
        assert episode.final_state is None

    async def test_call_tool_and_end_episode(self, session_manager, remote_world):
        episode = await session_manager.start_episode(remote_world, {"fixture_id": "a"})
        ok = await session_manager.call_tool(episode, "append_note", {"note": "hi"})
        assert ok.result == "noted:1" and ok.error is None
        assert ok.reward == 1.0 and ok.done is False
        listed = await session_manager.call_tool(episode, "read_notes", {})
        assert listed.result == ["hi"]
        boom = await session_manager.call_tool(episode, "explode", {})
        assert boom.result is None and boom.error == "boom"
        assert boom.reward == -1.0 and boom.done is True
        assert boom.error_code is None and boom.error_details is None
        missing = await session_manager.call_tool(episode, "nope", {})
        assert missing.error == "no tool 'nope'"
        # Rewards and done are tracked on the live session only.
        session = session_manager._sessions[episode.episode_id]
        assert session.rewards == [1.0, 0.0, -1.0] and session.done is True

        final = await session_manager.end_episode(episode)
        assert final.final_state is not None
        assert final.final_state["notes"] == ["hi"]
        assert final.final_state["step_count"] == 4
        assert final.final_state["episode_id"] == episode.episode_id
        # This environment serves no control tools, so the settle keys are absent.
        assert "changes" not in final.final_state
        assert "state_digest" not in final.final_state
        assert set(final.model_dump()) == {
            "reset",
            "episode_id",
            "world_version",
            "reset_facts",
            "final_state",
        }
        # The session is gone: tools cannot be called after end_episode, and a second
        # end_episode is a no-op.
        with pytest.raises(RuntimeError, match="no live session"):
            await session_manager.call_tool(episode, "append_note", {"note": "late"})
        assert await session_manager.end_episode(final) is final

    async def test_reference_server_end_to_end_without_control_tools(
        self, session_manager, remote_world
    ):
        """An environment that knows nothing of control tools is unaffected: its
        final_state is exactly what its own `state` reported."""
        tools = await session_manager.list_tools(remote_world)
        assert [t.name for t in tools] == ["append_note", "read_notes", "explode"]
        episode = await session_manager.start_episode(remote_world, {"fixture_id": "a"})
        await session_manager.call_tool(episode, "append_note", {"note": "hi"})
        final = await session_manager.end_episode(episode)
        assert final.final_state == {
            "episode_id": episode.episode_id,
            "step_count": 1,
            "notes": ["hi"],
            "fixture_id": "a",
        }
        assert session_manager._sessions == {}

    async def test_coded_error_is_forwarded(self, session_manager, controlled_world):
        episode = await session_manager.start_episode(controlled_world, {})
        outcome = await session_manager.call_tool(episode, "fail_coded", {})
        assert outcome.error == "bad note"
        assert outcome.error_code == "invalid_input"
        assert outcome.error_details == {"field": "note"}

    async def test_reset_result_fills_and_metadata_wins(
        self, session_manager, controlled_world
    ):
        episode = await session_manager.start_episode(
            controlled_world, {"fixture_id": "a", "frozen_time": "2026-07-14"}
        )
        # `tools` exists only in the observation's result; `fixture_id` is in both, and
        # the metadata's value wins.
        assert episode.reset_facts["tools"] == len(ControlledCounterEnv.TOOLS)
        assert episode.reset_facts["fixture_id"] == "a"
        assert episode.reset_facts["frozen_time"] == "2026-07-14"

    async def test_end_episode_settles_changes_and_digest(
        self, session_manager, controlled_world
    ):
        episode = await session_manager.start_episode(controlled_world, {})
        await session_manager.call_tool(episode, "append_note", {"note": "hi"})
        final = await session_manager.end_episode(episode)
        assert final.final_state["changes"] == [
            {
                "table": "notes",
                "op": "insert",
                "key": {"n": 0},
                "before": None,
                "after": {"n": 0, "note": "hi"},
            }
        ]
        assert final.final_state["state_digest"] == hashlib.sha256(b"hi").hexdigest()
        # Settling happens after `state`, so step_count is still the agent's own.
        assert final.final_state["step_count"] == 1
        assert final.final_state["notes"] == ["hi"]

    async def test_settle_calls_are_configurable(self, controlled_world):
        async def settled(**kwargs):
            session_manager = OpenEnvSessionManager(**kwargs)
            try:
                episode = await session_manager.start_episode(controlled_world, {})
                await session_manager.call_tool(episode, "append_note", {"note": "hi"})
                return (await session_manager.end_episode(episode)).final_state
            finally:
                await session_manager.shutdown()

        none = await settled(settle_calls=())
        assert "changes" not in none and "state_digest" not in none

        renamed = await settled(settle_calls=(("digest", "controller_digest"),))
        assert renamed["digest"] == hashlib.sha256(b"hi").hexdigest()
        assert "changes" not in renamed and "state_digest" not in renamed

    async def test_settle_records_a_coded_failure(
        self, session_manager, controlled_world
    ):
        """A control tool that is served and broken is evidence, not an exception: the
        episode still ends and the generation is still saved."""
        episode = await session_manager.start_episode(controlled_world, {})
        await session_manager.call_tool(episode, "append_note", {"note": "poison"})
        final = await session_manager.end_episode(episode)
        assert final.final_state["settle_error"] == {
            "tool": "controller_changes",
            "code": "db_error",
            "message": "diff failed",
        }
        # Settling stopped at the failure, so neither key was written.
        assert "changes" not in final.final_state
        assert "state_digest" not in final.final_state
        assert final.final_state["step_count"] == 1
        assert final.final_state["notes"] == ["poison"]
        assert session_manager._sessions == {}

    @pytest.mark.parametrize("error_code", [None, "unknown_tool", "tool_not_found"])
    async def test_settle_tolerates_every_shape_of_no_such_tool(
        self, session_manager, remote_world, error_code
    ):
        """An environment that does not serve a control tool leaves the key absent and
        settling running, whichever way it says so. OpenEnv's `MCPEnvironment` reports
        an unknown tool with no code at all today; if its error_type is ever mapped onto
        the code, the tolerance must still hold rather than write `settle_error` into
        every episode's final_state."""
        episode = await session_manager.start_episode(remote_world, {})
        session = session_manager._sessions[episode.episode_id]

        async def not_served(_session, tool_name, _arguments, *, record):
            return ToolCallOutcome(
                result=None,
                error=f"no tool '{tool_name}'",
                reward=None,
                done=False,
                error_code=error_code,
            )

        session_manager._step_call_tool = not_served
        state: dict = {}
        await session_manager._settle(episode, session, state)
        assert state == {}

    async def test_settle_stops_at_the_first_failure(self, controlled_world):
        session_manager = OpenEnvSessionManager(
            settle_calls=(
                ("digest", "controller_digest"),
                ("changes", "controller_changes"),
            )
        )
        try:
            episode = await session_manager.start_episode(controlled_world, {})
            await session_manager.call_tool(episode, "append_note", {"note": "poison"})
            final = await session_manager.end_episode(episode)
        finally:
            await session_manager.shutdown()
        # The digest was taken before the failing call, so only `changes` is missing.
        assert final.final_state["digest"] == hashlib.sha256(b"poison").hexdigest()
        assert "changes" not in final.final_state
        assert final.final_state["settle_error"]["tool"] == "controller_changes"

    async def test_call_control_tool_on_a_live_session(
        self, session_manager, controlled_world, remote_world
    ):
        episode = await session_manager.start_episode(controlled_world, {})
        await session_manager.call_tool(episode, "append_note", {"note": "hi"})
        outcome = await session_manager.call_control_tool(
            episode, "controller_digest", {}
        )
        assert outcome.result == hashlib.sha256(b"hi").hexdigest()
        # A control call is not the agent's: no reward is recorded for it.
        assert session_manager._sessions[episode.episode_id].rewards == [1.0]
        await session_manager.end_episode(episode)
        with pytest.raises(RuntimeError, match="no live session"):
            await session_manager.call_control_tool(episode, "controller_digest", {})

        # An environment that serves no such tool answers, rather than raising.
        other = await session_manager.start_episode(remote_world, {})
        absent = await session_manager.call_control_tool(other, "controller_digest", {})
        assert absent.error == "no tool 'controller_digest'"
        assert absent.error_code is None

    async def test_sessions_are_isolated(self, session_manager, remote_world):
        one = await session_manager.start_episode(remote_world, {"fixture_id": "one"})
        two = await session_manager.start_episode(remote_world, {"fixture_id": "two"})
        await session_manager.call_tool(one, "append_note", {"note": "from one"})
        await session_manager.call_tool(two, "append_note", {"note": "from two"})
        await session_manager.call_tool(two, "append_note", {"note": "again"})
        f1 = await session_manager.end_episode(one)
        f2 = await session_manager.end_episode(two)
        assert f1.final_state and f1.final_state["notes"] == ["from one"]
        assert f2.final_state and f2.final_state["notes"] == ["from two", "again"]
        assert f1.episode_id != f2.episode_id

    async def test_release_drops_session(self, session_manager, remote_world):
        episode = await session_manager.start_episode(remote_world, {})
        await session_manager.release(episode)
        assert episode.episode_id not in session_manager._sessions
        with pytest.raises(RuntimeError):
            await session_manager.call_tool(episode, "read_notes", {})
        await session_manager.release(episode)

    async def test_sessions_state_the_keepalive_they_run_under(
        self, session_manager, remote_world, monkeypatch
    ):
        """A world server that stalls its event loop cannot answer a ping, and the
        library's own 20s timeout would drop every session on the box at once. Both
        values are passed, so a library default that moves cannot change what a run
        measured."""
        seen: dict = {}
        real_connect = session_manager_module.connect

        async def recording_connect(url, **kwargs):
            seen.update(kwargs)
            return await real_connect(url, **kwargs)

        monkeypatch.setattr(session_manager_module, "connect", recording_connect)
        episode = await session_manager.start_episode(remote_world, {})
        assert seen["ping_interval"] == PING_INTERVAL_S == 20.0
        assert seen["ping_timeout"] == PING_TIMEOUT_S == 120.0
        assert seen["open_timeout"] == 30 and seen["max_size"] is None
        await session_manager.end_episode(episode)

    async def test_error_responses_raise(self, session_manager, remote_world):
        server = await session_manager._server_for(remote_world)
        async with session_manager._connect(server) as ws:
            with pytest.raises(OpenEnvError, match="Unknown message type"):
                await session_manager._request(ws, {"type": "bogus"})

    async def test_unreachable_url_is_an_error(self, session_manager, project):
        world = World(
            name="dead", parent=project, env_url=f"http://127.0.0.1:{free_port()}"
        )
        world.save_to_file()
        with pytest.raises(OpenEnvError, match="did not answer /metadata"):
            await session_manager.list_tools(world)

    async def test_shutdown_closes_sessions(self, session_manager, remote_world):
        await session_manager.start_episode(remote_world, {})
        assert session_manager._sessions
        await session_manager.shutdown()
        assert not session_manager._sessions and not session_manager._servers


class TestWorldsWithoutUrl:
    async def test_no_env_url_is_an_error(self, session_manager, project):
        world = World(name="no url", parent=project)
        world.save_to_file()
        with pytest.raises(OpenEnvError, match="has no env_url"):
            await session_manager.list_tools(world)
        assert session_manager.server_for_world_id(world.id) is None


class TestEnvironmentIdentity:
    async def test_version_keys_content(self, session_manager, remote_world):
        before = await session_manager.world_version(remote_world, {})
        with serve_in_thread(version="2.0.0") as upgraded:
            remote_world.env_url = upgraded
            after = await session_manager.world_version(remote_world, {})
            assert after != before
            server = session_manager.server_for_world_id(remote_world.id)
            assert server is not None and server.env_version == "2.0.0"

    async def test_url_change_reconnects(self, session_manager, remote_world):
        await session_manager.world_version(remote_world, {})
        first = session_manager.server_for_world_id(remote_world.id)
        remote_world.env_url = remote_world.env_url + "/"
        assert (await session_manager._server_for(remote_world)) is first
        remote_world.env_url = f"http://127.0.0.1:{free_port()}"
        with pytest.raises(OpenEnvError, match="did not answer /metadata"):
            await session_manager.world_version(remote_world, {})
