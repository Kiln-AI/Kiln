import asyncio

import pytest

from kiln_ai.datamodel.openenv import OpenEnvServer
from kiln_ai.datamodel.project import Project
from kiln_ai.openenv.episode_scope import openenv_episode_scope
from kiln_ai.openenv.session_manager import OpenEnvSessionManager
from kiln_ai.openenv.testing import serve_in_thread
from kiln_ai.run_context import get_episode


@pytest.fixture
def openenv_server(tmp_path):
    project = Project(name="proj", path=tmp_path / "proj" / "project.kiln")
    project.path.parent.mkdir(parents=True)
    project.save_to_file()
    with serve_in_thread() as url:
        server = OpenEnvServer(name="Acme", parent=project, url=url)
        server.save_to_file()
        yield server


@pytest.fixture
async def session_manager():
    session_manager = OpenEnvSessionManager()
    try:
        yield session_manager
    finally:
        await session_manager.shutdown()


@pytest.fixture
async def tools(session_manager, openenv_server):
    return {t.name: t for t in await session_manager.list_tools(openenv_server)}


async def test_binds_the_episode_then_ends_it_with_the_final_state(
    session_manager, openenv_server, tools
):
    async with openenv_episode_scope(
        session_manager, openenv_server, {"fixture_id": "f1"}, tools
    ) as scope:
        bound = get_episode()
        assert bound is not None
        assert bound.episode == scope.episode
        assert bound.tools == tools
        await session_manager.call_tool(scope.episode, "append_note", {"note": "hi"})
        with pytest.raises(RuntimeError, match="not ended yet"):
            _ = scope.ended

    assert get_episode() is None
    assert scope.ended.episode_id == scope.episode.episode_id
    assert scope.ended.final_state is not None
    assert scope.ended.final_state["notes"] == ["hi"]
    assert scope.ended.final_state["fixture_id"] == "f1"
    assert session_manager._sessions == {}


@pytest.mark.parametrize("error", [ValueError("boom"), asyncio.CancelledError()])
async def test_an_error_in_the_block_releases_the_episode(
    session_manager, openenv_server, tools, error
):
    with pytest.raises(type(error)):
        async with openenv_episode_scope(
            session_manager, openenv_server, {}, tools
        ) as scope:
            assert session_manager._sessions
            raise error

    assert get_episode() is None
    assert session_manager._sessions == {}
    with pytest.raises(RuntimeError):
        _ = scope.ended
