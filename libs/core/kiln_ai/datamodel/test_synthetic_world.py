"""Tests for the synthetic world datamodel: world, tools, environment refs, instance records."""

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
    LOCAL_FILES_LAUNCHER,
    SyntheticEnvironment,
    SyntheticInstance,
    SyntheticInstanceConnection,
    SyntheticInstanceInfo,
    SyntheticTool,
    SyntheticWorld,
    canonical_json,
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
    w = SyntheticWorld(name="Acme World", parent=project, content_version="eng1")
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


class TestOnDiskLayout:
    def test_world_under_project(self, project, world):
        assert world.path == (
            project.path.parent
            / "synthetic_worlds"
            / f"{world.id} - Acme World"
            / "synthetic_world.kiln"
        )
        assert [w.id for w in project.synthetic_worlds()] == [world.id]
        assert world.world_dir() == world.path.parent
        assert world.lib_dir() == world.path.parent / "lib"

    def test_world_defaults(self, world):
        loaded = SyntheticWorld.load_from_file(world.path)
        assert loaded.launcher == LOCAL_FILES_LAUNCHER
        assert loaded.launcher_config == {}
        assert loaded.strict is False

    def test_world_launcher_round_trip(self, project):
        w = SyntheticWorld(
            name="hosted",
            parent=project,
            launcher="matrix",
            launcher_config={"server": "https://matrix.example", "image": "acme:1"},
        )
        w.save_to_file()
        loaded = SyntheticWorld.load_from_file(w.path)
        assert loaded.launcher == "matrix"
        assert loaded.launcher_config["image"] == "acme:1"

    def test_tool_under_world_with_sibling_code(self, world):
        t = _tool(world)
        assert t.path.parent.parent.parent == world.path.parent
        assert t.path.name == "synthetic_tool.kiln"
        assert (t.path.parent / TOOL_CODE_FILENAME).read_text() == CODE
        loaded = world.tools()[0]
        assert loaded.code == CODE
        assert loaded.replaces_tool_id == "kiln_tool::code::real1"

    def test_synthetic_tools_are_not_project_code_tools(self, project, world):
        _tool(world)
        assert project.code_tools() == []


class TestSyntheticTool:
    @pytest.mark.parametrize(
        "bad",
        ["kiln_tool::synthetic::w::t", "kiln_tool::skill::s1", "kiln_unmanaged::slug"],
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

    def test_replaces_server_of_matches_only_that_servers_tools(self, world):
        assert world.replaces_server_of("mcp::remote::srv1::search") is False
        world.replaces_tool_server_id = "srv1"
        assert world.replaces_server_of("mcp::remote::srv1::search") is True
        assert world.replaces_server_of("mcp::local::srv1::search") is True
        assert world.replaces_server_of("mcp::remote::srv2::search") is False
        assert world.replaces_server_of("kiln_tool::code::srv1") is False

    def test_validate_bindings_warns_on_missing_replaced_server(self, project, world):
        world.replaces_tool_server_id = "srv-missing"
        warnings = world.validate_bindings(project)
        assert any("srv-missing" in w and "not found" in w for w in warnings)

    def test_validate_bindings_never_contacts_mcp(self, project, world):
        _tool(world, replaces="mcp::remote::srv::x", fn="x")
        assert world.validate_bindings(project) == []


class TestEnvironmentAndInstance:
    def test_environment_requires_world_id(self):
        with pytest.raises(ValidationError):
            SyntheticEnvironment(world_id="")
        assert SyntheticEnvironment(world_id="w").config == {}

    def test_environment_config_is_opaque_json(self):
        env = SyntheticEnvironment(
            world_id="w", config={"fixture_id": "f", "seed": 42, "opts": {"a": [1, 2]}}
        )
        assert env.config["opts"] == {"a": [1, 2]}

    def test_eval_input_round_trips_environment(self, project):
        task = Task(name="t", instruction="i", parent=project)
        task.save_to_file()
        ei = EvalInput(
            parent=task,
            data=SingleTurnEvalInputData(user_message=UserMessage(text="hi")),
            synthetic_environment=SyntheticEnvironment(
                world_id="w1",
                config={"fixture_id": "f1", "frozen_time": NOW.isoformat()},
            ),
        )
        ei.save_to_file()
        loaded = task.eval_inputs()[0]
        assert loaded.synthetic_environment is not None
        assert loaded.synthetic_environment.config["fixture_id"] == "f1"

    def test_eval_input_defaults_to_no_environment(self):
        ei = EvalInput(
            data=SingleTurnEvalInputData(user_message=UserMessage(text="hi"))
        )
        assert ei.synthetic_environment is None

    def _instance(self, **overrides):
        base = dict(
            instance_id="inst_1",
            world_id="w1",
            config={"fixture_id": "f1"},
            path="/cache/inst_1",
            source_path="/proj/fixtures/f1",
            world_lib_path="/proj/lib",
            metadata={"fixture_id": "f1", "frozen_time": NOW.isoformat()},
            content_version="eng1",
        )
        base.update(overrides)
        return SyntheticInstance(**base)

    def test_effective_path_follows_unchanged(self):
        assert self._instance().effective_path == "/cache/inst_1"
        assert self._instance(unchanged=True).effective_path == "/proj/fixtures/f1"
        hosted = self._instance(
            path=None,
            source_path=None,
            connection=SyntheticInstanceConnection(
                url="http://h/1", headers={"Authorization": "Bearer s3cret"}
            ),
        )
        assert hosted.effective_path is None
        assert hosted.connection is not None and hosted.connection.url == "http://h/1"

    def test_connection_credentials_never_serialize(self):
        hosted = self._instance(
            path=None,
            connection=SyntheticInstanceConnection(
                transport="stdio",
                command="world-server",
                args=["--inst", "1"],
                env={"TOKEN": "s3cret"},
                headers={"Authorization": "Bearer s3cret"},
            ),
        )
        dumped = hosted.model_dump()["connection"]
        assert dumped["command"] == "world-server" and dumped["args"] == ["--inst", "1"]
        assert "headers" not in dumped and "env" not in dumped
        assert "s3cret" not in hosted.model_dump_json()
        reloaded = SyntheticInstance.model_validate_json(hosted.model_dump_json())
        assert reloaded.connection is not None
        assert reloaded.connection.headers == {} and reloaded.connection.env == {}
        # The in-memory record handed to tools keeps them.
        sandbox = hosted.to_sandbox_dict()["connection"]
        assert isinstance(sandbox, dict)
        assert sandbox["env"] == {"TOKEN": "s3cret"}
        assert sandbox["headers"] == {"Authorization": "Bearer s3cret"}

    def test_changes_and_validity_round_trip(self):
        inst = self._instance(
            changes={"rows": [{"table": "t", "op": "update"}]},
            valid=False,
            invalid_reason="world gap on tool x",
        )
        again = SyntheticInstance.model_validate(inst.model_dump())
        assert again.changes == {"rows": [{"table": "t", "op": "update"}]}
        assert again.valid is False and again.invalid_reason == "world gap on tool x"
        info = SyntheticInstanceInfo.from_instance(inst)
        assert info.valid is False and info.invalid_reason == "world gap on tool x"
        assert "changes" not in SyntheticInstanceInfo.model_fields
        assert inst.to_sandbox_dict()["changes"] == {
            "rows": [{"table": "t", "op": "update"}]
        }

    def test_sandbox_dict_is_plain_json(self):
        d = self._instance().to_sandbox_dict()
        assert d["path"] == "/cache/inst_1"
        assert d["config"] == {"fixture_id": "f1"}
        assert d["metadata"]["frozen_time"] == NOW.isoformat()
        assert d["world_lib_path"] == "/proj/lib"
        canonical_json(d)  # JSON-serializable

    def test_info_has_no_locations(self):
        info = SyntheticInstanceInfo.from_instance(self._instance())
        assert info.instance_id == "inst_1"
        assert info.metadata["fixture_id"] == "f1"
        for field in ("path", "connection", "source_path", "changes"):
            assert field not in SyntheticInstanceInfo.model_fields
        props = EvalTaskInput.model_json_schema()["properties"]
        assert "synthetic_instance" in props
        defs = EvalTaskInput.model_json_schema().get("$defs", {})
        assert "path" not in defs["SyntheticInstanceInfo"]["properties"]

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
                source_type="eval_input", source_id="i1", variant="syn2:x"
            ),
            synthetic_instance=self._instance(),
        )
        run.save_to_file()
        loaded = TaskRun.load_from_file(run.path)
        assert loaded.eval_source.variant == "syn2:x"
        assert loaded.synthetic_instance.instance_id == "inst_1"
        eti = EvalTaskInput.from_task_run(loaded)
        assert eti.synthetic_instance is not None
        assert eti.synthetic_instance.config == {"fixture_id": "f1"}

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
        base = synthetic_fingerprint("w", {"fixture_id": "f"}, "eng1")
        assert base.startswith("syn2:")
        assert synthetic_fingerprint("w", {"fixture_id": "f"}, "eng1") == base
        assert synthetic_fingerprint("w", {"fixture_id": "f2"}, "eng1") != base
        assert (
            synthetic_fingerprint("w", {"fixture_id": "f", "seed": 1}, "eng1") != base
        )
        assert synthetic_fingerprint("w", {"fixture_id": "f"}, "eng2") != base
        assert synthetic_fingerprint("w2", {"fixture_id": "f"}, "eng1") != base

    def test_fingerprint_is_order_independent(self):
        assert synthetic_fingerprint(
            "w", {"a": 1, "b": 2}, None
        ) == synthetic_fingerprint("w", {"b": 2, "a": 1}, None)
