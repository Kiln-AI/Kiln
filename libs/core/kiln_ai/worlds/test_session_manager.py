"""Tests for the OpenEnv session manager against the test environment server. Kiln only
connects to a running server named by `env_url`; it never starts one."""

import pytest

from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.world import World
from kiln_ai.worlds import session_manager as session_manager_module
from kiln_ai.worlds.session_manager import (
    OpenEnvError,
    OpenEnvSessionManager,
    read_observation_error,
)
from kiln_ai.worlds.testing import (
    ENV_NAME,
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
        assert episode.reset_metadata == {
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
        assert boom.error_code == "execution_error" and boom.error_details is None
        assert boom.reward == -1.0 and boom.done is True
        missing = await session_manager.call_tool(episode, "nope", {})
        assert missing.error == "no tool 'nope'"
        assert missing.error_code == "tool_not_found"
        # Rewards and done are tracked on the live session only.
        session = session_manager._sessions[episode.episode_id]
        assert session.rewards == [1.0, 0.0, -1.0] and session.done is True

        final = await session_manager.end_episode(episode)
        assert final.final_state is not None
        assert final.final_state["notes"] == ["hi"]
        assert final.final_state["step_count"] == 4
        assert final.final_state["episode_id"] == episode.episode_id
        assert set(final.model_dump()) == {
            "reset",
            "episode_id",
            "world_version",
            "reset_metadata",
            "final_state",
        }
        # The session is gone: tools cannot be called after end_episode, and a second
        # end_episode is a no-op.
        with pytest.raises(RuntimeError, match="no live session"):
            await session_manager.call_tool(episode, "append_note", {"note": "late"})
        assert await session_manager.end_episode(final) is final

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


class TestErrorShapeTolerance:
    """Kiln reads what an environment sends and never rejects a shape.

    OpenEnv declares `{error_type, message}` and forbids extra keys, so a conformant
    environment cannot send a code or details of its own. Kiln still reads both, for
    an environment that reports an error some other way; an unreadable shape degrades
    to its text rather than failing the call."""

    @pytest.mark.parametrize(
        "error,expected_code,expected_message",
        [
            ({"error_type": "timeout", "message": "slow"}, "timeout", "slow"),
            ({"code": "not_found", "message": "gone"}, "not_found", "gone"),
            # `error_type` wins: it is the field the protocol declares.
            (
                {"error_type": "invalid_args", "code": "bad", "message": "no"},
                "invalid_args",
                "no",
            ),
            # No message: the whole dict is the best text there is.
            ({"error_type": "timeout"}, "timeout", "{'error_type': 'timeout'}"),
            # Not a dict at all.
            ("plain", None, "plain"),
            (42, None, "42"),
        ],
    )
    def test_shapes(self, error, expected_code, expected_message):
        message, code, _ = read_observation_error(error)
        assert message == expected_message
        assert code == expected_code

    def test_no_error_is_no_error(self):
        assert read_observation_error(None) == (None, None, None)

    def test_details_ride_along(self):
        _, _, details = read_observation_error(
            {"code": "not_found", "message": "gone", "details": {"id": 7}}
        )
        assert details == {"id": 7}


class TestKeepalive:
    async def test_session_is_opened_with_a_stated_keepalive(
        self, session_manager, remote_world, monkeypatch
    ):
        """A world server doing synchronous work cannot answer a ping, and the
        library's 20s default would drop the session long before a long tool call
        finished. Both values are stated so a moving default cannot change a run."""
        seen: dict[str, object] = {}
        real_connect = session_manager_module.connect

        async def spy(url, **kwargs):
            seen.update(kwargs)
            return await real_connect(url, **kwargs)

        monkeypatch.setattr(session_manager_module, "connect", spy)
        episode = await session_manager.start_episode(remote_world, {})
        assert seen["ping_interval"] == session_manager_module.PING_INTERVAL_S
        assert seen["ping_timeout"] == session_manager_module.PING_TIMEOUT_S
        assert seen["ping_timeout"] > 20, "the library default is what we are avoiding"
        await session_manager.release(episode)
