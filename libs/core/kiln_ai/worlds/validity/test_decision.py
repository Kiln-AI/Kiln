from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.datamodel.task import Task, TaskRunConfig
from kiln_ai.datamodel.world import OpenEnvTool, WorldEpisode, WorldReset
from kiln_ai.datamodel.world import World as KilnWorld
from kiln_ai.run_context import get_episode

from . import decision as decision_module
from .conftest import (
    assistant_message,
    episode,
    error_result,
    system_message,
    tool_call,
    tool_message,
    user_message,
)
from .cost import CostMeter, Pricing
from .decision import (
    Call,
    DecisionSelection,
    RecordingSessionManager,
    StopReplay,
    build_prefix,
    divergent_prefix,
    load_records,
    replay_all_decisions,
    replay_decision,
    select_decisions,
)
from .replay import Mismatch, ReplayedEpisode
from .scrub import ScrubRules

RULES = ScrubRules(
    placeholder_fields=frozenset(),
    ignored_fields=frozenset(),
    free_text_fields=frozenset({"text"}),
    id_fields=frozenset(),
    transport_codes=frozenset(),
    declared={},
)


def two_step_episode(**kwargs):
    return episode(
        system_message("prompt"),
        user_message("ask"),
        assistant_message(tool_call("c1", "get_note", note_id="n1")),
        tool_message("c1", {"id": "n1", "text": "first"}),
        assistant_message(tool_call("c2", "finish_note", note_id="n1")),
        tool_message("c2", {"id": "n1", "done": True}),
        assistant_message(content="all done"),
        **kwargs,
    )


def replayed_for(recorded, results, *, divergent=frozenset(), skipped=()):
    return ReplayedEpisode(
        run_id=recorded.run_id,
        results=list(results),
        mismatches=[
            Mismatch(
                run_id=recorded.run_id,
                configuration=recorded.configuration,
                step_index=index,
                tool_name="x",
                arguments={},
                recorded=None,
                replayed=None,
                diffs=[],
                kind="unserved",
                declared=(),
                classes=(),
            )
            for index in skipped
        ],
        id_pairs=[],
        divergent_steps=frozenset(divergent),
    )


# ---- build_prefix ----


def test_build_prefix_first_decision_uses_recorded_system_message():
    recorded = two_step_episode()
    prior, model_input = build_prefix(recorded, 0, None)
    assert prior == [{"role": "system", "content": "prompt"}]
    assert model_input == "ask"


def test_build_prefix_substitutes_world_results_and_tool_input():
    recorded = two_step_episode()
    prior, model_input = build_prefix(
        recorded, 1, [{"id": "n1", "text": "world text"}, None]
    )
    assert prior is not None
    assert [m["role"] for m in prior] == ["system", "user", "assistant"]
    assert model_input == [
        {
            "tool_call_id": "c1",
            "content": json.dumps({"id": "n1", "text": "world text"}),
            "is_error": None,
            "error_message": None,
        }
    ]


def test_build_prefix_substitutes_inside_the_prior_trace():
    recorded = two_step_episode()
    prior, _ = build_prefix(
        recorded, 2, [{"id": "n1", "text": "world text"}, {"id": "n1", "done": False}]
    )
    assert prior is not None
    tool_messages = [m for m in prior if m.get("role") == "tool"]
    assert [m["content"] for m in tool_messages] == [
        json.dumps({"id": "n1", "text": "world text"})
    ]


def test_build_prefix_control_arm_keeps_raw_content():
    recorded = two_step_episode()
    _, model_input = build_prefix(recorded, 1, None)
    assert model_input == [
        {
            "tool_call_id": "c1",
            "content": json.dumps({"id": "n1", "text": "first"}),
            "is_error": None,
            "error_message": None,
        }
    ]


def test_build_prefix_unserved_step_falls_back_to_raw_content():
    """A step the world never answered keeps the recorded text; a world result that is
    genuinely null does not, which is why the skipped steps are named explicitly."""
    recorded = two_step_episode()
    _, unserved = build_prefix(recorded, 1, [None, None], raw_steps=frozenset({0}))
    assert unserved[0]["content"] == json.dumps({"id": "n1", "text": "first"})

    _, null_result = build_prefix(recorded, 1, [None, None])
    assert null_result[0]["content"] == "null"


def test_build_prefix_world_failure_is_flagged_as_an_error():
    recorded = two_step_episode()
    _, model_input = build_prefix(
        recorded, 1, [error_result("world_gap", "nope"), None]
    )
    assert model_input[0]["is_error"] is True
    assert model_input[0]["error_message"] == "nope"

    _, product_error = build_prefix(
        recorded, 1, [error_result("not_found", "no note"), None]
    )
    assert product_error[0]["is_error"] is None


# ---- the recording session manager ----


async def test_recording_session_manager_call_tool_raises_stop_replay():
    manager = RecordingSessionManager()
    world_episode = WorldEpisode(
        reset=WorldReset(world_id="w", reset_kwargs={}),
        episode_id="e",
        world_version="v",
    )
    with pytest.raises(StopReplay):
        await manager.call_tool(world_episode, "get_note", {"note_id": "n1"})
    assert manager.calls == [("call_tool", "get_note", {"note_id": "n1"})]

    with pytest.raises(StopReplay):
        await manager.start_episode(KilnWorld(name="w"), {})
    with pytest.raises(StopReplay):
        await manager.end_episode(world_episode)
    with pytest.raises(StopReplay):
        await manager.world_version(KilnWorld(name="w"), {})
    with pytest.raises(StopReplay):
        await manager.list_tools(KilnWorld(name="w"))


async def test_recording_session_manager_control_tool_is_a_no_op():
    manager = RecordingSessionManager()
    world_episode = WorldEpisode(
        reset=WorldReset(world_id="w", reset_kwargs={}),
        episode_id="e",
        world_version="v",
    )
    outcome = await manager.call_control_tool(world_episode, "controller_changes", {})
    assert outcome.error_code == "unknown_tool"
    assert outcome.result is None
    await manager.release(world_episode)
    await manager.shutdown()


# ---- selection ----


def test_divergent_prefix_true_after_first_divergent_step():
    recorded = two_step_episode()
    replayed = replayed_for(recorded, [None, None], divergent={0})
    assert divergent_prefix(recorded, replayed, 0) is False
    assert divergent_prefix(recorded, replayed, 1) is True
    assert divergent_prefix(recorded, replayed, 2) is True
    assert divergent_prefix(recorded, replayed, 9) is False


def test_select_decisions_all_divergent_plus_seeded_control_sample():
    episodes = [two_step_episode(run_id=f"run-{n}") for n in range(4)]
    replayed = {
        e.run_id: replayed_for(e, [None, None], divergent={0} if n == 0 else set())
        for n, e in enumerate(episodes)
    }
    selection = select_decisions(episodes, replayed, control_sample=100)
    assert selection.divergent == [("run-0", 1), ("run-0", 2)]
    assert len(selection.control) == 10
    assert selection.prefix_of("run-0", 1) == "divergent"
    assert selection.prefix_of("run-1", 1) == "control"

    sampled = select_decisions(episodes, replayed, control_sample=3, seed=7)
    again = select_decisions(episodes, replayed, control_sample=3, seed=7)
    assert len(sampled.control) == 3
    assert sampled.control == again.control


# ---- replay_decision ----


@dataclass
class FakeRun:
    trace: list[dict[str, Any]]
    usage: Any = None


@dataclass
class FakeAdapter:
    reply: list[dict[str, Any]]
    seen: list[tuple[Any, Any]] = field(default_factory=list)
    fail: Exception | None = None

    async def invoke(self, model_input, prior_trace=None, **kwargs):
        self.seen.append((prior_trace, model_input))
        if self.fail is not None:
            raise self.fail
        return FakeRun(trace=list(prior_trace or []) + self.reply)


@pytest.fixture
def harness(tmp_path, monkeypatch):
    task = Task(name="Harness", instruction="do it", path=tmp_path / "task.kiln")
    task.save_to_file()
    run_config = TaskRunConfig(
        name="A-world-r1",
        parent=task,
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="model",
            model_provider_name="openai",
            prompt_id="simple_prompt_builder",
            temperature=0.0,
            structured_output_mode="default",
        ),
    )
    run_config.save_to_file()
    world = KilnWorld(name="notes", env_url="http://127.0.0.1:8010")
    tools = {"get_note": OpenEnvTool(name="get_note")}
    return task, run_config, world, tools


def patch_adapter(monkeypatch, adapter: FakeAdapter) -> None:
    monkeypatch.setattr(
        decision_module, "adapter_for_task", lambda *args, **kwargs: adapter
    )


async def test_replay_decision_agree_on_same_multiset(harness, monkeypatch):
    task, run_config, world, tools = harness
    recorded = two_step_episode()
    adapter = FakeAdapter(
        reply=[assistant_message(tool_call("x", "finish_note", note_id="n1"))]
    )
    patch_adapter(monkeypatch, adapter)

    record = await replay_decision(
        task,
        run_config,
        world,
        tools,
        {},
        recorded,
        1,
        "world",
        replayed_for(recorded, [{"id": "n1"}, None]),
        RULES,
        prefix="divergent",
    )
    assert record.agree is True
    assert record.name_match and record.args_match
    assert record.recorded == [Call("finish_note", {"note_id": "n1"})]
    assert record.error is None
    assert record.prefix == "divergent"


async def test_replay_decision_free_text_rewording_agrees(harness, monkeypatch):
    task, run_config, world, tools = harness
    recorded = episode(
        system_message(),
        user_message(),
        assistant_message(tool_call("c1", "create_note", text="Please review")),
        tool_message("c1", {"id": "n2"}),
        assistant_message(content="done"),
    )
    adapter = FakeAdapter(
        reply=[
            assistant_message(
                tool_call("x", "create_note", text="Kindly take a look at this")
            )
        ]
    )
    patch_adapter(monkeypatch, adapter)

    record = await replay_decision(
        task, run_config, world, tools, {}, recorded, 0, "control", None, RULES
    )
    assert record.agree is True
    assert record.replayed == [Call("create_note", {"text": "string"})]


async def test_replay_decision_final_answer_vs_tool_call_disagrees(
    harness, monkeypatch
):
    task, run_config, world, tools = harness
    recorded = two_step_episode()
    patch_adapter(
        monkeypatch, FakeAdapter(reply=[assistant_message(content="I'm done")])
    )

    record = await replay_decision(
        task, run_config, world, tools, {}, recorded, 1, "control", None, RULES
    )
    assert record.replayed == []
    assert record.agree is False
    assert record.name_match is False


async def test_replay_decision_sets_and_resets_episode_context(harness, monkeypatch):
    task, run_config, world, tools = harness
    recorded = two_step_episode()
    seen: list[Any] = []

    @dataclass
    class Watcher(FakeAdapter):
        async def invoke(self, model_input, prior_trace=None, **kwargs):
            seen.append(get_episode())
            return FakeRun(trace=self.reply)

    patch_adapter(monkeypatch, Watcher(reply=[assistant_message(content="done")]))
    await replay_decision(
        task,
        run_config,
        world,
        tools,
        {},
        recorded,
        0,
        "world",
        None,
        RULES,
        reset_kwargs={"fixture": "base"},
    )
    assert get_episode() is None
    context = seen[0]
    assert context is not None
    assert context.world is world
    assert isinstance(context.session_manager, RecordingSessionManager)
    assert context.episode.reset.reset_kwargs == {"fixture": "base"}
    assert context.tools == tools


async def test_replay_decision_records_adapter_error(harness, monkeypatch):
    task, run_config, world, tools = harness
    recorded = two_step_episode()
    adapter = FakeAdapter(reply=[], fail=RuntimeError("boom"))
    patch_adapter(monkeypatch, adapter)

    record = await replay_decision(
        task, run_config, world, tools, {}, recorded, 0, "world", None, RULES
    )
    assert record.error == "RuntimeError"
    assert record.agree is False
    assert get_episode() is None


async def test_replay_decision_unwraps_stop_replay(harness, monkeypatch):
    task, run_config, world, tools = harness
    recorded = two_step_episode()

    class Wrapped(RuntimeError):
        def __init__(self) -> None:
            super().__init__("wrapped")
            self.original = StopReplay("a tool ran")

    patch_adapter(monkeypatch, FakeAdapter(reply=[], fail=Wrapped()))
    record = await replay_decision(
        task, run_config, world, tools, {}, recorded, 0, "world", None, RULES
    )
    assert record.error == "StopReplay"


# ---- replay_all_decisions ----


async def test_replay_all_decisions_refuses_nonzero_temperature(
    harness, monkeypatch, tmp_path
):
    task, run_config, world, tools = harness
    hot = run_config.model_copy(deep=True)
    hot.run_config_properties.temperature = 1.0
    recorded = two_step_episode()
    patch_adapter(monkeypatch, FakeAdapter(reply=[assistant_message(content="x")]))

    with pytest.raises(ValueError, match="temperature-0"):
        await replay_all_decisions(
            task,
            lambda episode: hot,
            world,
            tools,
            {},
            [recorded],
            {recorded.run_id: replayed_for(recorded, [None, None])},
            DecisionSelection(divergent=[], control=[(recorded.run_id, 0)]),
            RULES,
            out=tmp_path / "decision.jsonl",
        )


async def test_replay_all_decisions_writes_both_arms(harness, monkeypatch, tmp_path):
    task, run_config, world, tools = harness
    recorded = two_step_episode()
    patch_adapter(monkeypatch, FakeAdapter(reply=[assistant_message(content="x")]))
    out = tmp_path / "decision.jsonl"

    records = await replay_all_decisions(
        task,
        lambda episode: run_config,
        world,
        tools,
        {},
        [recorded],
        {recorded.run_id: replayed_for(recorded, [None, None], divergent={0})},
        DecisionSelection(
            divergent=[(recorded.run_id, 1)], control=[(recorded.run_id, 0)]
        ),
        RULES,
        out=out,
    )
    assert len(records) == 4
    lines = [json.loads(line) for line in out.read_text().splitlines()]
    assert {(line["decision_index"], line["arm"]) for line in lines} == {
        (0, "world"),
        (0, "control"),
        (1, "world"),
        (1, "control"),
    }
    assert {line["prefix"] for line in lines} == {"divergent", "control"}
    assert {line["temperature"] for line in lines} == {0.0}
    assert {line["schema_version"] for line in lines} == {1}


async def test_replay_all_decisions_resumes_from_existing_lines(
    harness, monkeypatch, tmp_path
):
    task, run_config, world, tools = harness
    recorded = two_step_episode()
    patch_adapter(monkeypatch, FakeAdapter(reply=[assistant_message(content="x")]))
    out = tmp_path / "decision.jsonl"
    out.write_text(
        json.dumps(
            {
                "run_id": recorded.run_id,
                "configuration": "A",
                "decision_index": 0,
                "arm": "world",
                "prefix": "control",
                "recorded": [{"tool_name": "get_note", "arguments": {"note_id": "n1"}}],
                "replayed": [{"tool_name": "get_note", "arguments": {"note_id": "n1"}}],
                "name_match": True,
                "args_match": True,
                "agree": True,
            }
        )
        # A real truncation: a partial line with no newline of its own. Writing garbage
        # *with* a trailing newline is the one shape a crash cannot produce.
        + '\n{"run_id": "run-1", "decision_ind'
    )

    records = await replay_all_decisions(
        task,
        lambda episode: run_config,
        world,
        tools,
        {},
        [recorded],
        {recorded.run_id: replayed_for(recorded, [None, None])},
        DecisionSelection(divergent=[], control=[(recorded.run_id, 0)]),
        RULES,
        out=out,
    )
    # the resumed record comes back alongside the new one: a statistic handed only the
    # new half would drop the world arm's control twin and could report a measurable
    # gate as not_measurable
    assert sorted((r.decision_index, r.arm) for r in records) == [
        (0, "control"),
        (0, "world"),
    ]
    resumed = next(r for r in records if r.arm == "world")
    assert resumed.agree is True
    assert resumed.recorded == [Call("get_note", {"note_id": "n1"})]


async def test_load_records_round_trips_what_was_written(
    harness, monkeypatch, tmp_path
):
    task, run_config, world, tools = harness
    recorded = two_step_episode()
    patch_adapter(
        monkeypatch,
        FakeAdapter(
            reply=[assistant_message(tool_call("x", "finish_note", note_id="n1"))]
        ),
    )
    out = tmp_path / "decision.jsonl"
    written = await replay_all_decisions(
        task,
        lambda episode: run_config,
        world,
        tools,
        {},
        [recorded],
        {recorded.run_id: replayed_for(recorded, [None, None], divergent={0})},
        DecisionSelection(divergent=[(recorded.run_id, 1)], control=[]),
        RULES,
        out=out,
    )
    reloaded = load_records(out)
    assert sorted((r.arm, r.agree, r.prefix) for r in reloaded) == sorted(
        (r.arm, r.agree, r.prefix) for r in written
    )
    assert reloaded[0].recorded == written[0].recorded


def test_load_records_on_a_file_that_is_not_there():
    assert load_records(Path("/nonexistent/decision.jsonl")) == []


async def test_replay_all_decisions_stops_on_budget(harness, monkeypatch, tmp_path):
    task, run_config, world, tools = harness
    episodes = [two_step_episode(run_id=f"run-{n}") for n in range(6)]
    patch_adapter(
        monkeypatch,
        FakeAdapter(reply=[assistant_message(content="x")]),
    )
    monkeypatch.setattr(
        decision_module,
        "replay_decision",
        _costed_replay_decision,
    )
    meter = CostMeter(0.005, {"model": Pricing(1000.0, 1000.0)})
    out = tmp_path / "decision.jsonl"

    records = await replay_all_decisions(
        task,
        lambda episode: run_config,
        world,
        tools,
        {},
        episodes,
        {e.run_id: replayed_for(e, [None, None]) for e in episodes},
        DecisionSelection(divergent=[], control=[(e.run_id, 0) for e in episodes]),
        RULES,
        arms=("world",),
        concurrency=1,
        meter=meter,
        out=out,
    )
    assert 0 < len(records) < len(episodes)
    assert meter.spent_usd > 0.005
    assert len(out.read_text().splitlines()) == len(records)


async def _costed_replay_decision(task, run_config, *args, **kwargs):
    from .decision import DecisionRecord

    episode_arg = args[3]
    return DecisionRecord(
        run_id=episode_arg.run_id,
        configuration=episode_arg.configuration,
        decision_index=args[4],
        arm=args[5],
        prefix=kwargs.get("prefix", "control"),
        recorded=[],
        replayed=[],
        name_match=True,
        args_match=True,
        agree=True,
        usage={"input_tokens": 1000, "output_tokens": 1000},
        error=None,
    )


async def test_replay_all_decisions_appends_cleanly_after_a_truncated_line(
    harness, monkeypatch, tmp_path
):
    """The next record must not be concatenated onto the partial one, or both are lost."""
    task, run_config, world, tools = harness
    recorded = two_step_episode()
    patch_adapter(monkeypatch, FakeAdapter(reply=[assistant_message(content="x")]))
    out = tmp_path / "decision.jsonl"
    out.write_text('{"run_id": "run-1", "decision_ind')

    records = await replay_all_decisions(
        task,
        lambda episode: run_config,
        world,
        tools,
        {},
        [recorded],
        {recorded.run_id: replayed_for(recorded, [None, None])},
        DecisionSelection(divergent=[], control=[(recorded.run_id, 0)]),
        RULES,
        arms=("world",),
        out=out,
    )
    assert len(records) == 1
    assert len(load_records(out)) == 1, (
        "the appended record was eaten by the partial line"
    )


async def test_replay_all_decisions_drops_resumed_records_outside_the_selection(
    harness, monkeypatch, tmp_path
):
    """The control arm is a seeded sample, so a resume after the selection changed would
    otherwise fold decisions outside it into the statistic."""
    task, run_config, world, tools = harness
    recorded = two_step_episode()
    patch_adapter(monkeypatch, FakeAdapter(reply=[assistant_message(content="x")]))
    out = tmp_path / "decision.jsonl"
    out.write_text(
        json.dumps(
            {
                "run_id": recorded.run_id,
                "configuration": "A",
                "decision_index": 2,
                "arm": "world",
                "prefix": "control",
                "recorded": [],
                "replayed": [],
                "name_match": True,
                "args_match": True,
                "agree": True,
            }
        )
        + "\n"
    )

    records = await replay_all_decisions(
        task,
        lambda episode: run_config,
        world,
        tools,
        {},
        [recorded],
        {recorded.run_id: replayed_for(recorded, [None, None])},
        DecisionSelection(divergent=[], control=[(recorded.run_id, 0)]),
        RULES,
        arms=("world",),
        out=out,
    )
    assert [r.decision_index for r in records] == [0]


async def test_replay_all_decisions_runs_an_overlapping_selection_once(
    harness, monkeypatch, tmp_path
):
    task, run_config, world, tools = harness
    recorded = two_step_episode()
    adapter = FakeAdapter(reply=[assistant_message(content="x")])
    patch_adapter(monkeypatch, adapter)
    out = tmp_path / "decision.jsonl"

    records = await replay_all_decisions(
        task,
        lambda episode: run_config,
        world,
        tools,
        {},
        [recorded],
        {recorded.run_id: replayed_for(recorded, [None, None], divergent={0})},
        DecisionSelection(
            divergent=[(recorded.run_id, 1)], control=[(recorded.run_id, 1)]
        ),
        RULES,
        arms=("world",),
        out=out,
    )
    assert len(records) == 1
    assert len(adapter.seen) == 1
    assert records[0].prefix == "divergent"


async def test_load_records_skips_a_record_with_an_unknown_arm(tmp_path):
    out = tmp_path / "decision.jsonl"
    out.write_text(
        json.dumps(
            {
                "run_id": "run-1",
                "decision_index": 0,
                "arm": "sideways",
                "prefix": "control",
            }
        )
        + "\n"
    )
    assert load_records(out) == []
