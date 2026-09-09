"""Tests for the synthetic world datamodel: world, tools, fixtures, instance records."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from kiln_ai.datamodel.code_tool import TOOL_CODE_FILENAME, CodeTool
from kiln_ai.datamodel.eval import (
    EvalInput,
    EvalTaskInput,
    SingleTurnEvalInputData,
    UserMessage,
)
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.synthetic_world import (
    FIXTURE_DATA_DIRNAME,
    SyntheticEnvironment,
    SyntheticFixture,
    SyntheticInstance,
    SyntheticInstanceInfo,
    SyntheticTool,
    SyntheticWorld,
    synthetic_fingerprint,
)
from kiln_ai.datamodel.task import Task
from kiln_ai.datamodel.task_output import DataSource, DataSourceType, TaskOutput
from kiln_ai.datamodel.task_run import EvalItemSource, TaskRun
from kiln_ai.datamodel.tool_id import (
    build_code_tool_id,
    build_synthetic_tool_id,
    synthetic_world_and_tool_ids_from_id,
    validate_tool_allowlist,
)

SCHEMA = {"type": "object", "properties": {"q": {"type": "string"}}}
CODE = "def run(q):\n    return q\n"
NOW = datetime(2026, 7, 14, tzinfo=timezone.utc)


@pytest.fixture
def project(tmp_path) -> Project:
    p = Project(name="proj", path=tmp_path / "proj" / "project.kiln")
    p.path.parent.mkdir(parents=True)
    p.save_to_file()
    return p


@pytest.fixture
def world(project) -> SyntheticWorld:
    w = SyntheticWorld(name="Acme World", parent=project, framework_content_hash="eng1")
    w.save_to_file()
    return w


def _tool(world, replaces="kiln_tool::code::real1", fn="lookup", **overrides):
    defaults = dict(
        name=f"synthetic {fn}",
        parent=world,
        replaces_tool_id=replaces,
        tool_function_name=fn,
        tool_description="plays a real tool",
        parameters_schema=SCHEMA,
        code=CODE,
    )
    defaults.update(overrides)
    t = SyntheticTool(**defaults)
    t.save_to_file()
    return t


def _fixture(world, name="Fixture A", frozen_time=NOW, files=("fixture.db",)):
    f = SyntheticFixture(name=name, parent=world, frozen_time=frozen_time)
    f.save_to_file()
    data = f.data_dir()
    data.mkdir()
    for fname in files:
        (data / fname).write_bytes(b"data for " + fname.encode())
    return f


class TestOnDiskLayout:
    def test_world_under_project(self, project, world):
        assert world.path == (
            project.path.parent
            / "synthetic_worlds"
            / f"{world.id} - Acme World"
            / "synthetic_world.kiln"
        )
        assert [w.id for w in project.synthetic_worlds()] == [world.id]

    def test_tool_under_world_with_sibling_code(self, world):
        t = _tool(world)
        assert t.path.parent.parent.parent == world.path.parent
        assert t.path.name == "synthetic_tool.kiln"
        assert (t.path.parent / TOOL_CODE_FILENAME).read_text() == CODE
        loaded = world.tools()[0]
        assert loaded.code == CODE
        assert loaded.replaces_tool_id == "kiln_tool::code::real1"

    def test_fixture_under_world(self, world):
        f = _fixture(world)
        assert f.path.name == "synthetic_fixture.kiln"
        assert f.data_dir() == f.path.parent / FIXTURE_DATA_DIRNAME
        loaded = world.fixtures()[0]
        assert loaded.frozen_time == NOW
        assert world.fixture_by_id(f.id).id == f.id

    def test_lib_dir(self, world):
        assert world.lib_dir() == world.path.parent / "lib"

    def test_synthetic_tools_are_not_project_code_tools(self, project, world):
        _tool(world)
        assert project.code_tools() == []


class TestSyntheticTool:
    @pytest.mark.parametrize(
        "bad",
        [
            "kiln_tool::synthetic::w::t",
            "kiln_tool::skill::s1",
            "kiln_unmanaged::slug",
        ],
    )
    def test_replaces_must_be_a_real_tool(self, world, bad):
        with pytest.raises(ValidationError, match="real, registry-resolvable"):
            _tool(world, replaces=bad)

    @pytest.mark.parametrize(
        "real",
        [
            "kiln_tool::code::abc",
            "mcp::remote::srv::do_thing",
            "mcp::local::srv::do_thing",
            "kiln_task::srv",
            "kiln_tool::add_numbers",
        ],
    )
    def test_any_real_tool_kind_can_be_replaced(self, world, real):
        assert _tool(world, replaces=real).replaces_tool_id == real

    def test_synthetic_id_round_trip(self):
        tool_id = build_synthetic_tool_id("w1", "t1")
        assert tool_id == "kiln_tool::synthetic::w1::t1"
        assert synthetic_world_and_tool_ids_from_id(tool_id) == ("w1", "t1")

    @pytest.mark.parametrize(
        "bad", ["kiln_tool::synthetic::w1", "kiln_tool::synthetic::::t1", "x"]
    )
    def test_synthetic_id_rejects_malformed(self, bad):
        with pytest.raises(ValueError):
            synthetic_world_and_tool_ids_from_id(bad)

    def test_synthetic_ids_rejected_in_allowlists(self):
        with pytest.raises(ValueError, match="Synthetic tool IDs cannot"):
            validate_tool_allowlist(
                ["kiln_tool::synthetic::w1::t1"], caller="code tools"
            )

    def test_code_tool_self_reference_still_rejected(self, project):
        ct = CodeTool(
            name="t",
            parent=project,
            tool_function_name="t",
            tool_description="d",
            parameters_schema=SCHEMA,
            code=CODE,
        )
        with pytest.raises(ValidationError, match="cannot reference itself"):
            CodeTool(
                name="t",
                parent=project,
                id=ct.id,
                tool_function_name="t",
                tool_description="d",
                parameters_schema=SCHEMA,
                code=CODE,
                tool_allowlist=[build_code_tool_id(ct.id)],
            )


class TestBindings:
    def test_bindings_map_real_ids(self, world):
        a = _tool(world, replaces="kiln_tool::code::a", fn="a")
        b = _tool(world, replaces="mcp::remote::srv::b", fn="b")
        bindings = world.bindings()
        assert bindings["kiln_tool::code::a"].id == a.id
        assert bindings["mcp::remote::srv::b"].id == b.id
        assert world.binding_for("kiln_tool::code::missing") is None

    def test_duplicate_binding_raises(self, world):
        _tool(world, fn="one")
        _tool(world, fn="two")
        with pytest.raises(ValueError, match="binds kiln_tool::code::real1 twice"):
            world.bindings()

    def test_validate_bindings_reports_name_and_schema_mismatch(self, project, world):
        real = CodeTool(
            name="real",
            parent=project,
            tool_function_name="lookup",
            tool_description="d",
            parameters_schema=SCHEMA,
            code=CODE,
        )
        real.save_to_file()
        _tool(world, replaces=build_code_tool_id(real.id), fn="lookup")
        assert world.validate_bindings(project) == []

        other = CodeTool(
            name="other",
            parent=project,
            tool_function_name="other_name",
            tool_description="d",
            parameters_schema={"type": "object", "properties": {}},
            code=CODE,
        )
        other.save_to_file()
        _tool(world, replaces=build_code_tool_id(other.id), fn="lookup2")
        warnings = world.validate_bindings(project)
        assert any("function name mismatch" in w for w in warnings)
        assert any("parameters schema differs" in w for w in warnings)

    def test_validate_bindings_missing_real_tool(self, project, world):
        _tool(world, replaces="kiln_tool::code::nope")
        assert world.validate_bindings(project) == [
            "kiln_tool::code::nope: real code tool not found in project"
        ]

    def test_validate_bindings_never_contacts_mcp(self, project, world):
        _tool(world, replaces="mcp::remote::srv::x", fn="x")
        assert world.validate_bindings(project) == []


class TestFixture:
    def test_frozen_time_must_be_tz_aware(self, world):
        with pytest.raises(ValidationError, match="timezone-aware"):
            SyntheticFixture(name="f", parent=world, frozen_time=datetime(2026, 1, 1))

    def test_require_data_dir(self, world):
        f = SyntheticFixture(name="empty", parent=world)
        f.save_to_file()
        with pytest.raises(ValueError, match="has no data/"):
            f.require_data_dir()
        f.data_dir().mkdir()
        with pytest.raises(ValueError, match="empty data/"):
            f.require_data_dir()
        (f.data_dir() / "x.db").write_bytes(b"x")
        assert f.require_data_dir() == f.data_dir()

    def test_resolve_data_file_guards_traversal(self, world):
        f = _fixture(world)
        assert f.resolve_data_file("fixture.db").name == "fixture.db"
        with pytest.raises(ValueError, match="traversal"):
            f.resolve_data_file("../synthetic_fixture.kiln")
        with pytest.raises(ValueError, match="empty"):
            f.resolve_data_file(" ")

    def test_unsaved_fixture_has_no_data_dir(self, world):
        with pytest.raises(ValueError, match="saved"):
            SyntheticFixture(name="f", parent=world).data_dir()


class TestEnvironmentAndInstance:
    def test_environment_requires_ids(self):
        with pytest.raises(ValidationError):
            SyntheticEnvironment(world_id="", fixture_id="f")
        with pytest.raises(ValidationError, match="timezone-aware"):
            SyntheticEnvironment(
                world_id="w", fixture_id="f", frozen_time=datetime(2026, 1, 1)
            )

    def test_eval_input_round_trips_environment(self, project):
        task = Task(name="t", instruction="i", parent=project)
        task.save_to_file()
        ei = EvalInput(
            parent=task,
            data=SingleTurnEvalInputData(user_message=UserMessage(text="hi")),
            synthetic_environment=SyntheticEnvironment(
                world_id="w1", fixture_id="f1", frozen_time=NOW
            ),
        )
        ei.save_to_file()
        loaded = task.eval_inputs()[0]
        assert loaded.synthetic_environment is not None
        assert loaded.synthetic_environment.fixture_id == "f1"
        assert loaded.synthetic_environment.frozen_time == NOW

    def test_eval_input_defaults_to_no_environment(self):
        ei = EvalInput(
            data=SingleTurnEvalInputData(user_message=UserMessage(text="hi"))
        )
        assert ei.synthetic_environment is None

    def _instance(self, unchanged=False):
        return SyntheticInstance(
            instance_id="inst_1",
            world_id="w1",
            fixture_id="f1",
            path="/cache/inst_1",
            fixture_data_path="/proj/fixtures/f1/data",
            world_lib_path="/proj/lib",
            frozen_time=NOW,
            framework_content_hash="eng1",
            unchanged=unchanged,
        )

    def test_effective_path_follows_unchanged(self):
        assert self._instance().effective_path == "/cache/inst_1"
        assert self._instance(unchanged=True).effective_path == "/proj/fixtures/f1/data"

    def test_sandbox_dict_is_plain_values(self):
        d = self._instance().to_sandbox_dict()
        assert d["path"] == "/cache/inst_1"
        assert d["frozen_time"] == "2026-07-14T00:00:00+00:00"
        assert d["world_lib_path"] == "/proj/lib"
        assert all(isinstance(v, (str, bool)) or v is None for v in d.values())

    def test_info_has_no_paths(self):
        info = SyntheticInstanceInfo.from_instance(self._instance())
        assert info.instance_id == "inst_1"
        assert "path" not in SyntheticInstanceInfo.model_fields
        assert "path" not in EvalTaskInput.model_json_schema()["properties"]
        assert "synthetic_instance" in EvalTaskInput.model_json_schema()["properties"]

    def test_task_run_persists_instance_and_variant(self, project):
        task = Task(name="t", instruction="i", parent=project)
        task.save_to_file()
        run = TaskRun(
            parent=task,
            input="hi",
            output=TaskOutput(
                output="out",
                source=DataSource(
                    type=DataSourceType.synthetic,
                    properties={
                        "model_name": "m",
                        "model_provider": "p",
                        "adapter_name": "a",
                    },
                    run_config_id="rc1",
                ),
            ),
            eval_source=EvalItemSource(
                source_type="eval_input", source_id="i1", variant="syn1:x"
            ),
            synthetic_instance=self._instance(),
        )
        run.save_to_file()
        loaded = TaskRun.load_from_file(run.path)
        assert loaded.eval_source.variant == "syn1:x"
        assert loaded.synthetic_instance.instance_id == "inst_1"
        eti = EvalTaskInput.from_task_run(loaded)
        assert eti.synthetic_instance is not None
        assert eti.synthetic_instance.fixture_id == "f1"

    def test_from_trace_without_instance(self, project):
        task = Task(name="t", instruction="i", parent=project)
        run = TaskRun(
            parent=task,
            input="hi",
            output=TaskOutput(
                output="out",
                source=DataSource(
                    type=DataSourceType.human, properties={"created_by": "me"}
                ),
            ),
        )
        assert EvalTaskInput.from_task_run(run).synthetic_instance is None


class TestFingerprint:
    def test_fingerprint_changes_with_each_input(self):
        base = synthetic_fingerprint("w", "f", NOW, "eng1")
        assert base.startswith("syn1:")
        assert synthetic_fingerprint("w", "f", NOW, "eng1") == base
        assert synthetic_fingerprint("w", "f2", NOW, "eng1") != base
        assert synthetic_fingerprint("w", "f", None, "eng1") != base
        assert synthetic_fingerprint("w", "f", NOW, "eng2") != base
        assert synthetic_fingerprint("w2", "f", NOW, "eng1") != base
