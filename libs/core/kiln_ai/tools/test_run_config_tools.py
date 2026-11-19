from unittest.mock import patch

import pytest

from kiln_ai.datamodel.openenv import OpenEnvServer
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.task import Task
from kiln_ai.datamodel.tool_id import build_openenv_tool_id
from kiln_ai.openenv.session_manager import OpenEnvError, OpenEnvSessionManager
from kiln_ai.openenv.testing import free_port, serve_in_thread
from kiln_ai.tools.run_config_tools import (
    served_openenv_tools,
    tool_definitions_without_episode,
)


@pytest.fixture
def task(tmp_path) -> Task:
    project = Project(name="proj", path=tmp_path / "proj" / "project.kiln")
    project.path.parent.mkdir(parents=True)
    project.save_to_file()
    task = Task(name="t", instruction="Do it.", parent=project)
    task.save_to_file()
    return task


@pytest.fixture
def one_session_url():
    """Holds one session, so an episode left open blocks the next one."""
    with serve_in_thread(max_sessions=1) as base_url:
        yield base_url


def _server(task: Task, url: str, name: str = "counter") -> OpenEnvServer:
    server = OpenEnvServer(name=name, parent=task.parent_project(), url=url)
    server.save_to_file()
    return server


@pytest.fixture
async def manager():
    manager = OpenEnvSessionManager()
    try:
        yield manager
    finally:
        await manager.shutdown()


async def _no_session_left_open(server: OpenEnvServer) -> None:
    check = OpenEnvSessionManager()
    try:
        await check.release(await check.start_episode(server, {}))
    finally:
        await check.shutdown()


class TestServedOpenenvTools:
    async def test_maps_each_openenv_id_to_its_served_tool(
        self, task, one_session_url, manager
    ):
        server = _server(task, one_session_url)
        append = build_openenv_tool_id(server.id, "append_note")
        read = build_openenv_tool_id(server.id, "read_notes")

        tools = await served_openenv_tools(
            task, [append, "kiln_tool::add_numbers", read], manager
        )

        assert list(tools) == [append, read]
        assert tools[append].description == "Append a note to the episode's notebook."
        assert tools[read].name == "read_notes"
        await _no_session_left_open(server)

    async def test_lists_each_server_once(self, task, one_session_url, manager):
        server = _server(task, one_session_url)
        ids = [
            build_openenv_tool_id(server.id, "append_note"),
            build_openenv_tool_id(server.id, "read_notes"),
        ]
        with patch.object(
            manager, "list_tools", wraps=manager.list_tools
        ) as list_tools:
            await served_openenv_tools(task, ids, manager)
        assert list_tools.call_count == 1

    async def test_no_openenv_ids_reads_nothing(self, manager):
        # A task with no project works too: nothing needs the project.
        task = Task(name="t", instruction="Do it.")
        assert (
            await served_openenv_tools(task, ["kiln_tool::add_numbers"], manager) == {}
        )

    async def test_a_tool_the_server_does_not_serve_raises(
        self, task, one_session_url, manager
    ):
        server = _server(task, one_session_url)
        with pytest.raises(ValueError, match="does not serve a tool named 'nope'"):
            await served_openenv_tools(
                task, [build_openenv_tool_id(server.id, "nope")], manager
            )

    async def test_a_missing_server_record_raises(self, task, manager):
        with pytest.raises(ValueError, match="OpenEnv server 999 wasn't found"):
            await served_openenv_tools(
                task, [build_openenv_tool_id("999", "append_note")], manager
            )

    async def test_an_unreachable_server_raises_with_its_url(self, task, manager):
        url = f"http://127.0.0.1:{free_port()}"
        server = _server(task, url)
        with pytest.raises(OpenEnvError, match=url):
            await served_openenv_tools(
                task, [build_openenv_tool_id(server.id, "append_note")], manager
            )


class TestToolDefinitionsWithoutEpisode:
    async def test_definitions_keep_order_and_skip_skills(
        self, task, one_session_url, manager
    ):
        server = _server(task, one_session_url)

        definitions = await tool_definitions_without_episode(
            task,
            [
                build_openenv_tool_id(server.id, "read_notes"),
                "kiln_tool::skill::123",
                "kiln_tool::add_numbers",
            ],
            manager,
        )

        assert [d["function"]["name"] for d in definitions] == ["read_notes", "add"]
        assert definitions[0]["function"]["parameters"] == {
            "type": "object",
            "properties": {},
        }
        await _no_session_left_open(server)
