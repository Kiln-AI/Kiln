"""End-to-end runner tests against a synthetic world.

A tiny world with one synthetic tool that appends to a counter file inside the
instance; two fixtures with different clocks; eval inputs for each fixture plus one
with no environment. Generation is stubbed at the model boundary only: the fake
`run_task` resolves the run config's tool through the registry (so the swap, the proxy
and the sandbox all run for real) and calls it once.
"""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
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
    SingleTurnEvalInputData,
    SkippedReason,
    UserMessage,
    V2EvalResult,
)
from kiln_ai.datamodel.eval_splits import resolve_split
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties, ToolsRunConfig
from kiln_ai.datamodel.synthetic_world import (
    SyntheticEnvironment,
    SyntheticTool,
    SyntheticWorld,
)
from kiln_ai.datamodel.task import Task, TaskRunConfig
from kiln_ai.datamodel.task_output import DataSource, DataSourceType, TaskOutput
from kiln_ai.datamodel.task_run import TaskRun
from kiln_ai.datamodel.tool_id import build_code_tool_id
from kiln_ai.run_context import get_synthetic_instance
from kiln_ai.synthetic_worlds.launcher import LocalFilesLauncher, local_fixture_dir
from kiln_ai.tools.base_tool import ToolCallContext
from kiln_ai.tools.tool_registry import tool_from_id

SCHEMA = {"type": "object", "properties": {"note": {"type": "string"}}}
REAL_CODE = "def run(note):\n    return 'real'\n"
SYNTH_CODE = (
    "import os\n"
    "def run(note):\n"
    "    root = os.environ['KILN_SYNTHETIC_INSTANCE_PATH']\n"
    "    with open(os.path.join(root, 'counter.txt'), 'a') as f:\n"
    "        f.write(note + '\\n')\n"
    "    return 'synthetic:' + os.environ.get('KILN_SYNTHETIC_FROZEN_TIME', '')\n"
)
CLOCK_A = datetime(2026, 7, 14, tzinfo=timezone.utc)
CLOCK_B = datetime(2025, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def project(tmp_path):
    p = Project(name="proj", path=tmp_path / "proj" / "project.kiln")
    p.path.parent.mkdir(parents=True)
    p.save_to_file()
    return p


@pytest.fixture
def real_tool(project):
    ct = CodeTool(
        name="real note",
        parent=project,
        tool_function_name="write_note",
        tool_description="writes a note",
        parameters_schema=SCHEMA,
        code=REAL_CODE,
    )
    ct.save_to_file()
    return ct


@pytest.fixture
def world(project, real_tool):
    w = SyntheticWorld(name="World", parent=project, content_version="eng1")
    w.save_to_file()
    SyntheticTool(
        name="synthetic note",
        parent=w,
        replaces_tool_id=build_code_tool_id(real_tool.id),
        tool_function_name="write_note",
        tool_description="writes a note",
        parameters_schema=SCHEMA,
        code=SYNTH_CODE,
        timeout_seconds=10,
    ).save_to_file()
    return w


def _fixture(world, fixture_id, clock, content):
    d = local_fixture_dir(world, fixture_id)
    d.mkdir(parents=True)
    (d / "fixture.db").write_bytes(content)
    (d / "fixture.yaml").write_text(f"frozen_time: '{clock.isoformat()}'\n")
    return d


@pytest.fixture
def fixtures(world):
    """fixture id -> its directory."""
    return {
        "a": _fixture(world, "a", CLOCK_A, b"a-data"),
        "b": _fixture(world, "b", CLOCK_B, b"b-data"),
    }


@pytest.fixture
def task(project):
    t = Task(name="task", instruction="write a note", parent=project)
    t.save_to_file()
    return t


@pytest.fixture
def run_config(task, real_tool):
    rc = TaskRunConfig(
        name="rc",
        parent=task,
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name="openai",
            prompt_id="simple_prompt_builder",
            structured_output_mode=StructuredOutputMode.json_schema,
            tools_config=ToolsRunConfig(tools=[build_code_tool_id(real_tool.id)]),
        ),
    )
    rc.save_to_file()
    return rc


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


def _input(task, text, environment=None, id=None):
    ei = EvalInput(
        id=id,
        parent=task,
        data=SingleTurnEvalInputData(user_message=UserMessage(text=text)),
        synthetic_environment=environment,
    )
    ei.save_to_file()
    return ei


def _env(world, fixture_id, frozen_time=None):
    config = {"fixture_id": fixture_id}
    if frozen_time is not None:
        config["frozen_time"] = frozen_time.isoformat()
    return SyntheticEnvironment(world_id=world.id, config=config)


class ToolCallingGenerator:
    """Stands in for the model call: resolves the run config's tool through the registry
    and invokes it once, so the swap and the sandbox both run for real."""

    def __init__(self, task: Task, tool_id: str):
        self.task = task
        self.tool_id = tool_id
        self.outputs: dict[str, str] = {}

    async def __call__(self, item, run_config_id=None) -> TaskRun:
        await asyncio.sleep(0)
        tool = tool_from_id(self.tool_id, self.task)
        ctx = get_synthetic_instance()
        result = await tool.run(
            ToolCallContext(
                synthetic_instance=ctx.instance if ctx is not None else None
            ),
            note=item.data.user_message.text,
        )
        assert not result.is_error, result.output
        self.outputs[item.id] = result.output
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
    counters: ClassVar[dict[str, str | None]] = {}

    async def evaluate(self, eval_input: EvalTaskInput) -> V2EvalResult:
        RecordingJudge.seen.append(eval_input)
        ctx = get_synthetic_instance()
        if ctx is not None:
            counter = Path(ctx.instance.effective_path) / "counter.txt"
            RecordingJudge.counters[eval_input.task_input or ""] = (
                counter.read_text() if counter.exists() else None
            )
        return V2EvalResult(scores={"accuracy": 1.0})


@pytest.fixture(autouse=True)
def _reset_judge():
    RecordingJudge.seen = []
    RecordingJudge.counters = {}
    yield
    RecordingJudge.seen = []
    RecordingJudge.counters = {}


def _runner(eval_configs, run_config, launcher, split_name="test"):
    eval_ = eval_configs[0].parent_eval()
    task = eval_.parent_task()
    split = resolve_split(task, eval_, split_name)
    return EvalRunner(
        eval_configs=eval_configs,
        run_configs=[run_config],
        eval_run_type="task_run_eval",
        split=split,
        synthetic_launcher=launcher,
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


@pytest.fixture
def provider(tmp_path):
    return LocalFilesLauncher(cache_root=tmp_path / "cache", max_bytes=10**9)


async def test_full_run_isolates_and_records_instances(
    project, task, world, fixtures, real_tool, run_config, eval_, provider
):
    a = _input(task, "note for a", _env(world, "a"), id="ei_a")
    b = _input(task, "note for b", _env(world, "b"), id="ei_b")
    none = _input(task, "note for none", None, id="ei_none")
    cfg = _config(
        eval_,
        ExactMatchProperties(expected_value="synthetic:2026-07-14T00:00:00+00:00"),
    )
    generator = ToolCallingGenerator(task, build_code_tool_id(real_tool.id))
    with (
        patch.object(BaseV2EvalBridge, "run_task", new=generator),
        patch(
            "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
            side_effect=lambda config, *args, **kwargs: RecordingJudge(config),
        ),
    ):
        await _drain(_runner([cfg], run_config, provider))

    # The synthetic tool ran for the two environment inputs with each fixture's clock,
    # and the real tool for the input without one.
    assert generator.outputs[a.id] == "synthetic:2026-07-14T00:00:00+00:00"
    assert generator.outputs[b.id] == "synthetic:2025-01-01T00:00:00+00:00"
    assert generator.outputs[none.id] == "real"

    traces = {t.eval_source.source_id: t for t in _traces(task)}
    assert set(traces) == {a.id, b.id, none.id}
    inst_a, inst_b = traces[a.id].synthetic_instance, traces[b.id].synthetic_instance
    assert traces[none.id].synthetic_instance is None
    assert inst_a is not None and inst_b is not None
    assert inst_a.instance_id != inst_b.instance_id
    assert inst_a.config == {"fixture_id": "a"} and inst_b.config == {"fixture_id": "b"}
    assert inst_a.metadata["frozen_time"] == CLOCK_A.isoformat()
    assert inst_b.metadata["frozen_time"] == CLOCK_B.isoformat()
    assert inst_a.content_version is not None
    assert inst_a.content_version.startswith("local:")
    # Both runs wrote, so both copies are kept and hold only their own note.
    assert inst_a.unchanged is False and inst_b.unchanged is False
    assert (Path(inst_a.path) / "counter.txt").read_text() == "note for a\n"
    assert (Path(inst_b.path) / "counter.txt").read_text() == "note for b\n"
    # Variant on the trace key separates fixtures; the plain input has none.
    assert traces[a.id].eval_source.variant != traces[b.id].eval_source.variant
    assert traces[a.id].eval_source.variant.startswith("syn2:")
    assert traces[none.id].eval_source.variant is None

    # The judge saw ids and clock, no paths, and could read the instance state.
    by_input = {s.task_input: s for s in RecordingJudge.seen}
    info = by_input["note for a"].synthetic_instance
    assert info is not None
    assert info.config == {"fixture_id": "a"}
    assert info.metadata["fixture_id"] == "a"
    assert "path" not in info.model_dump()
    assert by_input["note for none"].synthetic_instance is None
    assert RecordingJudge.counters["note for a"] == "note for a\n"

    # Every job scored.
    runs = cfg.runs(readonly=True)
    assert len(runs) == 3
    assert all(r.scores == {"accuracy": 1.0} for r in runs)


async def test_read_only_run_drops_copy_and_later_judge_reuses_trace(
    project, task, world, fixtures, real_tool, run_config, eval_, provider
):
    """A run that leaves the fixture untouched keeps no copy; a judge added later
    scores the same trace and still reads the fixture's own data."""
    read_only_tool = world.tools()[0]
    read_only_tool.code = "def run(note):\n    return 'looked'\n"
    read_only_tool.save_to_file()
    _input(task, "look", _env(world, "a"), id="ei_a")
    first = _config(eval_, ExactMatchProperties(expected_value="looked"), name="first")
    generator = ToolCallingGenerator(task, build_code_tool_id(real_tool.id))
    patches = (
        patch.object(BaseV2EvalBridge, "run_task", new=generator),
        patch(
            "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
            side_effect=lambda config, *args, **kwargs: RecordingJudge(config),
        ),
    )
    with patches[0], patches[1]:
        await _drain(_runner([first], run_config, provider))
    trace = _traces(task)[0]
    assert trace.synthetic_instance.unchanged is True
    assert not Path(trace.synthetic_instance.path).exists()
    assert trace.synthetic_instance.effective_path == str(fixtures["a"])

    second = _config(
        eval_, ExactMatchProperties(expected_value="looked"), name="second"
    )
    with patches[0], patches[1]:
        await _drain(_runner([first, second], run_config, provider))
    assert len(_traces(task)) == 1, "the second judge reused the generation"
    assert len(generator.outputs) == 1
    assert len(second.runs(readonly=True)) == 1
    assert RecordingJudge.seen[-1].synthetic_instance.instance_id == (
        trace.synthetic_instance.instance_id
    )


async def test_changed_fixture_regenerates_and_evicted_state_skips_scorer(
    project, task, world, fixtures, real_tool, run_config, eval_, provider
):
    a = _input(task, "note", _env(world, "a"), id="ei_a")
    judge = _config(eval_, ExactMatchProperties(expected_value="x"), name="judge")
    scorer = _config(
        eval_,
        CodeEvalProperties(
            code=(
                "import os\n"
                "def score(output, synthetic_instance):\n"
                "    p = os.path.join(synthetic_instance['path'], 'counter.txt')\n"
                "    return {'accuracy': 1.0 if os.path.exists(p) else 0.0}\n"
            ),
            timeout_seconds=30,
        ),
        name="scorer",
    )
    generator = ToolCallingGenerator(task, build_code_tool_id(real_tool.id))
    with patch.object(BaseV2EvalBridge, "run_task", new=generator):
        await _drain(_runner([judge, scorer], run_config, provider))
    assert len(_traces(task)) == 1
    scorer_run = scorer.runs(readonly=True)[0]
    assert scorer_run.scores == {"accuracy": 1.0}
    assert scorer_run.skipped_reason is None

    # Pointing the input at the other fixture is a new variant: a fresh generation.
    a.synthetic_environment = _env(world, "b")
    a.save_to_file()
    third = _config(eval_, ExactMatchProperties(expected_value="x"), name="third")
    with patch.object(BaseV2EvalBridge, "run_task", new=generator):
        await _drain(_runner([third], run_config, provider))
    assert len(_traces(task)) == 2

    # Evict the newest instance's copy, then add a fourth config with a state-reading
    # scorer: it is skipped, never regenerated, while a trace-only judge still scores.
    newest = next(
        t for t in _traces(task) if t.synthetic_instance.config["fixture_id"] == "b"
    )
    import shutil

    shutil.rmtree(newest.synthetic_instance.path)
    fourth = _config(eval_, scorer.properties, name="fourth")
    fifth = _config(eval_, ExactMatchProperties(expected_value="x"), name="fifth")
    with patch.object(BaseV2EvalBridge, "run_task", new=generator):
        await _drain(_runner([fourth, fifth], run_config, provider))
    assert len(_traces(task)) == 2, "eviction never regenerates"
    fourth_run = fourth.runs(readonly=True)[0]
    assert (
        fourth_run.skipped_reason == SkippedReason.synthetic_instance_unavailable.value
    )
    assert fourth_run.scored_run_id == newest.id
    fifth_run = fifth.runs(readonly=True)[0]
    assert fifth_run.skipped_reason is None


async def test_missing_world_or_fixture_is_an_error_not_a_skip(
    project, task, world, fixtures, real_tool, run_config, eval_, provider
):
    _input(
        task,
        "note",
        SyntheticEnvironment(world_id="nope", config={"fixture_id": "a"}),
        id="ei_bad",
    )
    cfg = _config(eval_, ExactMatchProperties(expected_value="x"))
    generator = ToolCallingGenerator(task, build_code_tool_id(real_tool.id))
    with patch.object(BaseV2EvalBridge, "run_task", new=generator):
        runner = _runner([cfg], run_config, provider)
        job = runner.collect_tasks()[0]
        with pytest.raises(ValueError, match="Synthetic world nope not found"):
            await runner.run_job(job)
    assert generator.outputs == {}
    assert cfg.runs(readonly=True) == []
    assert not (provider.cache_root).exists()


async def test_skipped_job_creates_no_instance(
    project, task, world, fixtures, real_tool, run_config, eval_, provider
):
    _input(task, "note", _env(world, "a"), id="ei_a")
    cfg = _config(eval_, ExactMatchProperties(expected_value="x"))
    generator = ToolCallingGenerator(task, build_code_tool_id(real_tool.id))
    with (
        patch.object(BaseV2EvalBridge, "run_task", new=generator),
        patch(
            "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
            side_effect=NotImplementedError("nope"),
        ),
    ):
        await _drain(_runner([cfg], run_config, provider))
    assert cfg.runs(readonly=True)[0].skipped_reason == "type_not_available"
    assert generator.outputs == {}
    assert not provider.cache_root.exists()


async def test_frozen_time_override_on_input(
    project, task, world, fixtures, real_tool, run_config, eval_, provider
):
    override = datetime(2030, 3, 3, tzinfo=timezone.utc)
    _input(task, "note", _env(world, "a", frozen_time=override), id="ei_a")
    cfg = _config(eval_, ExactMatchProperties(expected_value="x"))
    generator = ToolCallingGenerator(task, build_code_tool_id(real_tool.id))
    with patch.object(BaseV2EvalBridge, "run_task", new=generator):
        await _drain(_runner([cfg], run_config, provider))
    assert generator.outputs["ei_a"] == "synthetic:2030-03-03T00:00:00+00:00"
    assert (
        _traces(task)[0].synthetic_instance.metadata["frozen_time"]
        == override.isoformat()
    )


async def test_prune_runs_before_synthetic_jobs_only(
    project, task, world, fixtures, real_tool, run_config, eval_, provider
):
    _input(task, "note", None, id="ei_plain")
    cfg = _config(eval_, ExactMatchProperties(expected_value="x"))
    generator = ToolCallingGenerator(task, build_code_tool_id(real_tool.id))
    with (
        patch.object(BaseV2EvalBridge, "run_task", new=generator),
        patch.object(provider, "prune") as prune,
    ):
        await _drain(_runner([cfg], run_config, provider))
    prune.assert_not_called()

    _input(task, "note", _env(world, "a"), id="ei_a")
    with (
        patch.object(BaseV2EvalBridge, "run_task", new=generator),
        patch.object(provider, "prune") as prune,
    ):
        await _drain(_runner([cfg], run_config, provider))
    prune.assert_called_once()


async def test_concurrent_judges_share_one_generation_and_copy(
    project, task, world, fixtures, real_tool, run_config, eval_, provider
):
    """Two judges on one read-only item, in one run: the second must still be able to
    read the copy while the first finalizes it. The copy is dropped only at the end."""
    read_only_tool = world.tools()[0]
    read_only_tool.code = "def run(note):\n    return 'looked'\n"
    read_only_tool.save_to_file()
    _input(task, "look", _env(world, "a"), id="ei_a")
    scorer_code = (
        "import os, time\n"
        "def score(output, synthetic_instance):\n"
        "    p = os.path.join(synthetic_instance['path'], 'fixture.db')\n"
        "    ok = os.path.exists(p)\n"
        "    time.sleep(0.3)\n"
        "    ok = ok and os.path.exists(p)\n"
        "    return {'accuracy': 1.0 if ok else 0.0}\n"
    )
    first = _config(
        eval_, CodeEvalProperties(code=scorer_code, timeout_seconds=30), name="first"
    )
    second = _config(
        eval_, CodeEvalProperties(code=scorer_code, timeout_seconds=30), name="second"
    )
    generator = ToolCallingGenerator(task, build_code_tool_id(real_tool.id))
    with patch.object(BaseV2EvalBridge, "run_task", new=generator):
        await _drain(_runner([first, second], run_config, provider))
    assert len(_traces(task)) == 1
    assert len(generator.outputs) == 1
    for cfg in (first, second):
        run = cfg.runs(readonly=True)[0]
        assert run.skipped_reason is None, cfg.name
        assert run.scores == {"accuracy": 1.0}, cfg.name
    trace = _traces(task)[0]
    assert trace.synthetic_instance.unchanged is True
    assert not Path(trace.synthetic_instance.path).exists()


async def test_missing_fixture_is_a_job_error_at_launch(
    project, task, world, fixtures, real_tool, run_config, eval_, provider
):
    """The world resolves but the launcher does not know the fixture: the job errors
    before any generation and nothing is persisted."""
    _input(task, "note", _env(world, "nope"), id="ei_bad")
    cfg = _config(eval_, ExactMatchProperties(expected_value="x"))
    generator = ToolCallingGenerator(task, build_code_tool_id(real_tool.id))
    with patch.object(BaseV2EvalBridge, "run_task", new=generator):
        runner = _runner([cfg], run_config, provider)
        job = runner.collect_tasks()[0]
        with pytest.raises(ValueError, match="Fixture 'nope' not found"):
            await runner.run_job(job)
    assert generator.outputs == {}
    assert _traces(task) == []


async def test_world_launcher_selected_by_name(
    project, task, world, fixtures, real_tool, run_config, eval_
):
    """Without an injected launcher, the runner picks the world's own launcher by name,
    and an unregistered name is a job error rather than a silent fallback."""
    _input(task, "note", _env(world, "a"), id="ei_a")
    cfg = _config(eval_, ExactMatchProperties(expected_value="x"))
    generator = ToolCallingGenerator(task, build_code_tool_id(real_tool.id))
    world.launcher = "not_a_registered_launcher"
    world.save_to_file()
    with patch.object(BaseV2EvalBridge, "run_task", new=generator):
        runner = _runner([cfg], run_config, None)
        job = runner.collect_tasks()[0]
        with pytest.raises(ValueError, match="not_a_registered_launcher"):
            await runner.run_job(job)
    assert generator.outputs == {}


class RecordingLauncher(LocalFilesLauncher):
    """A launcher that, at finalize, records what the run changed and judges runs
    that wrote anything as invalid — the shape a hosted framework's launcher takes."""

    async def finalize(self, instance):
        settled = await super().finalize(instance)
        counter = Path(settled.effective_path or "") / "counter.txt"
        lines = counter.read_text().splitlines() if counter.exists() else []
        return settled.model_copy(
            update={
                "changes": {"counter_lines": lines},
                "valid": not lines,
                "invalid_reason": "run wrote to the counter" if lines else None,
            }
        )


CHANGES_SCORER = (
    "def score(output, synthetic_instance):\n"
    "    lines = synthetic_instance['changes']['counter_lines']\n"
    "    return {'accuracy': float(len(lines))}\n"
)


async def test_finalize_settles_record_before_grading(
    project, task, world, fixtures, real_tool, run_config, eval_, tmp_path
):
    """The launcher's finalize runs after generation and before any grader: scorers
    read what it recorded (`changes`), judges see its validity verdict, and the trace
    persists the settled record. A non-strict world still grades an invalid run."""
    _input(task, "note", _env(world, "a"), id="ei_a")
    judge = _config(eval_, ExactMatchProperties(expected_value="x"), name="judge")
    scorer = _config(
        eval_, CodeEvalProperties(code=CHANGES_SCORER, timeout_seconds=30), name="s"
    )
    launcher = RecordingLauncher(cache_root=tmp_path / "cache", max_bytes=10**9)
    generator = ToolCallingGenerator(task, build_code_tool_id(real_tool.id))
    with patch.object(BaseV2EvalBridge, "run_task", new=generator):
        await _drain(_runner([scorer], run_config, launcher))

    (trace,) = _traces(task)
    assert trace.synthetic_instance is not None
    assert trace.synthetic_instance.changes == {"counter_lines": ["note"]}
    assert trace.synthetic_instance.valid is False
    assert trace.synthetic_instance.invalid_reason == "run wrote to the counter"

    scorer_run = scorer.runs(readonly=True)[0]
    assert scorer_run.skipped_reason is None
    assert scorer_run.scores == {"accuracy": 1.0}

    # A judge reusing the trace sees the launcher's verdict, and nothing else.
    with (
        patch.object(BaseV2EvalBridge, "run_task", new=generator),
        patch(
            "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
            side_effect=lambda config, *args, **kwargs: RecordingJudge(config),
        ),
    ):
        await _drain(_runner([judge], run_config, launcher))
    assert len(_traces(task)) == 1
    judge_run = judge.runs(readonly=True)[0]
    assert judge_run.skipped_reason is None
    (seen,) = RecordingJudge.seen
    assert seen.synthetic_instance is not None
    assert seen.synthetic_instance.valid is False
    assert seen.synthetic_instance.invalid_reason == "run wrote to the counter"


async def test_strict_world_skips_grading_an_invalid_run(
    project, task, world, fixtures, real_tool, run_config, eval_, tmp_path
):
    world.strict = True
    world.save_to_file()
    _input(task, "note", _env(world, "a"), id="ei_a")
    judge = _config(eval_, ExactMatchProperties(expected_value="x"), name="judge")
    launcher = RecordingLauncher(cache_root=tmp_path / "cache", max_bytes=10**9)
    generator = ToolCallingGenerator(task, build_code_tool_id(real_tool.id))
    with patch.object(BaseV2EvalBridge, "run_task", new=generator):
        await _drain(_runner([judge], run_config, launcher))

    assert len(_traces(task)) == 1, "the generation is kept; only grading is skipped"
    run = judge.runs(readonly=True)[0]
    assert run.skipped_reason == SkippedReason.synthetic_instance_invalid.value
    assert "run wrote to the counter" in (run.skipped_detail or "")
    assert RecordingJudge.seen == []

    # A later judge on the same trace is skipped the same way, without regenerating.
    later = _config(eval_, ExactMatchProperties(expected_value="x"), name="later")
    with patch.object(BaseV2EvalBridge, "run_task", new=generator):
        await _drain(_runner([later], run_config, launcher))
    assert len(_traces(task)) == 1
    assert (
        later.runs(readonly=True)[0].skipped_reason
        == SkippedReason.synthetic_instance_invalid.value
    )


async def test_regenerated_fixture_bytes_regenerate_the_trace(
    project, task, world, fixtures, real_tool, run_config, eval_, provider
):
    """Same fixture id, different bytes: the launcher's content version moves, so the
    trace variant moves and the item is generated again rather than reused."""
    _input(task, "note", _env(world, "a"), id="ei_a")
    first = _config(eval_, ExactMatchProperties(expected_value="x"), name="first")
    generator = ToolCallingGenerator(task, build_code_tool_id(real_tool.id))
    with patch.object(BaseV2EvalBridge, "run_task", new=generator):
        await _drain(_runner([first], run_config, provider))
    assert len(_traces(task)) == 1

    (fixtures["a"] / "fixture.db").write_bytes(b"a-data-regenerated")
    second = _config(eval_, ExactMatchProperties(expected_value="x"), name="second")
    with patch.object(BaseV2EvalBridge, "run_task", new=generator):
        await _drain(_runner([second], run_config, provider))
    traces = _traces(task)
    assert len(traces) == 2
    assert len({t.eval_source.variant for t in traces}) == 2
    assert len({t.synthetic_instance.content_version for t in traces}) == 2
