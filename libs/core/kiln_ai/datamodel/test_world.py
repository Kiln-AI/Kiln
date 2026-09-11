"""Tests for the world datamodel: worlds, environment refs, instance records."""

import json
from datetime import datetime, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from kiln_ai.datamodel.code_tool import CodeTool
from kiln_ai.datamodel.eval import (
    EvalInput,
    EvalTaskInput,
    SingleTurnEvalInputData,
    UserMessage,
)
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.task import Task
from kiln_ai.datamodel.task_output import DataSource, DataSourceType, TaskOutput
from kiln_ai.datamodel.task_run import EvalItemSource, TaskRun
from kiln_ai.datamodel.tool_id import (
    build_code_tool_id,
    build_world_tool_id,
    validate_tool_allowlist,
    world_and_tool_name_from_id,
)
from kiln_ai.datamodel.world import (
    Episode,
    OpenEnvTool,
    World,
    WorldReset,
)

SCHEMA = {"type": "object", "properties": {"q": {"type": "string"}}}
CODE = "def run(q):\n    return q\n"
NOW = datetime(2026, 7, 14, tzinfo=timezone.utc)


@pytest.fixture
def project(tmp_path) -> Project:
    path = tmp_path / "proj" / "project.kiln"
    path.parent.mkdir(parents=True)
    p = Project(name="proj", path=path)
    p.save_to_file()
    return p


@pytest.fixture
def world(project) -> World:
    w = World(name="Acme World", parent=project)
    w.save_to_file()
    return w


class TestOnDiskLayout:
    def test_world_under_project(self, project, world):
        assert world.path is not None
        assert world.path.parent.parent == project.path.parent / "worlds"
        assert world.path.name == "world.kiln"
        assert project.worlds()[0].id == world.id
        loaded = World.from_id_and_parent_path(world.id, project.path)
        assert loaded is not None and loaded.name == "Acme World"

    def test_world_defaults(self, world):
        assert world.env_url is None
        assert world.description is None

    def test_world_round_trip(self, project):
        w = World(
            name="Remote",
            parent=project,
            env_url="http://localhost:8123",
            description="hosted",
        )
        w.save_to_file()
        assert w.id is not None
        loaded = World.from_id_and_parent_path(w.id, project.path)
        assert loaded is not None
        assert loaded.env_url == "http://localhost:8123"
        assert loaded.description == "hosted"


class TestOpenEnvTool:
    def test_toolcall_definition_shape(self):
        tool = OpenEnvTool(
            name="lookup", description="finds things", input_schema=SCHEMA
        )
        assert tool.toolcall_definition() == {
            "type": "function",
            "function": {
                "name": "lookup",
                "description": "finds things",
                "parameters": SCHEMA,
            },
        }

    def test_empty_schema_defaults_to_object(self):
        tool = OpenEnvTool(name="ping")
        definition = tool.toolcall_definition()
        assert definition["function"]["description"] == ""
        assert definition["function"]["parameters"] == {
            "type": "object",
            "properties": {},
        }

    def test_name_required(self):
        with pytest.raises(ValidationError):
            OpenEnvTool(name="")


class TestToolIds:
    def test_synthetic_id_round_trip(self):
        tool_id = build_world_tool_id("w1", "lookup")
        assert tool_id == "kiln_tool::world::w1::lookup"
        assert world_and_tool_name_from_id(tool_id) == ("w1", "lookup")

    @pytest.mark.parametrize(
        "bad", ["kiln_tool::world::w1", "kiln_tool::world::::t1", "x"]
    )
    def test_synthetic_id_rejects_malformed(self, bad):
        with pytest.raises(ValueError):
            world_and_tool_name_from_id(bad)

    def test_world_tool_ids_accepted_in_allowlists(self):
        validate_tool_allowlist(["kiln_tool::world::w1::t1"], caller="code tools")

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


class TestEnvironmentAndInstance:
    def test_environment_requires_world_id(self):
        with pytest.raises(ValidationError):
            WorldReset(world_id="")
        assert WorldReset(world_id="w").reset_kwargs == {}

    def test_environment_config_is_opaque_json(self):
        env = WorldReset(
            world_id="w",
            reset_kwargs={"fixture_id": "f", "seed": 42, "opts": {"a": [1, 2]}},
        )
        assert env.reset_kwargs["opts"] == {"a": [1, 2]}

    def test_eval_input_round_trips_environment(self, project):
        task = Task(name="t", instruction="i", parent=project)
        task.save_to_file()
        ei = EvalInput(
            parent=task,
            data=SingleTurnEvalInputData(user_message=UserMessage(text="hi")),
            world_reset=WorldReset(
                world_id="w1",
                reset_kwargs={"fixture_id": "f1", "frozen_time": NOW.isoformat()},
            ),
        )
        ei.save_to_file()
        loaded = task.eval_inputs()[0]
        assert loaded.world_reset is not None
        assert loaded.world_reset.reset_kwargs["fixture_id"] == "f1"

    def test_eval_input_defaults_to_no_environment(self):
        ei = EvalInput(
            data=SingleTurnEvalInputData(user_message=UserMessage(text="hi"))
        )
        assert ei.world_reset is None

    def _instance(self, **overrides: Any) -> Episode:
        base: dict[str, Any] = dict(
            episode_id="ep_1",
            world_id="w1",
            reset_kwargs={"fixture_id": "f1"},
            metadata={"fixture_id": "f1", "frozen_time": NOW.isoformat()},
        )
        base.update(overrides)
        return Episode(**base)

    def test_instance_defaults(self):
        inst = self._instance()
        assert inst.state is None
        assert set(Episode.model_fields) == {
            "episode_id",
            "world_id",
            "world_version",
            "reset_kwargs",
            "metadata",
            "state",
        }

    def test_state_round_trip(self):
        inst = self._instance(state={"notes": ["a", "b"], "step_count": 2})
        again = Episode.model_validate_json(inst.model_dump_json())
        assert again.state == {"notes": ["a", "b"], "step_count": 2}

    def test_sandbox_dict_is_plain_json(self):
        d = self._instance(state={"notes": []}).to_sandbox_dict()
        assert set(d) == {
            "episode_id",
            "world_id",
            "world_version",
            "reset_kwargs",
            "metadata",
            "state",
        }
        assert d["reset_kwargs"] == {"fixture_id": "f1"}
        assert d["metadata"] == {"fixture_id": "f1", "frozen_time": NOW.isoformat()}
        assert d["state"] == {"notes": []}
        json.dumps(d)  # JSON-serializable

    def test_eval_task_input_carries_the_full_episode(self):
        inst = self._instance(state={"big": list(range(100))})
        defs = EvalTaskInput.model_json_schema().get("$defs", {})
        assert "state" in defs["Episode"]["properties"]
        assert "EpisodeInfo" not in defs
        assert inst.to_sandbox_dict()["state"] == {"big": list(range(100))}

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
            eval_source=EvalItemSource(source_type="eval_input", source_id="i1"),
            episode=self._instance(state={"notes": ["a"]}, world_version="acme@1.0.0"),
        )
        run.save_to_file()
        assert run.path is not None
        loaded = TaskRun.load_from_file(run.path)
        assert loaded.eval_source is not None
        assert loaded.episode is not None
        assert loaded.episode.world_version == "acme@1.0.0"
        assert loaded.episode.episode_id == "ep_1"
        assert loaded.episode.state == {"notes": ["a"]}
        eti = EvalTaskInput.from_task_run(loaded)
        assert eti.episode is not None
        assert eti.episode.reset_kwargs == {"fixture_id": "f1"}

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
        assert EvalTaskInput.from_task_run(run).episode is None
