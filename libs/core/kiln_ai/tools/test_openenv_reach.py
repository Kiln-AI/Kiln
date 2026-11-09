import pytest

from kiln_ai.datamodel.code_tool import CodeTool
from kiln_ai.datamodel.external_tool_server import ExternalToolServer, ToolServerType
from kiln_ai.datamodel.openenv import OpenEnvServer
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.run_config import (
    KilnAgentRunConfigProperties,
    McpRunConfigProperties,
    MCPToolReference,
    ToolsRunConfig,
)
from kiln_ai.datamodel.task import Task, TaskRunConfig
from kiln_ai.datamodel.tool_id import (
    build_code_tool_id,
    build_kiln_task_tool_id,
    build_openenv_tool_id,
)
from kiln_ai.tools.openenv_reach import (
    OpenEnvReach,
    OpenEnvReachError,
    openenv_reach,
    single_openenv_server_id,
)


@pytest.fixture
def project(tmp_path) -> Project:
    project = Project(name="proj", path=tmp_path / "project.kiln")
    project.save_to_file()
    return project


@pytest.fixture
def make_openenv_server(project):
    def _make(name: str) -> OpenEnvServer:
        env = OpenEnvServer(name=name, parent=project)
        env.save_to_file()
        return env

    return _make


@pytest.fixture
def make_code_tool(project):
    def _make(name: str, allowlist: list[str]) -> str:
        code_tool = CodeTool(
            name=name,
            tool_function_name=name,
            tool_description="d",
            parameters_schema={"type": "object", "properties": {}},
            code="def run() -> str:\n    return 'ok'\n",
            tool_allowlist=allowlist,
            parent=project,
        )
        code_tool.save_to_file()
        return build_code_tool_id(code_tool.id)

    return _make


@pytest.fixture
def make_kiln_task_tool(project):
    """A Kiln task tool whose run config lists *tools*. Returns its tool id."""

    def _make(name: str, tools: list[str], mcp_run_config: bool = False) -> str:
        task = Task(name="sub", instruction="do it", parent=project)
        task.save_to_file()
        properties = (
            McpRunConfigProperties(
                tool_reference=MCPToolReference(tool_id="mcp::local::s::t")
            )
            if mcp_run_config
            else KilnAgentRunConfigProperties(
                model_name="gpt-4o",
                model_provider_name="openai",
                prompt_id="simple_prompt_builder",
                structured_output_mode="json_schema",
                tools_config=ToolsRunConfig(tools=tools),
            )
        )
        run_config = TaskRunConfig(
            name="rc", run_config_properties=properties, parent=task
        )
        run_config.save_to_file()
        server = ExternalToolServer(
            name=f"{name}_server",
            type=ToolServerType.kiln_task,
            properties={
                "name": name,
                "description": "d",
                "task_id": task.id,
                "run_config_id": run_config.id,
                "is_archived": False,
            },
            parent=project,
        )
        server.save_to_file()
        return build_kiln_task_tool_id(server.id)

    return _make


def test_no_tools_reach_nothing(project, make_code_tool):
    code_tool = make_code_tool("plain", ["kiln_tool::add_numbers"])
    assert openenv_reach(project, []) == []
    assert openenv_reach(project, ["kiln_tool::add_numbers", code_tool]) == []
    assert single_openenv_server_id(project, [code_tool]) is None


def test_direct_openenv_tool(project, make_openenv_server):
    acme = make_openenv_server("Acme")
    tool_ids = [
        build_openenv_tool_id(acme.id, "search"),
        build_openenv_tool_id(acme.id, "get"),
    ]
    assert openenv_reach(project, tool_ids) == [OpenEnvReach(acme.id, "directly")]
    assert single_openenv_server_id(project, tool_ids) == acme.id


def test_nested_code_tools_name_the_outermost(
    project, make_openenv_server, make_code_tool
):
    acme = make_openenv_server("Acme")
    inner = make_code_tool("inner", [build_openenv_tool_id(acme.id, "search")])
    outer = make_code_tool("outer", [inner])
    assert openenv_reach(project, [outer]) == [OpenEnvReach(acme.id, "code tool outer")]


def test_kiln_task_tool_into_code_tool(
    project, make_openenv_server, make_code_tool, make_kiln_task_tool
):
    acme = make_openenv_server("Acme")
    code_tool = make_code_tool("lookup", [build_openenv_tool_id(acme.id, "search")])
    task_tool = make_kiln_task_tool("planner", [code_tool])
    assert openenv_reach(project, [task_tool]) == [
        OpenEnvReach(acme.id, "Kiln task tool planner")
    ]


def test_kiln_task_tool_with_mcp_run_config_reaches_nothing(
    project, make_kiln_task_tool
):
    task_tool = make_kiln_task_tool("planner", [], mcp_run_config=True)
    assert openenv_reach(project, [task_tool]) == []


def test_cycle_terminates(project, make_openenv_server, make_code_tool):
    acme = make_openenv_server("Acme")
    openenv_tool = build_openenv_tool_id(acme.id, "search")
    a = make_code_tool("a", [openenv_tool])
    b = make_code_tool("b", [a])
    a_tool = CodeTool.from_id_and_parent_path(a.split("::")[-1], project.path)
    assert a_tool is not None
    a_tool.tool_allowlist = [openenv_tool, b]
    a_tool.save_to_file()

    assert openenv_reach(project, [a, b]) == [
        OpenEnvReach(acme.id, "code tool a"),
        OpenEnvReach(acme.id, "code tool b"),
    ]


def test_missing_and_malformed_targets_are_skipped(
    project, make_openenv_server, make_kiln_task_tool
):
    acme = make_openenv_server("Acme")
    good = make_kiln_task_tool("planner", [build_openenv_tool_id(acme.id, "search")])
    missing_run_config = make_kiln_task_tool("broken", [])
    server_id = missing_run_config.split("::")[-1]
    server = ExternalToolServer.from_id_and_parent_path(server_id, project.path)
    assert server is not None
    server.properties = {**server.properties, "run_config_id": "gone"}
    server.save_to_file()
    missing_task = make_kiln_task_tool("orphan", [])
    server = ExternalToolServer.from_id_and_parent_path(
        missing_task.split("::")[-1], project.path
    )
    assert server is not None
    server.properties = {**server.properties, "task_id": "gone"}
    server.save_to_file()

    tool_ids = [
        "kiln_tool::code::missing",
        "kiln_task::missing_server",
        "kiln_tool::openenv::",
        missing_run_config,
        missing_task,
        good,
    ]
    assert openenv_reach(project, tool_ids) == [
        OpenEnvReach(acme.id, "Kiln task tool planner")
    ]


def test_one_openenv_server_reached_two_ways(
    project, make_openenv_server, make_code_tool
):
    acme = make_openenv_server("Acme")
    openenv_tool = build_openenv_tool_id(acme.id, "search")
    code_tool = make_code_tool("lookup", [openenv_tool])
    tool_ids = [openenv_tool, code_tool]
    assert openenv_reach(project, tool_ids) == [
        OpenEnvReach(acme.id, "directly"),
        OpenEnvReach(acme.id, "code tool lookup"),
    ]
    assert single_openenv_server_id(project, tool_ids) == acme.id


def test_two_openenv_servers_raise_naming_each(
    project, make_openenv_server, make_code_tool
):
    acme = make_openenv_server("Acme")
    beta = make_openenv_server("Beta")
    code_tool = make_code_tool("lookup", [build_openenv_tool_id(beta.id, "search")])
    tool_ids = [build_openenv_tool_id(acme.id, "search"), code_tool]

    with pytest.raises(OpenEnvReachError) as exc_info:
        single_openenv_server_id(project, tool_ids)

    error = exc_info.value
    assert error.message == (
        "Your tools use more than one OpenEnv server (Acme, Beta). A run can only use one."
    )
    assert str(error) == (
        f"{error.message} Reached by: Acme (directly), Beta (code tool lookup)."
    )
    assert isinstance(error, ValueError)


def test_missing_openenv_server_named_by_id(project, make_openenv_server):
    acme = make_openenv_server("Acme")
    tool_ids = [
        build_openenv_tool_id(acme.id, "search"),
        build_openenv_tool_id("gone_openenv_server", "search"),
    ]
    with pytest.raises(OpenEnvReachError, match=r"\(Acme, gone_openenv_server\)"):
        single_openenv_server_id(project, tool_ids)
