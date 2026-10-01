"""Tests for the OpenEnv session manager against the test environment server. Kiln only
connects to a running server named by `env_url`; it never starts one."""

import pytest

from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.world import World
from kiln_ai.worlds import session_manager as session_manager_module
from kiln_ai.worlds.session_manager import (
    OpenEnvError,
    OpenEnvRejectedError,
    OpenEnvSessionManager,
    OpenEnvTransientError,
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
        assert [t.name for t in tools] == [
            "append_note",
            "read_notes",
            "explode",
            "sleep",
        ]
        assert tools[0].input_schema["required"] == ["note"]
        assert tools[0].toolcall_definition()["function"]["name"] == "append_note"
        # Cached per server: a second call does not open a session.
        assert await session_manager.list_tools(remote_world) is tools
        assert await session_manager.world_version(remote_world) == f"{ENV_NAME}@1.0.0"

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
            with pytest.raises(OpenEnvRejectedError, match="Unknown message type"):
                await session_manager._request(ws, {"type": "bogus"}, "observation")

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


class TestFailurePaths:
    """What a flaky, overloaded or misbehaving environment does to a session: every
    failure is an `OpenEnvError`, the ones that may not recur are transient, and no
    failure leaves a session behind."""

    async def test_timed_out_call_drops_the_session(self, project, server_url):
        """A late answer would otherwise be read as the answer to the next call, and
        `end_episode` would record it as the final state."""
        world = World(name="slow", parent=project, env_url=server_url)
        world.save_to_file()
        session_manager = OpenEnvSessionManager(step_timeout_s=0.3)
        try:
            episode = await session_manager.start_episode(world, {})
            with pytest.raises(OpenEnvTransientError, match=r"within 0\.3s"):
                await session_manager.call_tool(episode, "sleep", {"seconds": 1})
            assert session_manager._sessions == {}
            with pytest.raises(RuntimeError, match="no live session"):
                await session_manager.call_tool(episode, "read_notes", {})
        finally:
            await session_manager.shutdown()

    async def test_rejected_call_keeps_the_session(self, session_manager, remote_world):
        """An error answer leaves the session in step, so it stays usable."""
        episode = await session_manager.start_episode(remote_world, {})
        with pytest.raises(OpenEnvRejectedError):
            await session_manager.call_tool(episode, "sleep", {"seconds": "soon"})
        listed = await session_manager.call_tool(episode, "read_notes", {})
        assert listed.result == []
        await session_manager.release(episode)

    async def test_rejected_reset_leaves_no_session(
        self, session_manager, remote_world
    ):
        with pytest.raises(OpenEnvRejectedError, match="reset refused"):
            await session_manager.start_episode(remote_world, {"fail_reset": True})
        assert session_manager._sessions == {}

    async def test_failed_state_still_ends_the_session(
        self, session_manager, remote_world
    ):
        episode = await session_manager.start_episode(
            remote_world, {"fail_state": True}
        )
        with pytest.raises(OpenEnvRejectedError, match="state unavailable"):
            await session_manager.end_episode(episode)
        assert session_manager._sessions == {}
        # The ended session freed its slot: a one-session server takes the next reset.
        again = await session_manager.start_episode(remote_world, {})
        await session_manager.release(again)

    async def test_full_server_is_transient(self, session_manager, project):
        with serve_in_thread(max_sessions=1) as base_url:
            world = World(name="full", parent=project, env_url=base_url)
            world.save_to_file()
            first = await session_manager.start_episode(world, {})
            # OpenEnv sends its capacity error and closes at once, so the reset meets
            # either the error or the closed socket; both are transient.
            with pytest.raises(OpenEnvTransientError):
                await session_manager.start_episode(world, {})
            await session_manager.release(first)
            second = await session_manager.start_episode(world, {})
            await session_manager.release(second)

    async def test_refused_session_is_an_open_env_error(self, session_manager, project):
        """A server that answers /metadata but refuses the websocket (an auth wall, a
        proxy, something that isn't OpenEnv) is reported, not leaked as a library
        exception."""
        with serve_in_thread(refuse_sessions=True) as base_url:
            world = World(name="walled", parent=project, env_url=base_url)
            world.save_to_file()
            with pytest.raises(OpenEnvError, match="refused a session"):
                await session_manager.list_tools(world)

    async def test_reply_of_the_wrong_type_is_an_error(
        self, session_manager, remote_world
    ):
        server = await session_manager._server_for(remote_world)
        async with session_manager._connect(server) as ws:
            with pytest.raises(
                OpenEnvError, match="'observation' message, not 'state'"
            ):
                await session_manager._request(
                    ws, {"type": "step", "data": {"type": "list_tools"}}, "state"
                )


class TestWorldsWithoutUrl:
    async def test_no_env_url_is_an_error(self, session_manager, project):
        world = World(name="no url", parent=project)
        world.save_to_file()
        with pytest.raises(OpenEnvError, match="has no env_url"):
            await session_manager.list_tools(world)
        assert world.id not in session_manager._servers


class TestEnvironmentIdentity:
    async def test_version_keys_content(self, session_manager, remote_world):
        before = await session_manager.world_version(remote_world)
        with serve_in_thread(version="2.0.0") as upgraded:
            remote_world.env_url = upgraded
            after = await session_manager.world_version(remote_world)
            assert after == f"{ENV_NAME}@2.0.0" != before

    async def test_url_change_reconnects(self, session_manager, remote_world):
        await session_manager.world_version(remote_world)
        first = session_manager._servers[remote_world.id]
        remote_world.env_url = remote_world.env_url + "/"
        assert (await session_manager._server_for(remote_world)) is first
        remote_world.env_url = f"http://127.0.0.1:{free_port()}"
        with pytest.raises(OpenEnvError, match="did not answer /metadata"):
            await session_manager.world_version(remote_world)

    async def test_refresh_sees_a_new_version_on_the_same_url(
        self, session_manager, project
    ):
        """An environment restarted at a new version on the same URL is seen only
        after a refresh; a refresh that finds the same version keeps the tools, and one
        that finds a new version re-lists them."""
        port = free_port()
        world = World(
            name="same url", parent=project, env_url=f"http://127.0.0.1:{port}"
        )
        world.save_to_file()
        with serve_in_thread(port=port):
            tools = await session_manager.list_tools(world)
            await session_manager.refresh(world)
            assert await session_manager.list_tools(world) is tools
        with serve_in_thread(port=port, version="2.0.0"):
            assert await session_manager.world_version(world) == f"{ENV_NAME}@1.0.0"
            await session_manager.refresh(world)
            assert await session_manager.world_version(world) == f"{ENV_NAME}@2.0.0"
            assert await session_manager.list_tools(world) is not tools


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
