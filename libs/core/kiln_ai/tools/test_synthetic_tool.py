"""Tests for the registry-level synthetic tool swap and the proxy it returns."""

import pytest

from kiln_ai.datamodel.code_tool import CodeTool
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.synthetic_world import (
    SyntheticInstance,
    SyntheticTool,
    SyntheticWorld,
)
from kiln_ai.datamodel.tool_id import KilnBuiltInToolId, build_code_tool_id
from kiln_ai.run_context import (
    SyntheticInstanceContext,
    get_synthetic_instance,
    reset_synthetic_instance,
    set_synthetic_instance,
)
from kiln_ai.tools.base_tool import ToolCallContext
from kiln_ai.tools.built_in_tools.math_tools import AddTool
from kiln_ai.tools.code_tool import PythonCodeTool
from kiln_ai.tools.synthetic_tool import SyntheticToolProxy
from kiln_ai.tools.tool_registry import (
    SyntheticWorldStrictError,
    tool_from_id_and_project,
)

SCHEMA = {"type": "object", "properties": {"x": {"type": "string"}}}
REAL_CODE = "def run(x):\n    return 'real:' + x\n"
SYNTH_CODE = (
    "import os\n"
    "def run(x):\n"
    "    return 'synthetic:' + x + ':' + os.environ.get('KILN_SYNTHETIC_INSTANCE_ID', '')\n"
)


@pytest.fixture
def project(tmp_path):
    p = Project(name="proj", path=tmp_path / "proj" / "project.kiln")
    p.path.parent.mkdir(parents=True)
    p.save_to_file()
    return p


@pytest.fixture
def real_tool(project):
    ct = CodeTool(
        name="real",
        parent=project,
        tool_function_name="lookup",
        tool_description="real lookup",
        parameters_schema=SCHEMA,
        code=REAL_CODE,
    )
    ct.save_to_file()
    return ct


@pytest.fixture
def world(project, real_tool):
    w = SyntheticWorld(name="w", parent=project)
    w.save_to_file()
    t = SyntheticTool(
        name="synthetic lookup",
        parent=w,
        replaces_tool_id=build_code_tool_id(real_tool.id),
        tool_function_name="lookup",
        tool_description="synthetic lookup",
        parameters_schema=SCHEMA,
        code=SYNTH_CODE,
        timeout_seconds=10,
    )
    t.save_to_file()
    return w


def _instance(tmp_path) -> SyntheticInstance:
    return SyntheticInstance(
        instance_id="inst_test",
        world_id="w",
        fixture_id="f",
        path=str(tmp_path / "inst"),
        fixture_data_path=str(tmp_path / "fixture"),
    )


@pytest.fixture
def active_world(world, tmp_path):
    ctx = SyntheticInstanceContext(
        instance=_instance(tmp_path), world=world, bindings=world.bindings()
    )
    token = set_synthetic_instance(ctx)
    yield ctx
    reset_synthetic_instance(token)


class TestRegistrySwap:
    async def test_no_context_resolves_real_tool(self, project, real_tool):
        tool = tool_from_id_and_project(build_code_tool_id(real_tool.id), project)
        assert isinstance(tool, PythonCodeTool)
        assert not isinstance(tool, SyntheticToolProxy)

    async def test_bound_id_resolves_to_proxy_under_real_id(
        self, project, real_tool, active_world
    ):
        real_id = build_code_tool_id(real_tool.id)
        tool = tool_from_id_and_project(real_id, project)
        assert isinstance(tool, SyntheticToolProxy)
        assert await tool.id() == real_id
        assert await tool.name() == "lookup"
        assert (await tool.toolcall_definition())["function"]["name"] == "lookup"
        assert await tool.description() == "synthetic lookup"

    async def test_unbound_id_passes_through(self, project, active_world):
        assert isinstance(
            tool_from_id_and_project(KilnBuiltInToolId.ADD_NUMBERS, project), AddTool
        )

    async def test_context_reset_restores_real_resolution(
        self, project, real_tool, world, tmp_path
    ):
        real_id = build_code_tool_id(real_tool.id)
        token = set_synthetic_instance(
            SyntheticInstanceContext(
                instance=_instance(tmp_path), world=world, bindings=world.bindings()
            )
        )
        assert isinstance(
            tool_from_id_and_project(real_id, project), SyntheticToolProxy
        )
        reset_synthetic_instance(token)
        assert get_synthetic_instance() is None
        assert not isinstance(
            tool_from_id_and_project(real_id, project), SyntheticToolProxy
        )

    async def test_bound_id_without_project_raises(self, active_world, real_tool):
        with pytest.raises(ValueError, match="requires a parent project"):
            tool_from_id_and_project(build_code_tool_id(real_tool.id), None)

    async def test_direct_synthetic_id_resolves_code_tool(self, project, world):
        synthetic = world.tools()[0]
        tool = tool_from_id_and_project(
            f"kiln_tool::synthetic::{world.id}::{synthetic.id}", project
        )
        assert isinstance(tool, PythonCodeTool)
        assert await tool.id() == f"kiln_tool::synthetic::{world.id}::{synthetic.id}"

    async def test_direct_synthetic_id_missing(self, project, world):
        with pytest.raises(ValueError, match="Synthetic tool not found"):
            tool_from_id_and_project(f"kiln_tool::synthetic::{world.id}::nope", project)
        with pytest.raises(ValueError, match="Synthetic world not found"):
            tool_from_id_and_project("kiln_tool::synthetic::nope::x", project)


class TestStrictMode:
    async def test_strict_rejects_unbound_non_builtin(
        self, project, world, real_tool, tmp_path
    ):
        world.strict = True
        world.save_to_file()
        other = CodeTool(
            name="other",
            parent=project,
            tool_function_name="other",
            tool_description="d",
            parameters_schema=SCHEMA,
            code=REAL_CODE,
        )
        other.save_to_file()
        token = set_synthetic_instance(
            SyntheticInstanceContext(
                instance=_instance(tmp_path), world=world, bindings=world.bindings()
            )
        )
        try:
            with pytest.raises(SyntheticWorldStrictError, match="does not replace"):
                tool_from_id_and_project(build_code_tool_id(other.id), project)
            # Bound ids and built-ins are still fine.
            assert isinstance(
                tool_from_id_and_project(build_code_tool_id(real_tool.id), project),
                SyntheticToolProxy,
            )
            assert isinstance(
                tool_from_id_and_project(KilnBuiltInToolId.ADD_NUMBERS, project),
                AddTool,
            )
        finally:
            reset_synthetic_instance(token)


class TestProxyExecution:
    async def test_proxy_runs_synthetic_code_with_instance_env(
        self, project, real_tool, active_world
    ):
        tool = tool_from_id_and_project(build_code_tool_id(real_tool.id), project)
        result = await tool.run(
            ToolCallContext(synthetic_instance=active_world.instance), x="q"
        )
        assert result.is_error is False
        assert result.output == "synthetic:q:inst_test"

    async def test_real_tool_runs_without_context(self, project, real_tool):
        tool = tool_from_id_and_project(build_code_tool_id(real_tool.id), project)
        result = await tool.run(ToolCallContext(), x="q")
        assert result.output == "real:q"
