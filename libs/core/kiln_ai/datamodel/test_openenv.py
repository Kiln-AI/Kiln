"""Tests for the OpenEnv datamodel: OpenEnv server records, resets, episode records and OpenEnv tool ids."""

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
from kiln_ai.datamodel.openenv import (
    NamedResetKwargs,
    OpenEnvEpisode,
    OpenEnvReset,
    OpenEnvServer,
    OpenEnvTool,
)
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.task import Task
from kiln_ai.datamodel.task_output import DataSource, DataSourceType, TaskOutput
from kiln_ai.datamodel.task_run import EvalItemSource, TaskRun
from kiln_ai.datamodel.tool_id import (
    build_code_tool_id,
    build_openenv_tool_id,
    openenv_and_tool_name_from_id,
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
def openenv_server(project) -> OpenEnvServer:
    openenv_server = OpenEnvServer(name="Acme Environment", parent=project)
    openenv_server.save_to_file()
    return openenv_server


class TestOnDiskLayout:
    def test_openenv_server_under_project(self, project, openenv_server):
        assert openenv_server.path is not None
        assert (
            openenv_server.path.parent.parent == project.path.parent / "openenv_servers"
        )
        assert openenv_server.path.name == "openenv_server.kiln"
        assert openenv_server.model_type == "openenv_server"
        assert project.openenv_servers()[0].id == openenv_server.id
        loaded = OpenEnvServer.from_id_and_parent_path(openenv_server.id, project.path)
        assert loaded is not None and loaded.name == "Acme Environment"

    def test_openenv_server_defaults(self, openenv_server):
        assert openenv_server.url is None
        assert openenv_server.description is None
        assert openenv_server.is_archived is False

    def test_openenv_server_round_trip(self, project):
        openenv_server = OpenEnvServer(
            name="Remote",
            parent=project,
            url="http://localhost:8123",
            description="hosted",
        )
        openenv_server.save_to_file()
        assert openenv_server.id is not None
        loaded = OpenEnvServer.from_id_and_parent_path(openenv_server.id, project.path)
        assert loaded is not None
        assert loaded.url == "http://localhost:8123"
        assert loaded.description == "hosted"

    def test_archive_round_trip(self, project):
        openenv_server = OpenEnvServer(name="Old", parent=project, is_archived=True)
        openenv_server.save_to_file()
        assert openenv_server.id is not None
        loaded = OpenEnvServer.from_id_and_parent_path(openenv_server.id, project.path)
        assert loaded is not None
        assert loaded.is_archived is True


def test_project_lists_its_openenv_servers(project):
    openenv_server = OpenEnvServer(
        name="Notes", parent=project, url="http://127.0.0.1:8000"
    )
    openenv_server.save_to_file()
    assert [saved.id for saved in project.openenv_servers()] == [openenv_server.id]


class TestNamedResetKwargs:
    def test_default_empty(self, openenv_server):
        assert openenv_server.named_reset_kwargs == []

    def test_round_trip_preserves_order_and_nested_json(self, project):
        options = [
            NamedResetKwargs(
                name="Acme Manager",
                reset_kwargs={"company": "acme", "user": {"role": "manager"}},
            ),
            NamedResetKwargs(
                name="Beta Tech",
                description="Beta's tech account",
                reset_kwargs={"seeds": [1, 2, None]},
            ),
            NamedResetKwargs(name="Empty"),
        ]
        env = OpenEnvServer(name="Opts", parent=project, named_reset_kwargs=options)
        env.save_to_file()
        assert env.id is not None
        loaded = OpenEnvServer.from_id_and_parent_path(env.id, project.path)
        assert loaded is not None
        assert loaded.named_reset_kwargs == options
        assert loaded.named_reset_kwargs[2].reset_kwargs == {}
        assert loaded.named_reset_kwargs[1].description == "Beta's tech account"
        assert loaded.named_reset_kwargs[2].description is None

    def test_duplicate_names_rejected(self):
        with pytest.raises(
            ValidationError,
            match="An Environment Preset named Acme Manager already exists",
        ):
            OpenEnvServer(
                name="E",
                named_reset_kwargs=[
                    NamedResetKwargs(name="Acme Manager"),
                    NamedResetKwargs(name=" Acme Manager  "),
                ],
            )

    def test_names_differing_by_case_are_distinct(self):
        env = OpenEnvServer(
            name="E",
            named_reset_kwargs=[
                NamedResetKwargs(name="acme"),
                NamedResetKwargs(name="Acme"),
            ],
        )
        assert [o.name for o in env.named_reset_kwargs] == ["acme", "Acme"]

    def test_duplicate_rejected_on_assignment(self, openenv_server):
        with pytest.raises(ValidationError, match="named Beta already exists"):
            openenv_server.named_reset_kwargs = [
                NamedResetKwargs(name="Beta"),
                NamedResetKwargs(name="Beta"),
            ]

    @pytest.mark.parametrize("reset_kwargs", [[1, 2], "acme", 3, None])
    def test_non_object_reset_kwargs_rejected(self, reset_kwargs):
        with pytest.raises(ValidationError):
            NamedResetKwargs(name="Acme", reset_kwargs=reset_kwargs)

    @pytest.mark.parametrize("name", ["", "   ", "x" * 121])
    def test_name_bounds(self, name):
        with pytest.raises(ValidationError):
            NamedResetKwargs(name=name)

    def test_name_stored_stripped(self):
        assert NamedResetKwargs(name="  Acme  ").name == "Acme"
        assert NamedResetKwargs(name="x" * 120).name == "x" * 120


class TestOpenEnvTool:
    def test_name_required(self):
        with pytest.raises(ValidationError):
            OpenEnvTool(name="")


class TestToolIds:
    def test_openenv_tool_id_round_trip(self):
        tool_id = build_openenv_tool_id("openenv1", "lookup")
        assert tool_id == "kiln_tool::openenv::openenv1::lookup"
        assert openenv_and_tool_name_from_id(tool_id) == ("openenv1", "lookup")

    @pytest.mark.parametrize(
        "bad", ["kiln_tool::openenv::openenv1", "kiln_tool::openenv::::t1", "x"]
    )
    def test_openenv_tool_id_rejects_malformed(self, bad):
        with pytest.raises(ValueError):
            openenv_and_tool_name_from_id(bad)

    def test_openenv_tool_ids_accepted_in_allowlists(self):
        validate_tool_allowlist(
            ["kiln_tool::openenv::openenv1::t1"], caller="code tools"
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


class TestResetAndEpisode:
    def test_reset_requires_openenv_server_id(self):
        with pytest.raises(ValidationError):
            OpenEnvReset(openenv_server_id="")
        assert OpenEnvReset(openenv_server_id="openenv1").reset_kwargs == {}

    def test_reset_kwargs_are_opaque_json(self):
        reset = OpenEnvReset(
            openenv_server_id="openenv1",
            reset_kwargs={"fixture_id": "f", "seed": 42, "opts": {"a": [1, 2]}},
        )
        assert reset.reset_kwargs["opts"] == {"a": [1, 2]}

    def test_eval_input_round_trips_openenv_reset(self, project):
        task = Task(name="t", instruction="i", parent=project)
        task.save_to_file()
        ei = EvalInput(
            parent=task,
            data=SingleTurnEvalInputData(user_message=UserMessage(text="hi")),
            openenv_reset=OpenEnvReset(
                openenv_server_id="openenv1",
                reset_kwargs={"fixture_id": "f1", "frozen_time": NOW.isoformat()},
            ),
        )
        ei.save_to_file()
        loaded = task.eval_inputs()[0]
        assert loaded.openenv_reset is not None
        assert loaded.openenv_reset.reset_kwargs["fixture_id"] == "f1"

    def test_eval_input_defaults_to_no_openenv_reset(self):
        ei = EvalInput(
            data=SingleTurnEvalInputData(user_message=UserMessage(text="hi"))
        )
        assert ei.openenv_reset is None

    def _episode(self, **overrides: Any) -> OpenEnvEpisode:
        base: dict[str, Any] = dict(
            reset=OpenEnvReset(
                openenv_server_id="openenv1", reset_kwargs={"fixture_id": "f1"}
            ),
            episode_id="ep_1",
            openenv_version="acme@1.0.0",
            reset_metadata={"fixture_id": "f1", "frozen_time": NOW.isoformat()},
        )
        base.update(overrides)
        return OpenEnvEpisode(**base)

    def test_episode_defaults(self):
        ep = self._episode()
        assert ep.final_state is None
        assert list(OpenEnvEpisode.model_fields) == [
            "reset",
            "episode_id",
            "openenv_version",
            "reset_metadata",
            "final_state",
        ]

    def test_final_state_round_trip(self):
        ep = self._episode(final_state={"notes": ["a", "b"], "step_count": 2})
        again = OpenEnvEpisode.model_validate_json(ep.model_dump_json())
        assert again.final_state == {"notes": ["a", "b"], "step_count": 2}
        assert again.reset == OpenEnvReset(
            openenv_server_id="openenv1", reset_kwargs={"fixture_id": "f1"}
        )

    def test_sandbox_dict_is_plain_json(self):
        d = self._episode(final_state={"notes": []}).to_sandbox_dict()
        assert set(d) == {
            "reset",
            "episode_id",
            "openenv_version",
            "reset_metadata",
            "final_state",
        }
        assert d["reset"] == {
            "openenv_server_id": "openenv1",
            "reset_kwargs": {"fixture_id": "f1"},
        }
        assert d["reset_metadata"] == {
            "fixture_id": "f1",
            "frozen_time": NOW.isoformat(),
        }
        assert d["openenv_version"] == "acme@1.0.0"
        assert d["final_state"] == {"notes": []}
        json.dumps(d)  # JSON-serializable

    def test_eval_task_input_carries_the_full_episode(self):
        ep = self._episode(final_state={"big": list(range(100))})
        eval_input = EvalTaskInput(final_message="done", openenv_episode=ep)
        restored = EvalTaskInput.model_validate_json(eval_input.model_dump_json())
        assert restored.openenv_episode == ep

    def test_files_saved_before_openenvs_still_load(self):
        """Records written before environments existed carry none of the new fields."""
        legacy_input = EvalInput.model_validate(
            {
                "data": {
                    "type": "single_turn",
                    "user_message": {"text": "hi"},
                }
            }
        )
        assert legacy_input.openenv_reset is None
        legacy_run = TaskRun.model_validate(
            {"input": "hi", "output": {"output": "hello"}}
        )
        assert legacy_run.openenv_episode is None

    def test_task_run_persists_openenv_episode(self, project):
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
            openenv_episode=self._episode(final_state={"notes": ["a"]}),
        )
        run.save_to_file()
        assert run.path is not None
        loaded = TaskRun.load_from_file(run.path)
        assert loaded.eval_source is not None
        assert loaded.openenv_episode is not None
        assert loaded.openenv_episode.openenv_version == "acme@1.0.0"
        assert loaded.openenv_episode.episode_id == "ep_1"
        assert loaded.openenv_episode.final_state == {"notes": ["a"]}
        eti = EvalTaskInput.from_task_run(loaded)
        assert eti.openenv_episode is not None
        assert eti.openenv_episode.reset.reset_kwargs == {"fixture_id": "f1"}

    def test_from_trace_without_openenv_episode(self, project):
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
        assert EvalTaskInput.from_task_run(run).openenv_episode is None
