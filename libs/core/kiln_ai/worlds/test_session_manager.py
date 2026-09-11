"""Tests for the OpenEnv session manager against the test environment server. Kiln only
connects to a running server named by `env_url`; it never starts one."""

import pytest

from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.world import World
from kiln_ai.worlds.session_manager import (
    OpenEnvError,
    OpenEnvSessionManager,
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

    async def test_start_episode_reports_reset_metadata(
        self, session_manager, remote_world
    ):
        episode = await session_manager.start_episode(
            remote_world, {"fixture_id": "boxr", "frozen_time": "2026-07-14"}
        )
        assert episode.world_id == remote_world.id
        assert episode.world_version == f"{ENV_NAME}@1.0.0"
        assert episode.reset_kwargs == {
            "fixture_id": "boxr",
            "frozen_time": "2026-07-14",
        }
        # Only what the environment reported: no Kiln-added keys.
        assert episode.metadata == {"fixture_id": "boxr", "frozen_time": "2026-07-14"}
        assert episode.state is None

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
        missing = await session_manager.call_tool(episode, "nope", {})
        assert missing.error == "no tool 'nope'"
        # Rewards and done are tracked on the live session only.
        session = session_manager._sessions[episode.episode_id]
        assert session.rewards == [1.0, 0.0, -1.0] and session.done is True

        final = await session_manager.end_episode(episode)
        assert final.state is not None
        assert final.state["notes"] == ["hi"]
        assert final.state["step_count"] == 4
        assert final.state["episode_id"] == episode.episode_id
        assert set(final.model_dump()) == {
            "episode_id",
            "world_id",
            "world_version",
            "reset_kwargs",
            "metadata",
            "state",
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
        assert f1.state and f1.state["notes"] == ["from one"]
        assert f2.state and f2.state["notes"] == ["from two", "again"]
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
