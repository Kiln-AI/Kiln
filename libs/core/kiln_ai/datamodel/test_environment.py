"""Tests for the environment datamodel: environments, resets, episode records and environment tool ids."""

import json
from datetime import datetime, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from kiln_ai.datamodel.code_tool import CodeTool
from kiln_ai.datamodel.environment import (
    Environment,
    EnvironmentEpisode,
    EnvironmentReset,
    OpenEnvTool,
)
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
    build_env_tool_id,
    env_and_tool_name_from_id,
    validate_tool_allowlist,
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
def environment(project) -> Environment:
    w = Environment(name="Acme Environment", parent=project)
    w.save_to_file()
    return w


class TestOnDiskLayout:
    def test_environment_under_project(self, project, environment):
        assert environment.path is not None
        assert environment.path.parent.parent == project.path.parent / "environments"
        assert environment.path.name == "environment.kiln"
        assert project.environments()[0].id == environment.id
        loaded = Environment.from_id_and_parent_path(environment.id, project.path)
        assert loaded is not None and loaded.name == "Acme Environment"

    def test_environment_defaults(self, environment):
        assert environment.env_url is None
        assert environment.description is None

    def test_environment_round_trip(self, project):
        w = Environment(
            name="Remote",
            parent=project,
            env_url="http://localhost:8123",
            description="hosted",
        )
        w.save_to_file()
        assert w.id is not None
        loaded = Environment.from_id_and_parent_path(w.id, project.path)
        assert loaded is not None
        assert loaded.env_url == "http://localhost:8123"
        assert loaded.description == "hosted"


def test_project_lists_its_environments(project):
    environment = Environment(name="w", parent=project, env_url="http://127.0.0.1:8000")
    environment.save_to_file()
    assert [w.id for w in project.environments()] == [environment.id]


class TestOpenEnvTool:
    def test_name_required(self):
        with pytest.raises(ValidationError):
            OpenEnvTool(name="")


class TestToolIds:
    def test_env_tool_id_round_trip(self):
        tool_id = build_env_tool_id("w1", "lookup")
        assert tool_id == "kiln_tool::env::w1::lookup"
        assert env_and_tool_name_from_id(tool_id) == ("w1", "lookup")

    @pytest.mark.parametrize("bad", ["kiln_tool::env::w1", "kiln_tool::env::::t1", "x"])
    def test_env_tool_id_rejects_malformed(self, bad):
        with pytest.raises(ValueError):
            env_and_tool_name_from_id(bad)

    def test_env_tool_ids_accepted_in_allowlists(self):
        validate_tool_allowlist(["kiln_tool::env::w1::t1"], caller="code tools")

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


class TestResetAndEpisode:
    def test_reset_requires_environment_id(self):
        with pytest.raises(ValidationError):
            EnvironmentReset(environment_id="")
        assert EnvironmentReset(environment_id="w").reset_kwargs == {}

    def test_reset_kwargs_are_opaque_json(self):
        env = EnvironmentReset(
            environment_id="w",
            reset_kwargs={"fixture_id": "f", "seed": 42, "opts": {"a": [1, 2]}},
        )
        assert env.reset_kwargs["opts"] == {"a": [1, 2]}

    def test_eval_input_round_trips_env_reset(self, project):
        task = Task(name="t", instruction="i", parent=project)
        task.save_to_file()
        ei = EvalInput(
            parent=task,
            data=SingleTurnEvalInputData(user_message=UserMessage(text="hi")),
            env_reset=EnvironmentReset(
                environment_id="w1",
                reset_kwargs={"fixture_id": "f1", "frozen_time": NOW.isoformat()},
            ),
        )
        ei.save_to_file()
        loaded = task.eval_inputs()[0]
        assert loaded.env_reset is not None
        assert loaded.env_reset.reset_kwargs["fixture_id"] == "f1"

    def test_eval_input_defaults_to_no_env_reset(self):
        ei = EvalInput(
            data=SingleTurnEvalInputData(user_message=UserMessage(text="hi"))
        )
        assert ei.env_reset is None

    def _episode(self, **overrides: Any) -> EnvironmentEpisode:
        base: dict[str, Any] = dict(
            reset=EnvironmentReset(
                environment_id="w1", reset_kwargs={"fixture_id": "f1"}
            ),
            episode_id="ep_1",
            env_version="acme@1.0.0",
            reset_metadata={"fixture_id": "f1", "frozen_time": NOW.isoformat()},
        )
        base.update(overrides)
        return EnvironmentEpisode(**base)

    def test_episode_defaults(self):
        ep = self._episode()
        assert ep.final_state is None
        assert list(EnvironmentEpisode.model_fields) == [
            "reset",
            "episode_id",
            "env_version",
            "reset_metadata",
            "final_state",
        ]

    def test_final_state_round_trip(self):
        ep = self._episode(final_state={"notes": ["a", "b"], "step_count": 2})
        again = EnvironmentEpisode.model_validate_json(ep.model_dump_json())
        assert again.final_state == {"notes": ["a", "b"], "step_count": 2}
        assert again.reset == EnvironmentReset(
            environment_id="w1", reset_kwargs={"fixture_id": "f1"}
        )

    def test_sandbox_dict_is_plain_json(self):
        d = self._episode(final_state={"notes": []}).to_sandbox_dict()
        assert set(d) == {
            "reset",
            "episode_id",
            "env_version",
            "reset_metadata",
            "final_state",
        }
        assert d["reset"] == {
            "environment_id": "w1",
            "reset_kwargs": {"fixture_id": "f1"},
        }
        assert d["reset_metadata"] == {
            "fixture_id": "f1",
            "frozen_time": NOW.isoformat(),
        }
        assert d["env_version"] == "acme@1.0.0"
        assert d["final_state"] == {"notes": []}
        json.dumps(d)  # JSON-serializable

    def test_eval_task_input_carries_the_full_episode(self):
        ep = self._episode(final_state={"big": list(range(100))})
        eval_input = EvalTaskInput(final_message="done", env_episode=ep)
        restored = EvalTaskInput.model_validate_json(eval_input.model_dump_json())
        assert restored.env_episode == ep

    def test_files_saved_before_environments_still_load(self):
        """Records written before environments existed carry none of the new fields."""
        legacy_input = EvalInput.model_validate(
            {
                "data": {
                    "type": "single_turn",
                    "user_message": {"text": "hi"},
                }
            }
        )
        assert legacy_input.env_reset is None
        legacy_run = TaskRun.model_validate(
            {"input": "hi", "output": {"output": "hello"}}
        )
        assert legacy_run.env_episode is None

    def test_task_run_persists_env_episode(self, project):
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
            env_episode=self._episode(final_state={"notes": ["a"]}),
        )
        run.save_to_file()
        assert run.path is not None
        loaded = TaskRun.load_from_file(run.path)
        assert loaded.eval_source is not None
        assert loaded.env_episode is not None
        assert loaded.env_episode.env_version == "acme@1.0.0"
        assert loaded.env_episode.episode_id == "ep_1"
        assert loaded.env_episode.final_state == {"notes": ["a"]}
        eti = EvalTaskInput.from_task_run(loaded)
        assert eti.env_episode is not None
        assert eti.env_episode.reset.reset_kwargs == {"fixture_id": "f1"}

    def test_from_trace_without_env_episode(self, project):
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
        assert EvalTaskInput.from_task_run(run).env_episode is None
