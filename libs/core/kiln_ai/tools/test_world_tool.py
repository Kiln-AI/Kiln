"""Tests for resolving world tool ids through the registry, and the proxy
they resolve to. The session manager is a fake that records calls."""

from dataclasses import dataclass, field
from typing import Any

import pytest

from kiln_ai.datamodel.code_tool import CodeTool
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.tool_id import (
    KilnBuiltInToolId,
    build_code_tool_id,
    build_world_tool_id,
)
from kiln_ai.datamodel.world import (
    Episode,
    OpenEnvTool,
    World,
)
from kiln_ai.run_context import (
    EpisodeContext,
    get_episode,
    reset_episode,
    set_episode,
)
from kiln_ai.tools.base_tool import ToolCallContext
from kiln_ai.tools.built_in_tools.math_tools import AddTool
from kiln_ai.tools.code_tool import PythonCodeTool
from kiln_ai.tools.tool_registry import tool_from_id_and_project
from kiln_ai.tools.world_tool import OpenEnvToolProxy, render_tool_result
from kiln_ai.worlds.session_manager import ToolCallOutcome

SCHEMA = {"type": "object", "properties": {"x": {"type": "string"}}}
ENV_SCHEMA = {
    "type": "object",
    "properties": {"x": {"type": "string"}, "extra": {"type": "integer"}},
}
REAL_CODE = "def run(x):\n    return 'real:' + x\n"


@dataclass
class FakeSessionManager:
    outcome: ToolCallOutcome = field(
        default_factory=lambda: ToolCallOutcome(
            result="env:ok", error=None, reward=1.0, done=False
        )
    )
    calls: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)

    async def call_tool(self, episode, tool_name, arguments):
        self.calls.append((episode.episode_id, tool_name, dict(arguments)))
        return self.outcome


@pytest.fixture
def project(tmp_path):
    p = Project(name="proj", path=tmp_path / "proj" / "project.kiln")
    p.path.parent.mkdir(parents=True)
    p.save_to_file()
    return p


@pytest.fixture
def project_tool(project):
    """A project code tool with the same function name as the environment's tool. It is
    never swapped: a run config picks one or the other by id."""
    ct = CodeTool(
        name="real lookup",
        parent=project,
        tool_function_name="lookup",
        tool_description="real lookup",
        parameters_schema=SCHEMA,
        code=REAL_CODE,
    )
    ct.save_to_file()
    return ct


@pytest.fixture
def world(project):
    w = World(name="w", parent=project)
    w.save_to_file()
    return w


@pytest.fixture
def session_manager():
    return FakeSessionManager()


def _context(world, session_manager):
    return EpisodeContext(
        episode=Episode(episode_id="ep_test", world_id=world.id),
        world=world,
        session_manager=session_manager,  # type: ignore[arg-type]
        tools={
            "lookup": OpenEnvTool(
                name="lookup", description="env lookup", input_schema=ENV_SCHEMA
            )
        },
    )


@pytest.fixture
def active(world, session_manager):
    ctx = _context(world, session_manager)
    token = set_episode(ctx)
    yield ctx
    reset_episode(token)


class TestProjectToolsAreNeverSwapped:
    async def test_no_context_resolves_real_tool(self, project, project_tool):
        assert get_episode() is None
        tool = tool_from_id_and_project(build_code_tool_id(project_tool.id), project)
        assert isinstance(tool, PythonCodeTool)

    async def test_real_id_stays_real_with_an_active_instance(
        self, project, project_tool, active, session_manager
    ):
        real_id = build_code_tool_id(project_tool.id)
        tool = tool_from_id_and_project(real_id, project)
        assert isinstance(tool, PythonCodeTool)
        assert await tool.id() == real_id
        definition = await tool.toolcall_definition()
        assert definition["function"]["parameters"] == SCHEMA
        result = await tool.run(ToolCallContext(), x="q")
        assert result.output == "real:q"
        assert session_manager.calls == []

    async def test_builtins_stay_builtin(self, active):
        assert isinstance(
            tool_from_id_and_project(KilnBuiltInToolId.ADD_NUMBERS.value), AddTool
        )


class TestWorldToolIds:
    async def test_resolves_to_env_tool(self, world, active, session_manager):
        tool_id = build_world_tool_id(world.id, "lookup")
        tool = tool_from_id_and_project(tool_id)
        assert isinstance(tool, OpenEnvToolProxy)
        assert await tool.id() == tool_id
        assert await tool.name() == "lookup"
        assert await tool.description() == "env lookup"
        definition = await tool.toolcall_definition()
        assert definition["function"]["name"] == "lookup"
        assert definition["function"]["parameters"] == ENV_SCHEMA
        assert tool.env_tool is active.tools["lookup"]

        result = await tool.run(ToolCallContext(), x="1")
        assert result.output == "env:ok" and not result.is_error
        assert session_manager.calls == [("ep_test", "lookup", {"x": "1"})]

    async def test_error_outcome_reaches_model_as_error(
        self, world, active, session_manager
    ):
        session_manager.outcome = ToolCallOutcome(
            result=None, error="tool exploded", reward=-1.0, done=True
        )
        tool = tool_from_id_and_project(build_world_tool_id(world.id, "lookup"))
        result = await tool.run(ToolCallContext(), x="q")
        assert result.is_error and result.output == "tool exploded"
        assert result.error_message == "tool exploded"

    async def test_fastmcp_is_error_result_is_an_error(
        self, world, active, session_manager
    ):
        session_manager.outcome = ToolCallOutcome(
            result={
                "content": [{"type": "text", "text": "bad input"}],
                "data": None,
                "is_error": True,
            },
            error=None,
            reward=None,
            done=False,
        )
        tool = tool_from_id_and_project(build_world_tool_id(world.id, "lookup"))
        result = await tool.run(ToolCallContext(), x="q")
        assert result.is_error and result.output == "bad input"
        assert result.error_message == "bad input"

    async def test_without_context(self, world):
        with pytest.raises(ValueError, match="only be used while an episode"):
            tool_from_id_and_project(build_world_tool_id(world.id, "lookup"))

    async def test_context_reset_restores_the_error(self, world, session_manager):
        tool_id = build_world_tool_id(world.id, "lookup")
        token = set_episode(_context(world, session_manager))
        try:
            assert isinstance(tool_from_id_and_project(tool_id), OpenEnvToolProxy)
        finally:
            reset_episode(token)
        with pytest.raises(ValueError, match="only be used while an episode"):
            tool_from_id_and_project(tool_id)

    async def test_for_another_world(self, active):
        with pytest.raises(ValueError, match="only be used while an episode"):
            tool_from_id_and_project(build_world_tool_id("other_world", "lookup"))

    async def test_unknown_tool(self, world, active):
        with pytest.raises(ValueError, match="does not serve a tool named 'nope'"):
            tool_from_id_and_project(build_world_tool_id(world.id, "nope"))


class TestRenderResult:
    def test_shapes(self):
        assert render_tool_result(None) == ""
        assert render_tool_result("text") == "text"
        assert render_tool_result({"a": 1}) == '{"a": 1}'
        assert render_tool_result([1, 2]) == "[1, 2]"
        assert (
            render_tool_result(
                {
                    "content": [
                        {"type": "text", "text": "a"},
                        {"type": "text", "text": "b"},
                    ]
                }
            )
            == "a\nb"
        )
        assert render_tool_result([{"type": "text", "text": "only"}]) == "only"
        fastmcp = {
            "content": [{"type": "text", "text": '{"a": 1}'}],
            "structured_content": {"a": 1},
            "data": {"a": 1},
            "is_error": False,
        }
        assert render_tool_result(fastmcp) == '{"a": 1}'
        assert render_tool_result({**fastmcp, "data": "plain"}) == "plain"
        assert render_tool_result({**fastmcp, "data": None}) == '{"a": 1}'
        assert render_tool_result(
            {"content": [{"type": "image", "data": "x"}]}
        ).startswith('{"content"')
