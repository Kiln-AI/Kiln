from __future__ import annotations

import pytest

from kiln_ai.datamodel.basemodel import KilnParentedModel
from kiln_ai.datamodel.datamodel_enums import TaskOutputRatingType
from kiln_ai.datamodel.eval import (
    Eval,
    EvalConfig,
    EvalInput,
    EvalInputSplit,
    EvalOutputScore,
    EvalRun,
    SingleTurnEvalInputData,
    UserMessage,
)
from kiln_ai.datamodel.task import Task
from kiln_ai.datamodel.task_output import DataSource, DataSourceType, TaskOutput
from kiln_ai.datamodel.task_run import EvalItemSource, TaskRun
from kiln_ai.datamodel.world import WorldEpisode, WorldReset
from kiln_ai.utils.usage import Usage

from .conftest import (
    assistant_message,
    episode,
    error_result,
    system_message,
    tool_call,
    tool_message,
    trace,
    user_message,
)
from .traces import (
    changes,
    content_text,
    extract_steps,
    final_state,
    invalid_reason,
    load_episodes,
    settle_error,
    step_count,
    world_gap,
)
from .traces import system_message as trace_system_message
from .traces import user_message as trace_user_message

TRANSPORT = frozenset({"upstream_error", "rate_limited"})


def test_extract_steps_pairs_calls_with_tool_messages_in_order():
    steps = extract_steps(
        trace(
            system_message(),
            user_message(),
            assistant_message(tool_call("c1", "get_note", note_id="n1")),
            tool_message("c1", {"id": "n1"}),
            assistant_message(tool_call("c2", "finish_note", note_id="n1")),
            tool_message("c2", {"id": "n1", "done": True}),
        )
    )
    assert [(s.index, s.tool_name, s.arguments) for s in steps] == [
        (0, "get_note", {"note_id": "n1"}),
        (1, "finish_note", {"note_id": "n1"}),
    ]
    assert [s.message_index for s in steps] == [2, 4]
    assert [s.parallel for s in steps] == [False, False]
    assert steps[0].result == {"id": "n1"}


def test_extract_steps_parallel_group_flagged():
    steps = extract_steps(
        trace(
            assistant_message(
                tool_call("c1", "create_note", text="a"),
                tool_call("c2", "create_note", text="b"),
            ),
            tool_message("c1", {"id": "x"}),
            tool_message("c2", {"id": "y"}),
        )
    )
    assert [s.parallel for s in steps] == [True, True]
    assert [s.call_id for s in steps] == ["c1", "c2"]


def test_extract_steps_error_envelope_code():
    steps = extract_steps(
        trace(
            assistant_message(tool_call("c1", "get_note", note_id="nope")),
            tool_message("c1", error_result("not_found")),
        )
    )
    assert steps[0].error_code == "not_found"
    assert steps[0].is_error is False


def test_extract_steps_dangling_call_id_raises():
    with pytest.raises(ValueError, match="has no tool message"):
        extract_steps(
            trace(assistant_message(tool_call("c1", "get_note", note_id="n1")))
        )


def test_extract_steps_orphan_tool_message_raises():
    with pytest.raises(ValueError, match="answer calls that are not in the trace"):
        extract_steps(trace(user_message(), tool_message("c9", {"id": "n"})))


def test_extract_steps_non_json_content_is_kept_verbatim():
    steps = extract_steps(
        trace(
            assistant_message(tool_call("c1", "get_note", note_id="n1")),
            tool_message("c1", None, raw="not json at all"),
        )
    )
    assert steps[0].result == "not json at all"
    assert steps[0].raw_content == "not json at all"


def test_extract_steps_malformed_arguments_send_nothing():
    message = assistant_message(tool_call("c1", "get_note"))
    message["tool_calls"][0]["function"]["arguments"] = "{not json"
    steps = extract_steps(trace(message, tool_message("c1", error_result("invalid"))))
    assert steps[0].arguments == {}


def test_step_count_counts_every_tool_call():
    assert (
        step_count(
            trace(
                assistant_message(tool_call("c1", "a"), tool_call("c2", "b")),
                tool_message("c1", {}),
                tool_message("c2", {}),
                assistant_message(content="done"),
            )
        )
        == 2
    )


def test_system_and_user_messages_are_read_from_the_trace():
    built = trace(system_message("prompt"), user_message("ask"))
    assert trace_system_message(built) == "prompt"
    assert trace_user_message(built) == "ask"


def test_world_gap_finds_first_gap_step():
    recorded = episode(
        assistant_message(tool_call("c1", "get_note", note_id="n1")),
        tool_message("c1", {"id": "n1"}),
        assistant_message(tool_call("c2", "archive_note", note_id="n1")),
        tool_message("c2", error_result("world_gap"), is_error=True),
        system="world",
    )
    gap = world_gap(recorded)
    assert gap is not None and gap.tool_name == "archive_note"
    assert world_gap(episode(user_message())) is None


def test_changes_null_reads_as_absent():
    """A settle call that succeeded with a null result writes `changes: null`. Absent and
    null are one answer, so a caller asking for a length never gets a TypeError."""
    with_changes = episode(
        user_message(), world_episode={"final_state": {"changes": [{"table": "notes"}]}}
    )
    assert changes(with_changes) == [{"table": "notes"}]
    assert changes(episode(user_message(), world_episode={"final_state": {}})) is None
    assert (
        changes(
            episode(user_message(), world_episode={"final_state": {"changes": None}})
        )
        is None
    )
    assert changes(episode(user_message())) is None


@pytest.mark.parametrize(
    "system,steps_trace,world_episode,marker,malformed,expected",
    [
        ("world", [], {"final_state": {}}, None, False, None),
        ("real", [], None, None, False, None),
        ("real", [], None, None, True, "malformed_trace"),
        ("real", [], None, "reset_anomaly", False, "reset_anomaly"),
        ("real", [], None, "judge_failure", False, "judge_failure"),
        ("world", [], None, "provider_error", False, "provider_error"),
        ("world", ["world_gap"], None, None, False, "world_gap"),
        (
            "world",
            [],
            {"final_state": {"settle_error": {"tool": "t", "code": "c"}}},
            None,
            False,
            "settle_error",
        ),
        ("real", ["upstream_error"], None, None, False, "upstream_error"),
        ("real", ["rate_limited"], None, None, False, "rate_limited"),
        ("real", ["not_found"], None, None, False, None),
        # a world gap on the real lane is not a real-lane reason; the lanes are separate
        ("real", ["world_gap"], None, None, False, None),
    ],
)
def test_invalid_reason_symmetric_rules(
    system, steps_trace, world_episode, marker, malformed, expected
):
    messages: list = []
    for index, code in enumerate(steps_trace):
        messages.append(assistant_message(tool_call(f"c{index}", "get_note")))
        messages.append(tool_message(f"c{index}", error_result(code)))
    recorded = (
        episode(*messages, system=system) if messages else episode(user_message())
    )
    assert (
        invalid_reason(
            system=system,
            steps=recorded.steps,
            world_episode=world_episode,
            marker=marker,
            malformed=malformed,
            transport_codes=TRANSPORT,
        )
        == expected
    )


# ---- load_episodes ----


def _project(tmp_path) -> Task:
    task = Task(name="Harness", instruction="do the thing", path=tmp_path / "task.kiln")
    task.save_to_file()
    return task


def _source() -> DataSource:
    return DataSource(
        type=DataSourceType.synthetic,
        properties={
            "model_name": "m",
            "model_provider": "p",
            "adapter_name": "kiln_agent",
        },
    )


def _eval_config(task: Task) -> EvalConfig:
    evaluator = Eval(
        name="Validity",
        parent=task,
        output_scores=[
            EvalOutputScore(
                name="predicates_pass", type=TaskOutputRatingType.pass_fail
            ),
            EvalOutputScore(
                name="collateral_pass", type=TaskOutputRatingType.pass_fail
            ),
        ],
        splits={"test": EvalInputSplit(filter_id="tag::real")},
    )
    evaluator.save_to_file()
    config = EvalConfig(
        name="judge",
        model_name="model",
        model_provider="provider",
        parent=evaluator,
        properties={"eval_steps": ["one"]},
    )
    config.save_to_file()
    return config


def _input(task: Task, input_no: int, tags: list[str]) -> EvalInput:
    item = EvalInput(
        parent=task,
        data=SingleTurnEvalInputData(user_message=UserMessage(text="ask")),
        reference={"input_no": input_no},
        tags=tags,
    )
    item.save_to_file()
    return item


def _run(
    task: Task,
    item: EvalInput,
    run_config_id: str,
    messages: list,
    *,
    world_episode: WorldEpisode | None = None,
    usage: Usage | None = None,
) -> TaskRun:
    source = _source()
    source.run_config_id = run_config_id
    run = TaskRun(
        parent=task,
        input="ask",
        input_source=_source(),
        output=TaskOutput(output="done", source=source),
        trace=messages,
        eval_source=EvalItemSource(source_type="eval_input", source_id=str(item.id)),
        world_episode=world_episode,
        usage=usage,
    )
    run.save_to_file()
    return run


def _world_episode(final_state: dict | None) -> WorldEpisode:
    return WorldEpisode(
        reset=WorldReset(world_id="world-1", reset_kwargs={"fixture": "notes-v1"}),
        episode_id="ep_abc",
        world_version="notes@1",
        reset_facts={"now": "2026-03-04T00:00:00Z"},
        final_state=final_state,
    )


def _score(
    config: EvalConfig, item: EvalInput, run: TaskRun, run_config_id: str, scores: dict
) -> EvalRun:
    record = EvalRun(
        parent=config,
        eval_input_id=item.id,
        scored_run_id=run.id,
        task_run_config_id=run_config_id,
        scores=scores,
    )
    record.save_to_file()
    return record


RUN_CONFIGS = {
    "rc-real": ("A", "real", 1),
    "rc-world": ("A", "world", 1),
}

MESSAGES = [
    {"role": "system", "content": "prompt"},
    {"role": "user", "content": "ask"},
    {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "c1",
                "type": "function",
                "function": {"name": "get_note", "arguments": '{"note_id": "n1"}'},
            }
        ],
    },
    {"role": "tool", "tool_call_id": "c1", "content": '{"id": "n1"}'},
    {"role": "assistant", "content": "done"},
]


def test_load_episodes_joins_scores_by_scored_run_id(tmp_path):
    task = _project(tmp_path)
    config = _eval_config(task)
    item = _input(task, 3, ["real", "ep_03"])
    real = _run(task, item, "rc-real", MESSAGES)
    world = _run(task, item, "rc-world", MESSAGES)
    _score(
        config, item, real, "rc-real", {"predicates_pass": 1.0, "collateral_pass": 1.0}
    )
    _score(
        config,
        item,
        world,
        "rc-world",
        {"predicates_pass": 0.0, "collateral_pass": 1.0},
    )

    episodes = load_episodes(
        task,
        config,
        RUN_CONFIGS,
        input_no_for=lambda item: int((item.reference or {})["input_no"]),
        half_for=lambda n: "tuning" if n <= 10 else "sealed",
        transport_codes=TRANSPORT,
    )
    by_system = {e.system: e for e in episodes}
    assert set(by_system) == {"real", "world"}
    assert by_system["real"].scores == {
        "predicates_pass": 1.0,
        "collateral_pass": 1.0,
    }
    assert by_system["world"].scores == {
        "predicates_pass": 0.0,
        "collateral_pass": 1.0,
    }
    assert by_system["real"].configuration == "A"
    assert len(by_system["real"].steps) == 1
    assert by_system["real"].assistant_indices == [2, 4]
    assert by_system["real"].invalid is None


def test_load_episodes_assigns_input_no_and_half(tmp_path):
    task = _project(tmp_path)
    config = _eval_config(task)
    item = _input(task, 14, ["real", "ep_14"])
    run = _run(task, item, "rc-real", MESSAGES)
    _score(
        config, item, run, "rc-real", {"predicates_pass": 1.0, "collateral_pass": 1.0}
    )

    episodes = load_episodes(
        task,
        config,
        RUN_CONFIGS,
        input_no_for=lambda item: int((item.reference or {})["input_no"]),
        half_for=lambda n: "tuning" if n <= 10 else "sealed",
        transport_codes=TRANSPORT,
    )
    assert [(e.input_no, e.half) for e in episodes] == [(14, "sealed")]
    assert episodes[0].pair_key == ("A", 14, 1)


def test_load_episodes_applies_invalid_markers(tmp_path):
    task = _project(tmp_path)
    config = _eval_config(task)
    item = _input(task, 1, ["real"])
    run = _run(task, item, "rc-real", MESSAGES)
    _score(
        config, item, run, "rc-real", {"predicates_pass": 1.0, "collateral_pass": 1.0}
    )

    episodes = load_episodes(
        task,
        config,
        RUN_CONFIGS,
        input_no_for=lambda item: 1,
        half_for=lambda n: "tuning",
        invalid_markers={str(run.id): "judge_failure"},
        transport_codes=TRANSPORT,
    )
    assert episodes[0].invalid == "judge_failure"


def test_load_episodes_ignores_run_configs_it_was_not_given(tmp_path):
    task = _project(tmp_path)
    config = _eval_config(task)
    item = _input(task, 1, ["real"])
    run = _run(task, item, "rc-someone-else", MESSAGES)
    _score(
        config,
        item,
        run,
        "rc-someone-else",
        {"predicates_pass": 1.0, "collateral_pass": 1.0},
    )

    assert (
        load_episodes(
            task,
            config,
            RUN_CONFIGS,
            input_no_for=lambda item: 1,
            half_for=lambda n: "tuning",
            transport_codes=TRANSPORT,
        )
        == []
    )


def test_load_episodes_raises_on_missing_trace(tmp_path):
    task = _project(tmp_path)
    config = _eval_config(task)
    item = _input(task, 1, ["real"])
    run = _run(task, item, "rc-real", MESSAGES)
    run.trace = None
    KilnParentedModel.save_to_file(run)
    _score(
        config, item, run, "rc-real", {"predicates_pass": 1.0, "collateral_pass": 1.0}
    )

    with pytest.raises(ValueError, match="has no trace"):
        load_episodes(
            task,
            config,
            RUN_CONFIGS,
            input_no_for=lambda item: 1,
            half_for=lambda n: "tuning",
            transport_codes=TRANSPORT,
        )


def test_load_episodes_marks_a_malformed_trace(tmp_path):
    task = _project(tmp_path)
    config = _eval_config(task)
    item = _input(task, 1, ["real"])
    dangling = MESSAGES[:3]
    run = _run(task, item, "rc-real", dangling)
    _score(
        config, item, run, "rc-real", {"predicates_pass": 1.0, "collateral_pass": 1.0}
    )

    episodes = load_episodes(
        task,
        config,
        RUN_CONFIGS,
        input_no_for=lambda item: 1,
        half_for=lambda n: "tuning",
        transport_codes=TRANSPORT,
    )
    assert episodes[0].invalid == "malformed_trace"
    assert episodes[0].steps == []


GAP_MESSAGES = [
    {"role": "system", "content": "prompt"},
    {"role": "user", "content": "ask"},
    {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "c1",
                "type": "function",
                "function": {"name": "archive_note", "arguments": '{"note_id": "n1"}'},
            }
        ],
    },
    {
        "role": "tool",
        "tool_call_id": "c1",
        "content": '{"error": {"code": "world_gap", "message": "not implemented", "details": null}}',
        "is_error": True,
    },
    {"role": "assistant", "content": "cannot do that"},
]


def _load(task, config, **kwargs):
    return load_episodes(
        task,
        config,
        RUN_CONFIGS,
        input_no_for=lambda item: int((item.reference or {})["input_no"]),
        half_for=lambda n: "tuning" if n <= 10 else "sealed",
        transport_codes=TRANSPORT,
        **kwargs,
    )


def test_load_episodes_reads_a_world_episode_end_to_end(tmp_path):
    """The whole world-arm path from a stored TaskRun: the episode record is carried onto
    the RecordedEpisode, its final state is readable, and usage comes back as plain JSON.

    A shape change in `WorldEpisode.final_state` would otherwise ship green and present as
    "the world arm reports 0 invalid episodes" — the value everyone expects to see."""
    task = _project(tmp_path)
    config = _eval_config(task)
    item = _input(task, 4, ["world", "ep_04"])
    run = _run(
        task,
        item,
        "rc-world",
        MESSAGES,
        world_episode=_world_episode(
            {
                "episode_id": "ep_abc",
                "step_count": 1,
                "fixture": "notes-v1",
                "changes": [{"table": "notes", "op": "update"}],
                "state_digest": "abc123",
            }
        ),
        usage=Usage(input_tokens=3120, output_tokens=88, cost=0.0041),
    )
    _score(
        config, item, run, "rc-world", {"predicates_pass": 1.0, "collateral_pass": 1.0}
    )

    episode = _load(task, config)[0]
    assert episode.system == "world"
    assert episode.invalid is None
    assert episode.world_episode is not None
    assert episode.world_episode["world_version"] == "notes@1"
    assert episode.world_episode["reset"]["reset_kwargs"] == {"fixture": "notes-v1"}
    assert final_state(episode)["state_digest"] == "abc123"
    assert changes(episode) == [{"table": "notes", "op": "update"}]
    assert settle_error(episode) is None
    assert episode.usage is not None
    assert episode.usage["input_tokens"] == 3120 and episode.usage["cost"] == 0.0041


def test_load_episodes_marks_a_world_gap_invalid(tmp_path):
    task = _project(tmp_path)
    config = _eval_config(task)
    item = _input(task, 4, ["world"])
    run = _run(
        task,
        item,
        "rc-world",
        GAP_MESSAGES,
        world_episode=_world_episode({"episode_id": "ep_abc", "step_count": 1}),
    )
    _score(
        config, item, run, "rc-world", {"predicates_pass": 0.0, "collateral_pass": 1.0}
    )

    episode = _load(task, config)[0]
    assert episode.invalid == "world_gap"
    gap = world_gap(episode)
    assert gap is not None and gap.tool_name == "archive_note"


def test_load_episodes_marks_a_settle_error_invalid(tmp_path):
    task = _project(tmp_path)
    config = _eval_config(task)
    item = _input(task, 4, ["world"])
    run = _run(
        task,
        item,
        "rc-world",
        MESSAGES,
        world_episode=_world_episode(
            {
                "episode_id": "ep_abc",
                "step_count": 1,
                "settle_error": {"tool": "controller_changes", "code": "db_error"},
            }
        ),
    )
    _score(
        config, item, run, "rc-world", {"predicates_pass": 1.0, "collateral_pass": 1.0}
    )

    episode = _load(task, config)[0]
    assert episode.invalid == "settle_error"
    assert changes(episode) is None
    assert settle_error(episode) == {"tool": "controller_changes", "code": "db_error"}


def test_load_episodes_raises_on_a_dangling_scored_run(tmp_path):
    """A silent drop would be laundered into a `reset_anomaly` count by `metrics.cells`."""
    task = _project(tmp_path)
    config = _eval_config(task)
    item = _input(task, 1, ["real"])
    run = _run(task, item, "rc-real", MESSAGES)
    _score(
        config, item, run, "rc-real", {"predicates_pass": 1.0, "collateral_pass": 1.0}
    )
    run.path.unlink()

    with pytest.raises(ValueError, match="which is missing"):
        _load(task, config)


def test_load_episodes_raises_on_a_missing_eval_input(tmp_path):
    task = _project(tmp_path)
    config = _eval_config(task)
    item = _input(task, 1, ["real"])
    run = _run(task, item, "rc-real", MESSAGES)
    _score(
        config, item, run, "rc-real", {"predicates_pass": 1.0, "collateral_pass": 1.0}
    )
    item.path.unlink()

    with pytest.raises(ValueError, match="which is missing"):
        _load(task, config)


def test_extract_steps_duplicate_call_id_raises():
    """Two answers to one call: which the model saw is unknowable."""
    with pytest.raises(ValueError, match="answered twice"):
        extract_steps(
            trace(
                assistant_message(tool_call("c1", "get_note", note_id="n1")),
                tool_message("c1", {"id": "n1"}),
                tool_message("c1", {"id": "n2"}),
            )
        )
    with pytest.raises(ValueError, match="requested twice"):
        extract_steps(
            trace(
                assistant_message(tool_call("c1", "get_note", note_id="n1")),
                tool_message("c1", {"id": "n1"}),
                assistant_message(tool_call("c1", "get_note", note_id="n1")),
            )
        )


def test_content_text_reads_parts_and_does_not_iterate_a_mapping():
    assert content_text("plain") == "plain"
    assert (
        content_text([{"type": "text", "text": "a"}, {"type": "text", "text": "b"}])
        == "ab"
    )
    assert content_text(None) == ""
    # a Mapping is str()-ed, not iterated: iterating one yields its keys
    assert content_text({"text": "x"}) == "{'text': 'x'}"


def test_invalid_reason_never_reports_a_world_reason_on_the_real_lane():
    """A world-side code configured as a transport code must not cross lanes, or the two
    lanes' counts stop being comparable."""
    recorded = episode(
        assistant_message(tool_call("c1", "get_note")),
        tool_message("c1", error_result("world_gap")),
        system="real",
    )
    assert (
        invalid_reason(
            system="real",
            steps=recorded.steps,
            world_episode=None,
            marker=None,
            malformed=False,
            transport_codes=frozenset({"world_gap"}),
        )
        == "upstream_error"
    )
