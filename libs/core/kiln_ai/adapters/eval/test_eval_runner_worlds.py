"""End-to-end runner tests against a world.

The world is the test OpenEnv environment from `kiln_ai.worlds.testing`: one
tool, `append_note`, that records a note and pays a reward; `reset()` starts an
episode. The world run config lists the environment's tool
by its `kiln_tool::world::<world_id>::append_note` id; a second run config lists a
project code tool with the same function name for inputs without an environment. Nothing
is swapped: the runner refuses a job whose run config and input disagree. Generation
is stubbed at the model boundary only: the fake `run_task` resolves the run config's
tool through the registry (so the proxy runs for real) and calls it once.
"""

import asyncio
import re
from typing import ClassVar
from unittest.mock import patch

import pytest

from kiln_ai.adapters.eval.base_eval import BaseV2EvalBridge
from kiln_ai.adapters.eval.eval_runner import EvalRunner
from kiln_ai.datamodel.code_tool import CodeTool
from kiln_ai.datamodel.datamodel_enums import (
    StructuredOutputMode,
    TaskOutputRatingType,
)
from kiln_ai.datamodel.eval import (
    CodeEvalProperties,
    Eval,
    EvalConfig,
    EvalConfigType,
    EvalInput,
    EvalInputSplit,
    EvalOutputScore,
    EvalTaskInput,
    ExactMatchProperties,
    MultiTurnDriveConfig,
    MultiTurnSyntheticEvalInputData,
    SingleTurnEvalInputData,
    SyntheticUserInfo,
    UserMessage,
    V2EvalResult,
)
from kiln_ai.datamodel.eval_splits import resolve_split
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties, ToolsRunConfig
from kiln_ai.datamodel.task import Task, TaskRunConfig
from kiln_ai.datamodel.task_output import DataSource, DataSourceType, TaskOutput
from kiln_ai.datamodel.task_run import TaskRun
from kiln_ai.datamodel.tool_id import build_code_tool_id, build_world_tool_id
from kiln_ai.datamodel.world import World, WorldReset
from kiln_ai.run_context import get_episode
from kiln_ai.synthetic_user.drive_loop import DriveCaseResult
from kiln_ai.tools.base_tool import ToolCallContext
from kiln_ai.tools.tool_registry import tool_from_id
from kiln_ai.worlds.session_manager import OpenEnvSessionManager
from kiln_ai.worlds.testing import ENV_NAME, free_port, serve_in_thread

SCHEMA = {"type": "object", "properties": {"note": {"type": "string"}}}
CLOCK_A = "2026-07-14T00:00:00+00:00"
CLOCK_B = "2025-01-01T00:00:00+00:00"


@pytest.fixture
def project(tmp_path):
    p = Project(name="proj", path=tmp_path / "proj" / "project.kiln")
    p.path.parent.mkdir(parents=True)
    p.save_to_file()
    return p


@pytest.fixture
def project_tool(project):
    """A project tool with the same function name as the environment's: for inputs
    without an environment. Never swapped."""
    ct = CodeTool(
        name="real append",
        parent=project,
        tool_function_name="append_note",
        tool_description="appends a note",
        parameters_schema=SCHEMA,
        code="def run(note):\n    return 'real'\n",
    )
    ct.save_to_file()
    return ct


@pytest.fixture
def other_tool(project):
    """A project tool the environment does not serve: always allowed alongside the
    world's tools, even for an input that requires its world."""
    ct = CodeTool(
        name="real write",
        parent=project,
        tool_function_name="write_note",
        tool_description="writes a note",
        parameters_schema=SCHEMA,
        code="def run(note):\n    return 'real-write'\n",
    )
    ct.save_to_file()
    return ct


@pytest.fixture
def env_server():
    with serve_in_thread() as base_url:
        yield base_url


@pytest.fixture
def world(project, env_server):
    w = World(name="World", parent=project, env_url=env_server)
    w.save_to_file()
    return w


@pytest.fixture
async def session_manager(tmp_path):
    session_manager = OpenEnvSessionManager()
    try:
        yield session_manager
    finally:
        await session_manager.shutdown()


@pytest.fixture
def task(project):
    t = Task(name="task", instruction="write a note", parent=project)
    t.save_to_file()
    return t


def _run_config(task, tool_ids, name="rc"):
    rc = TaskRunConfig(
        name=name,
        parent=task,
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name="openai",
            prompt_id="simple_prompt_builder",
            structured_output_mode=StructuredOutputMode.json_schema,
            tools_config=ToolsRunConfig(tools=tool_ids),
        ),
    )
    rc.save_to_file()
    return rc


@pytest.fixture
def syn_tool_id(world):
    return build_world_tool_id(world.id, "append_note")


@pytest.fixture
def run_config(task, syn_tool_id):
    """The run config for inputs that run in the world: it lists the world's tool."""
    return _run_config(task, [syn_tool_id], name="world rc")


@pytest.fixture
def project_run_config(task, project_tool):
    return _run_config(task, [build_code_tool_id(project_tool.id)], name="real rc")


@pytest.fixture
def eval_(task):
    e = Eval(
        name="eval",
        splits={"test": EvalInputSplit(filter_id="all")},
        eval_configs_filter_id="all",
        output_scores=[
            EvalOutputScore(
                name="Accuracy",
                instruction="is it accurate",
                type=TaskOutputRatingType.pass_fail,
            )
        ],
        parent=task,
    )
    e.save_to_file()
    return e


def _config(eval_, properties, name="cfg"):
    cfg = EvalConfig(
        name=name, config_type=EvalConfigType.v2, properties=properties, parent=eval_
    )
    cfg.save_to_file()
    return cfg


def _input(task, text, world_reset=None, id=None):
    ei = EvalInput(
        id=id,
        parent=task,
        data=SingleTurnEvalInputData(user_message=UserMessage(text=text)),
        world_reset=world_reset,
    )
    ei.save_to_file()
    return ei


def _reset(world, fixture_id, frozen_time=None):
    config = {"fixture_id": fixture_id}
    if frozen_time is not None:
        config["frozen_time"] = frozen_time
    return WorldReset(world_id=world.id, reset_kwargs=config)


class ToolCallingGenerator:
    """Stands in for the model call: resolves the run config's tool through the registry
    and invokes it once, so the proxy runs for real."""

    def __init__(self, task: Task, tool_id: str, allow_error: bool = False):
        self.task = task
        self.tool_id = tool_id
        self.allow_error = allow_error
        self.outputs: dict[str, str] = {}
        self.errors: dict[str, str | None] = {}

    async def __call__(self, item, run_config_id=None) -> TaskRun:
        await asyncio.sleep(0)
        tool = tool_from_id(self.tool_id, self.task)
        ctx = get_episode()
        result = await tool.run(
            ToolCallContext(episode=ctx.episode if ctx is not None else None),
            note=item.data.user_message.text,
        )
        if not self.allow_error:
            assert not result.is_error, result.output
        self.outputs[item.id] = result.output
        self.errors[item.id] = result.error_message
        run = TaskRun(
            parent=self.task,
            input=item.data.user_message.text,
            output=TaskOutput(
                output=result.output,
                source=DataSource(
                    type=DataSourceType.synthetic,
                    properties={
                        "model_name": "gpt-4",
                        "model_provider": "openai",
                        "adapter_name": "test_adapter",
                    },
                    run_config_id=run_config_id,
                ),
            ),
            trace=[
                {"role": "user", "content": item.data.user_message.text},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {"name": await tool.name(), "arguments": "{}"},
                        }
                    ],
                },
                {"role": "assistant", "content": result.output},
            ],
        )
        run.id = None
        return run


class RecordingJudge(BaseV2EvalBridge):
    """A judge that records what it was shown and what state it could see."""

    seen: ClassVar[list[EvalTaskInput]] = []
    states: ClassVar[dict[str, dict | None]] = {}

    async def evaluate(self, eval_input: EvalTaskInput) -> V2EvalResult:
        RecordingJudge.seen.append(eval_input)
        ctx = get_episode()
        if ctx is not None:
            RecordingJudge.states[eval_input.task_input or ""] = ctx.episode.state
        return V2EvalResult(scores={"accuracy": 1.0})


@pytest.fixture(autouse=True)
def _reset_judge():
    RecordingJudge.seen = []
    RecordingJudge.states = {}
    yield
    RecordingJudge.seen = []
    RecordingJudge.states = {}


def _judge_patch():
    return patch(
        "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
        side_effect=lambda config, *args, **kwargs: RecordingJudge(config),
    )


def _runner(eval_configs, run_config, session_manager, split_name="test"):
    eval_ = eval_configs[0].parent_eval()
    task = eval_.parent_task()
    split = resolve_split(task, eval_, split_name)
    return EvalRunner(
        eval_configs=eval_configs,
        run_configs=[run_config],
        eval_run_type="task_run_eval",
        split=split,
        world_session_manager=session_manager,
    )


async def _drain(runner, concurrency=25):
    async for _ in runner.run(concurrency=concurrency):
        pass


def _traces(task):
    return [
        r
        for r in task.runs(readonly=True, include_eval_generated=True)
        if r.eval_source is not None
    ]


STATE_SCORER = (
    "def score(output, episode):\n"
    "    notes = episode['state']['notes']\n"
    "    ok = len(notes) == 1 and episode['state']['step_count'] == 1\n"
    "    return {'accuracy': 1.0 if ok else 0.0}\n"
)


async def test_full_run_isolates_and_records_instances(
    project, task, world, syn_tool_id, run_config, eval_, session_manager
):
    a = _input(task, "note for a", _reset(world, "a", CLOCK_A), id="ei_a")
    b = _input(task, "note for b", _reset(world, "b", CLOCK_B), id="ei_b")
    cfg = _config(eval_, ExactMatchProperties(expected_value="noted:1"))
    generator = ToolCallingGenerator(task, syn_tool_id)
    with patch.object(BaseV2EvalBridge, "run_task", new=generator), _judge_patch():
        await _drain(_runner([cfg], run_config, session_manager))

    # The environment's tool ran for both inputs.
    assert generator.outputs[a.id] == "noted:1"
    assert generator.outputs[b.id] == "noted:1"

    traces = {t.eval_source.source_id: t for t in _traces(task)}
    assert set(traces) == {a.id, b.id}
    ep_a, ep_b = traces[a.id].episode, traces[b.id].episode
    assert ep_a is not None and ep_b is not None
    # The trace records the environment's function name; the run config records the
    # world tool id it was chosen by.
    assert traces[a.id].trace[1]["tool_calls"][0]["function"]["name"] == "append_note"
    assert run_config.run_config_properties.tools_config.tools == [syn_tool_id]
    assert ep_a.episode_id != ep_b.episode_id
    assert ep_a.reset_kwargs == {"fixture_id": "a", "frozen_time": CLOCK_A}
    assert ep_b.reset_kwargs == {"fixture_id": "b", "frozen_time": CLOCK_B}
    assert ep_a.metadata["fixture_id"] == "a"
    assert ep_a.metadata["frozen_time"] == CLOCK_A
    assert ep_b.metadata["frozen_time"] == CLOCK_B
    assert "env_name" not in ep_a.metadata
    # Each episode holds only its own run's note.
    assert ep_a.state["notes"] == ["note for a"]
    assert ep_b.state["notes"] == ["note for b"]
    # Variant on the trace key separates configs.
    # Same world, same reported version: the world_version is identical and readable;
    # the inputs'
    # own ids keep their traces apart.
    assert traces[a.id].episode.world_version == traces[b.id].episode.world_version
    assert traces[a.id].episode.world_version == f"{ENV_NAME}@1.0.0"
    # Sessions are closed once the episode is ended.
    assert session_manager._sessions == {}

    # The judge saw ids and facts but not the state record, and the context let
    # it read the settled state.
    by_input = {s.task_input: s for s in RecordingJudge.seen}
    info = by_input["note for a"].episode
    assert info is not None
    assert info.reset_kwargs == {"fixture_id": "a", "frozen_time": CLOCK_A}
    assert info.metadata["fixture_id"] == "a"
    assert info.state["notes"] == ["note for a"]
    assert RecordingJudge.states["note for a"]["notes"] == ["note for a"]

    # Every job scored.
    runs = cfg.runs(readonly=True)
    assert len(runs) == 2
    assert all(r.scores == {"accuracy": 1.0} for r in runs)


async def test_project_run_config_runs_project_tools_without_an_environment(
    project, task, world, project_tool, project_run_config, eval_, session_manager
):
    """An input with no environment runs the project tool under a real run config; no
    session, no instance, no world_version."""
    none = _input(task, "note for none", None, id="ei_none")
    cfg = _config(eval_, ExactMatchProperties(expected_value="real"))
    generator = ToolCallingGenerator(task, build_code_tool_id(project_tool.id))
    with (
        patch.object(BaseV2EvalBridge, "run_task", new=generator),
        patch.object(
            session_manager, "start_episode", wraps=session_manager.start_episode
        ) as start_episode,
        _judge_patch(),
    ):
        await _drain(_runner([cfg], project_run_config, session_manager))
    assert generator.outputs[none.id] == "real"
    start_episode.assert_not_called()
    (trace,) = _traces(task)
    assert trace.episode is None
    assert trace.episode is None
    (seen,) = RecordingJudge.seen
    assert seen.episode is None
    assert cfg.runs(readonly=True)[0].scores == {"accuracy": 1.0}


# ---------------------------------------------------------------------------
# Run config and eval input must agree
# ---------------------------------------------------------------------------


async def _expect_job_error(runner, match, session_manager, task):
    job = runner.collect_tasks()[0]
    with pytest.raises(ValueError, match=match):
        await runner.run_job(job)
    assert _traces(task) == []
    assert session_manager._sessions == {}


async def test_world_run_config_without_world_reset_is_an_error(
    project, task, world, syn_tool_id, run_config, eval_, session_manager
):
    _input(task, "note", None, id="ei_none")
    cfg = _config(eval_, ExactMatchProperties(expected_value="x"))
    generator = ToolCallingGenerator(task, syn_tool_id)
    with patch.object(BaseV2EvalBridge, "run_task", new=generator):
        await _expect_job_error(
            _runner([cfg], run_config, session_manager),
            "lists world tools .* has no world_reset",
            session_manager,
            task,
        )
    assert generator.outputs == {}


async def test_unserved_project_tools_ignore_the_environment(
    project, task, world, other_tool, eval_, session_manager
):
    """An input with a world, run under a run config whose only tools
    are real ones the world does not serve, is a plain real-tools job: nothing is
    launched and no instance or world_version is recorded. The environment only matters to
    tools that use it."""
    run_config = _run_config(task, [build_code_tool_id(other_tool.id)], name="other rc")
    _input(task, "note", _reset(world, "a"), id="ei_a")
    cfg = _config(eval_, ExactMatchProperties(expected_value="x"))
    generator = ToolCallingGenerator(task, build_code_tool_id(other_tool.id))
    with (
        patch.object(BaseV2EvalBridge, "run_task", new=generator),
        patch.object(
            session_manager, "start_episode", wraps=session_manager.start_episode
        ) as start_episode,
    ):
        await _drain(_runner([cfg], run_config, session_manager))
    assert generator.outputs == {"ei_a": "real-write"}
    start_episode.assert_not_called()
    traces = _traces(task)
    assert len(traces) == 1
    assert traces[0].episode is None
    assert traces[0].episode is None
    assert not session_manager._sessions


async def test_tools_from_another_world_are_an_error(
    project, task, world, eval_, session_manager
):
    foreign = build_world_tool_id("other_world", "append_note")
    run_config = _run_config(task, [foreign], name="foreign rc")
    _input(task, "note", _reset(world, "a"), id="ei_a")
    cfg = _config(eval_, ExactMatchProperties(expected_value="x"))
    generator = ToolCallingGenerator(task, foreign)
    with patch.object(BaseV2EvalBridge, "run_task", new=generator):
        await _expect_job_error(
            _runner([cfg], run_config, session_manager),
            r"lists tools from world\(s\) \['other_world'\]",
            session_manager,
            task,
        )
    assert generator.outputs == {}


async def test_world_tool_id_outside_a_world_job_raises(task, syn_tool_id):
    with pytest.raises(ValueError, match="can only be used while an episode"):
        tool_from_id(syn_tool_id, task)


async def test_later_judge_reuses_trace_and_instance(
    project, task, world, syn_tool_id, run_config, eval_, session_manager
):
    """A judge added later scores the same trace and sees the same instance record,
    without opening a new session."""
    _input(task, "look", _reset(world, "a"), id="ei_a")
    first = _config(eval_, ExactMatchProperties(expected_value="x"), name="first")
    generator = ToolCallingGenerator(task, syn_tool_id)
    with patch.object(BaseV2EvalBridge, "run_task", new=generator), _judge_patch():
        await _drain(_runner([first], run_config, session_manager))
    (trace,) = _traces(task)
    launched = set()
    original_start = session_manager.start_episode

    async def counting_start(world_, config):
        instance = await original_start(world_, config)
        launched.add(instance.episode_id)
        return instance

    second = _config(eval_, ExactMatchProperties(expected_value="x"), name="second")
    with (
        patch.object(BaseV2EvalBridge, "run_task", new=generator),
        patch.object(session_manager, "start_episode", new=counting_start),
        _judge_patch(),
    ):
        await _drain(_runner([first, second], run_config, session_manager))
    assert len(_traces(task)) == 1, "the second judge reused the generation"
    assert len(generator.outputs) == 1
    assert launched == set()
    assert len(second.runs(readonly=True)) == 1
    assert RecordingJudge.seen[-1].episode.episode_id == (trace.episode.episode_id)
    assert RecordingJudge.states["look"]["notes"] == ["look"]


async def test_changed_environment_version_regenerates_the_trace(
    project, task, eval_, session_manager, env_server
):
    """Same world, pointed at an environment reporting a new version: the content
    version moves, so the trace world_version moves and the item is generated again rather
    than reused."""
    world = World(name="Versioned", parent=project, env_url=env_server)
    world.save_to_file()
    syn_tool_id = build_world_tool_id(world.id, "append_note")
    run_config = _run_config(task, [syn_tool_id])

    _input(task, "note", _reset(world, "a"), id="ei_a")
    first = _config(eval_, ExactMatchProperties(expected_value="x"), name="first")
    generator = ToolCallingGenerator(task, syn_tool_id)
    with patch.object(BaseV2EvalBridge, "run_task", new=generator):
        await _drain(_runner([first], run_config, session_manager))
    assert len(_traces(task)) == 1
    assert generator.outputs["ei_a"] == "noted:1"

    with serve_in_thread(version="2.0.0") as upgraded:
        world.env_url = upgraded
        world.save_to_file()
        second = _config(eval_, ExactMatchProperties(expected_value="x"), name="second")
        with patch.object(BaseV2EvalBridge, "run_task", new=generator):
            await _drain(_runner([second], run_config, session_manager))
    traces = _traces(task)
    assert len(traces) == 2
    assert len({t.episode.world_version for t in traces}) == 2
    assert len({t.episode.episode_id for t in traces}) == 2


async def test_missing_world_is_an_error_not_a_skip(
    project, task, world, syn_tool_id, run_config, eval_, session_manager
):
    _input(
        task,
        "note",
        WorldReset(world_id="nope", reset_kwargs={"fixture_id": "a"}),
        id="ei_bad",
    )
    run_config = _run_config(
        task, [build_world_tool_id("nope", "append_note")], name="nope rc"
    )
    cfg = _config(eval_, ExactMatchProperties(expected_value="x"))
    generator = ToolCallingGenerator(task, syn_tool_id)
    with patch.object(BaseV2EvalBridge, "run_task", new=generator):
        runner = _runner([cfg], run_config, session_manager)
        job = runner.collect_tasks()[0]
        with pytest.raises(ValueError, match="World nope not found"):
            await runner.run_job(job)
    assert generator.outputs == {}
    assert cfg.runs(readonly=True) == []
    assert session_manager._sessions == {} and session_manager._servers == {}


async def test_unreachable_environment_is_a_job_error(
    project, task, eval_, session_manager
):
    """The world resolves but its environment does not answer: the job errors before
    any generation and nothing is persisted."""
    world = World(
        name="Dead", parent=project, env_url=f"http://127.0.0.1:{free_port()}"
    )
    world.save_to_file()
    syn_tool_id = build_world_tool_id(world.id, "append_note")
    run_config = _run_config(task, [syn_tool_id])
    _input(task, "note", _reset(world, "a"), id="ei_bad")
    cfg = _config(eval_, ExactMatchProperties(expected_value="x"))
    generator = ToolCallingGenerator(task, syn_tool_id)
    with patch.object(BaseV2EvalBridge, "run_task", new=generator):
        runner = _runner([cfg], run_config, session_manager)
        job = runner.collect_tasks()[0]
        with pytest.raises(RuntimeError, match="did not answer /metadata"):
            await runner.run_job(job)
    assert generator.outputs == {}
    assert _traces(task) == []
    assert session_manager._sessions == {}


async def test_skipped_job_creates_no_session(
    project, task, world, syn_tool_id, run_config, eval_, session_manager
):
    _input(task, "note", _reset(world, "a"), id="ei_a")
    cfg = _config(eval_, ExactMatchProperties(expected_value="x"))
    generator = ToolCallingGenerator(task, syn_tool_id)
    with (
        patch.object(BaseV2EvalBridge, "run_task", new=generator),
        patch(
            "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
            side_effect=NotImplementedError("nope"),
        ),
        patch.object(
            session_manager, "start_episode", wraps=session_manager.start_episode
        ) as start_episode,
    ):
        await _drain(_runner([cfg], run_config, session_manager))
    assert cfg.runs(readonly=True)[0].skipped_reason == "type_not_available"
    assert generator.outputs == {}
    start_episode.assert_not_called()
    assert session_manager._sessions == {}
    assert _traces(task) == []


async def test_concurrent_judges_share_one_generation_and_instance(
    project, task, world, syn_tool_id, run_config, eval_, session_manager
):
    """Two scorers on one item, in one run: one generation, one instance, and both
    read the settled state."""
    _input(task, "look", _reset(world, "a"), id="ei_a")
    first = _config(
        eval_, CodeEvalProperties(code=STATE_SCORER, timeout_seconds=30), name="first"
    )
    second = _config(
        eval_, CodeEvalProperties(code=STATE_SCORER, timeout_seconds=30), name="second"
    )
    generator = ToolCallingGenerator(task, syn_tool_id)
    with patch.object(BaseV2EvalBridge, "run_task", new=generator):
        await _drain(_runner([first, second], run_config, session_manager))
    assert len(_traces(task)) == 1
    assert len(generator.outputs) == 1
    for cfg in (first, second):
        run = cfg.runs(readonly=True)[0]
        assert run.skipped_reason is None, cfg.name
        assert run.scores == {"accuracy": 1.0}, cfg.name
    (trace,) = _traces(task)
    assert trace.episode.state["notes"] == ["look"]
    assert session_manager._sessions == {}


# ---------------------------------------------------------------------------
# Multi-turn: one instance shared by every turn of a drive
# ---------------------------------------------------------------------------


async def test_multi_turn_drive_shares_one_instance_across_turns(
    project, task, world, syn_tool_id, run_config, eval_, session_manager
):
    """The drive runs with the episode in context for its whole conversation: every
    turn's tool call lands in the same session, the leaf trace records that episode,
    and the trace is keyed by the world_version."""
    ei = EvalInput(
        id="ei_multi",
        parent=task,
        data=MultiTurnSyntheticEvalInputData(
            first_message=UserMessage(text="first note"),
            synthetic_user_info=SyntheticUserInfo(
                persona="a technician", goal="log two notes", behavior_guidance=None
            ),
            drive_config=MultiTurnDriveConfig(
                model_name="claude_4_5_haiku", model_provider="openrouter", turns=2
            ),
        ),
        world_reset=_reset(world, "a"),
    )
    ei.save_to_file()
    cfg = _config(
        eval_,
        CodeEvalProperties(
            code=(
                "def score(output, episode):\n"
                "    notes = episode['state']['notes']\n"
                "    return {'accuracy': 1.0 if notes == ['first note', 'second note'] else 0.0}\n"
            ),
            timeout_seconds=30,
        ),
    )
    tool_id = syn_tool_id
    seen_instances: list[str] = []

    async def fake_drive(*, seed_prompt, target_task, turns, **_):
        chain = []
        for note in ("first note", "second note")[:turns]:
            tool = tool_from_id(tool_id, target_task)
            ctx = get_episode()
            assert ctx is not None, "the drive must run with the instance in context"
            seen_instances.append(ctx.episode.episode_id)
            result = await tool.run(ToolCallContext(episode=ctx.episode), note=note)
            assert not result.is_error, result.output
            chain.append(
                TaskRun(
                    parent=target_task,
                    input=note,
                    output=TaskOutput(
                        output=result.output,
                        source=DataSource(
                            type=DataSourceType.synthetic,
                            properties={
                                "model_name": "gpt-4",
                                "model_provider": "openai",
                                "adapter_name": "test_adapter",
                            },
                        ),
                    ),
                    trace=[
                        {"role": "user", "content": "first note"},
                        {"role": "assistant", "content": "ok"},
                        {"role": "user", "content": "second note"},
                        {"role": "assistant", "content": result.output},
                    ],
                )
            )
        for run in chain:
            run.id = None
        return DriveCaseResult(chain=chain, su_usage=None)

    with patch("kiln_ai.adapters.eval.eval_runner.drive_case_for_eval", new=fake_drive):
        await _drain(_runner([cfg], run_config, session_manager))

    assert len(seen_instances) == 2 and len(set(seen_instances)) == 1
    traces = _traces(task)
    assert len(traces) == 1
    trace = traces[0]
    assert trace.episode is not None
    assert trace.episode.episode_id == seen_instances[0]
    assert trace.episode.state["notes"] == ["first note", "second note"]
    assert trace.episode.state["step_count"] == 2
    assert trace.episode.world_version == f"{ENV_NAME}@1.0.0"
    run = cfg.runs(readonly=True)[0]
    assert run.skipped_reason is None
    assert run.scores == {"accuracy": 1.0}
    assert session_manager._sessions == {}

    # A second judge reuses the drive and its instance rather than re-driving.
    second = _config(eval_, ExactMatchProperties(expected_value="x"), name="second")
    with patch("kiln_ai.adapters.eval.eval_runner.drive_case_for_eval", new=fake_drive):
        await _drain(_runner([second], run_config, session_manager))
    assert len(seen_instances) == 2
    assert len(_traces(task)) == 1


async def test_multi_turn_skip_creates_no_instance(
    project, task, world, run_config, eval_, session_manager
):
    EvalInput(
        id="ei_nodrive",
        parent=task,
        data=MultiTurnSyntheticEvalInputData(
            first_message=UserMessage(text="hi"),
            synthetic_user_info=SyntheticUserInfo(persona="p", goal="g"),
            drive_config=None,
        ),
        world_reset=_reset(world, "a"),
    ).save_to_file()
    cfg = _config(eval_, ExactMatchProperties(expected_value="x"))
    with patch.object(
        session_manager, "start_episode", wraps=session_manager.start_episode
    ) as start_episode:
        await _drain(_runner([cfg], run_config, session_manager))
    assert cfg.runs(readonly=True)[0].skipped_reason == "missing_drive_config"
    start_episode.assert_not_called()
    assert session_manager._sessions == {}
    assert _traces(task) == []


# ---------------------------------------------------------------------------
# Finalize, validity, strictness
# ---------------------------------------------------------------------------


async def test_end_episode_settles_record_before_grading(
    project, task, world, syn_tool_id, run_config, eval_, session_manager
):
    """Finalize runs after generation and before any grader: scorers read the
    environment's state, judges see the ids and facts, and the trace persists the
    settled record."""
    _input(task, "note", _reset(world, "a"), id="ei_a")
    judge = _config(eval_, ExactMatchProperties(expected_value="x"), name="judge")
    scorer = _config(
        eval_, CodeEvalProperties(code=STATE_SCORER, timeout_seconds=30), name="s"
    )
    generator = ToolCallingGenerator(task, syn_tool_id)
    with patch.object(BaseV2EvalBridge, "run_task", new=generator):
        await _drain(_runner([scorer], run_config, session_manager))

    (trace,) = _traces(task)
    assert trace.episode is not None
    assert trace.episode.state["notes"] == ["note"]
    assert trace.episode.state["step_count"] == 1

    scorer_run = scorer.runs(readonly=True)[0]
    assert scorer_run.skipped_reason is None
    assert scorer_run.scores == {"accuracy": 1.0}

    # A judge reusing the trace sees the whole episode, state included.
    with patch.object(BaseV2EvalBridge, "run_task", new=generator), _judge_patch():
        await _drain(_runner([judge], run_config, session_manager))
    assert len(_traces(task)) == 1
    judge_run = judge.runs(readonly=True)[0]
    assert judge_run.skipped_reason is None
    (seen,) = RecordingJudge.seen
    assert seen.episode is not None
    assert seen.episode.episode_id == trace.episode.episode_id
    assert seen.episode.state["notes"] == ["note"]


async def test_project_versions_of_served_tools_are_refused(
    project, task, world, project_tool, project_run_config, eval_, session_manager
):
    """An input with a world never meets the project's own version of a tool
    its world serves: such a run config is refused before anything runs, whether or
    not it also lists the world's tools."""
    _input(task, "note", _reset(world, "a"), id="ei_a")
    cfg = _config(eval_, ExactMatchProperties(expected_value="x"))
    generator = ToolCallingGenerator(task, build_code_tool_id(project_tool.id))
    with (
        patch.object(BaseV2EvalBridge, "run_task", new=generator),
        patch.object(
            session_manager, "start_episode", wraps=session_manager.start_episode
        ) as start_episode,
    ):
        await _expect_job_error(
            _runner([cfg], project_run_config, session_manager),
            "runs in world 'World', but run config 'real rc' lists "
            "the project's own version of tools the world serves: "
            + re.escape(build_code_tool_id(project_tool.id))
            + r" \(append_note\)",
            session_manager,
            task,
        )
    assert generator.outputs == {}
    start_episode.assert_not_called()


async def test_project_tools_the_world_does_not_serve_are_allowed(
    project, task, world, syn_tool_id, other_tool, eval_, session_manager
):
    """A project tool outside the world's coverage (a web search, a docs lookup) may sit
    beside the world's tools; it runs for real while the world's tools run in the
    instance."""
    run_config = _run_config(
        task, [syn_tool_id, build_code_tool_id(other_tool.id)], name="mixed rc"
    )
    _input(task, "note", _reset(world, "a"), id="ei_a")
    cfg = _config(eval_, ExactMatchProperties(expected_value="x"))
    generator = ToolCallingGenerator(task, build_code_tool_id(other_tool.id))
    with patch.object(BaseV2EvalBridge, "run_task", new=generator):
        await _drain(_runner([cfg], run_config, session_manager))
    assert generator.outputs["ei_a"] == "real-write"
    (trace,) = _traces(task)
    assert trace.episode is not None
    assert trace.episode.state["notes"] == []


async def test_tool_error_reaches_the_model_and_ends_the_episode(
    project, task, world, eval_, session_manager
):
    tool_id = build_world_tool_id(world.id, "explode")
    run_config = _run_config(task, [tool_id])
    _input(task, "note", _reset(world, "a"), id="ei_a")
    cfg = _config(eval_, ExactMatchProperties(expected_value="x"))
    generator = ToolCallingGenerator(task, tool_id, allow_error=True)
    with patch.object(BaseV2EvalBridge, "run_task", new=generator):
        await _drain(_runner([cfg], run_config, session_manager))
    assert generator.outputs["ei_a"] == "boom"
    assert generator.errors["ei_a"] == "boom"
    (trace,) = _traces(task)
    assert trace.episode.state["notes"] == []
    assert trace.episode.state["step_count"] == 1
