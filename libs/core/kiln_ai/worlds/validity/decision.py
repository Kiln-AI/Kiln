"""Decision replay: does the model make the same choice when the world answered instead?

Replay (`replay.py`) measures whether the world's results match. This measures whether the
differences that remain *matter*: for one assistant turn of a recorded episode, rebuild the
conversation up to that point with the world's replayed results substituted, ask the same
run config for its next move, and compare the whole tool-call batch it asks for against the
batch the recording made. The control arm does the same with the recorded results, so the
figure is read as a difference against the model's own turn-to-turn noise rather than as an
absolute.

Two mechanics make it safe:

- The adapter is stopped with `AdapterConfig(return_on_tool_call=True)`, so it returns the
  model's whole batch without executing any of it. Stopping inside a tool call would be a
  race — a turn's calls are launched together — and would surface as a wrapped error with a
  partial trace.
- A `RecordingSessionManager` is installed as the guard. The run config lists world tool
  ids, which resolve only under an active episode context, so the context has to exist; if
  anything ever calls through it, `StopReplay` propagates and the decision is recorded as an
  error rather than quietly executing against a world.

Temperature is 0 on both arms: a deliberate deviation from the traces' generating
configuration, so the arms differ by the substitution and not by sampling.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, get_args

from pydantic import JsonValue

from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig, SkillsDict
from kiln_ai.datamodel.datamodel_enums import InputType
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.datamodel.task import Task, TaskRunConfig
from kiln_ai.datamodel.world import (
    OpenEnvTool,
    WorldEpisode,
    WorldReset,
)
from kiln_ai.datamodel.world import (
    World as KilnWorld,
)
from kiln_ai.run_context import EpisodeContext, reset_episode, set_episode
from kiln_ai.tools.world_tool import WORLD_FAILURE_CODES, render_tool_result
from kiln_ai.utils.open_ai_types import ChatCompletionMessageParam
from kiln_ai.worlds.session_manager import ToolCallOutcome

from .cost import BudgetExceeded, CostMeter
from .replay import ReplayedEpisode
from .scrub import ScrubRules, as_json, normalize_arguments
from .traces import RecordedEpisode, error_code, user_message

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

TASK_RESPONSE_TOOL = "task_response"
"""The adapter's structured-output pseudo-tool. Never a decision; the task is unstructured."""

Arm = Literal["world", "control"]
PrefixKind = Literal["divergent", "control"]

ARMS: frozenset[str] = frozenset(get_args(Arm))
PREFIXES: frozenset[str] = frozenset(get_args(PrefixKind))


class StopReplay(RuntimeError):
    """Something tried to run a tool during decision replay. A decision that reaches the
    session manager is a harness bug, not a data point."""


@dataclass
class RecordingSessionManager:
    """Satisfies `WorldSessionManager` for the tool registry's sake only.

    Every method except `call_control_tool` records the attempt and raises `StopReplay`;
    nothing is ever meant to reach it. `call_control_tool` is a pass-through no-op so a
    settle attempt cannot turn a replay into a failure."""

    calls: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)

    async def call_tool(
        self, episode: WorldEpisode, tool_name: str, arguments: dict[str, Any]
    ) -> ToolCallOutcome:
        self.calls.append(("call_tool", tool_name, dict(arguments)))
        raise StopReplay(f"decision replay called tool {tool_name}")

    async def call_control_tool(
        self, episode: WorldEpisode, tool_name: str, arguments: dict[str, Any]
    ) -> ToolCallOutcome:
        self.calls.append(("call_control_tool", tool_name, dict(arguments)))
        return ToolCallOutcome(
            result=None,
            error=f"unknown tool: {tool_name}",
            reward=None,
            done=False,
            error_code="unknown_tool",
            error_details=None,
        )

    async def world_version(
        self, world: KilnWorld, reset_kwargs: dict[str, JsonValue]
    ) -> str:
        self.calls.append(("world_version", "", dict(reset_kwargs)))
        raise StopReplay("decision replay asked for a world version")

    async def list_tools(self, world: KilnWorld) -> list[OpenEnvTool]:
        self.calls.append(("list_tools", "", {}))
        raise StopReplay("decision replay listed tools")

    async def start_episode(
        self, world: KilnWorld, reset_kwargs: dict[str, JsonValue]
    ) -> WorldEpisode:
        self.calls.append(("start_episode", "", dict(reset_kwargs)))
        raise StopReplay("decision replay started an episode")

    async def end_episode(self, episode: WorldEpisode) -> WorldEpisode:
        self.calls.append(("end_episode", "", {}))
        raise StopReplay("decision replay ended an episode")

    async def release(self, episode: WorldEpisode) -> None:
        return None

    async def shutdown(self) -> None:
        return None


@dataclass(frozen=True)
class Call:
    tool_name: str
    arguments: dict[str, JsonValue]

    def key(self) -> str:
        return json.dumps(
            [self.tool_name, self.arguments], sort_keys=True, ensure_ascii=False
        )


@dataclass(frozen=True)
class DecisionRecord:
    run_id: str
    configuration: str
    decision_index: int
    arm: Arm
    prefix: PrefixKind
    recorded: list[Call]
    replayed: list[Call]
    name_match: bool
    args_match: bool
    agree: bool
    usage: dict[str, JsonValue] | None = None
    error: str | None = None


@dataclass(frozen=True)
class DecisionSelection:
    divergent: list[tuple[str, int]]
    control: list[tuple[str, int]]

    def prefix_of(self, run_id: str, decision_index: int) -> PrefixKind:
        """How this selection classifies one decision. A record read back from an earlier
        run keeps the prefix it was written with, so a driver comparing partitions across
        selections asks here rather than trusting the file."""
        return (
            "divergent"
            if (run_id, decision_index) in set(self.divergent)
            else "control"
        )


def divergent_prefix(
    episode: RecordedEpisode, replayed: ReplayedEpisode, decision_index: int
) -> bool:
    """True when a substituted result before this decision differed from the recording."""
    if decision_index >= len(episode.assistant_indices):
        return False
    boundary = episode.assistant_indices[decision_index]
    return any(
        step.message_index < boundary and step.index in replayed.divergent_steps
        for step in episode.steps
    )


def select_decisions(
    episodes: Sequence[RecordedEpisode],
    replayed: Mapping[str, ReplayedEpisode],
    *,
    control_sample: int = 300,
    seed: int = 0,
) -> DecisionSelection:
    """Every divergent-prefix decision, plus a seeded sample of control-prefix decisions.

    The conditional figure needs every divergence it can get; the unconditional one only
    needs a fixed budget, so it is sampled."""
    divergent: list[tuple[str, int]] = []
    control: list[tuple[str, int]] = []
    for episode in episodes:
        one = replayed.get(episode.run_id)
        if one is None:
            continue
        for index in range(len(episode.assistant_indices)):
            key = (episode.run_id, index)
            if divergent_prefix(episode, one, index):
                divergent.append(key)
            else:
                control.append(key)
    if len(control) > control_sample:
        control = sorted(random.Random(seed).sample(control, control_sample))
    return DecisionSelection(divergent=divergent, control=control)


def build_prefix(
    episode: RecordedEpisode,
    decision_index: int,
    results: Sequence[JsonValue] | None,
    *,
    raw_steps: frozenset[int] = frozenset(),
) -> tuple[list[ChatCompletionMessageParam] | None, InputType]:
    """The conversation as the model would have seen it just before decision `j`.

    `results` is the world's replayed result per step, or None for the control arm, which
    keeps the recorded text throughout. `raw_steps` names the steps the world was never
    asked to answer (unserved, transport-excluded); they keep the recorded text too. They
    are passed explicitly rather than inferred from `results[i] is None`, because a world
    result that is genuinely null is not the same thing as a step that was skipped.

    Decision 0 seeds the prior trace with the recorded system message, so no arm rebuilds
    the prompt from a template; later decisions feed the previous turn's tool results as the
    formatter's tool-result input, which is the teacher-forcing seam."""
    trace = episode.trace
    if not trace or decision_index >= len(episode.assistant_indices):
        return None, ""
    if decision_index == 0:
        return [dict(trace[0])], user_message(trace)  # type: ignore[list-item]

    previous = episode.assistant_indices[decision_index - 1]
    steps_by_call = {step.call_id: step for step in episode.steps}

    prior: list[ChatCompletionMessageParam] = []
    for message in trace[: previous + 1]:
        if isinstance(message, dict) and message.get("role") == "tool":
            prior.append(
                _substituted(message, steps_by_call, results, raw_steps)  # type: ignore[arg-type]
            )
        else:
            prior.append(dict(message))  # type: ignore[arg-type]

    call_ids = _call_ids(trace[previous])
    tool_input: list[dict[str, Any]] = []
    for call_id in call_ids:
        answer = _answer_for(trace, call_id)
        if answer is None:
            continue
        substituted = _substituted(answer, steps_by_call, results, raw_steps)
        tool_input.append(
            {
                "tool_call_id": call_id,
                "content": substituted.get("content", ""),
                "is_error": substituted.get("is_error"),
                "error_message": substituted.get("error_message"),
            }
        )
    return prior, tool_input


def _substituted(
    message: Mapping[str, Any],
    steps_by_call: Mapping[str, Any],
    results: Sequence[JsonValue] | None,
    raw_steps: frozenset[int],
) -> dict[str, Any]:
    """One tool message with the world's result rendered in place of the recorded text."""
    out = dict(message)
    call_id = out.get("tool_call_id")
    step = steps_by_call.get(call_id) if isinstance(call_id, str) else None
    if results is None or step is None or step.index in raw_steps:
        return out
    if step.index >= len(results):
        return out
    result = results[step.index]
    out["content"] = render_tool_result(result)
    code = error_code(result)
    if code is not None and code in WORLD_FAILURE_CODES:
        # The world's own failure, which the tool proxy shows the model as an error. A
        # coded product error is an ordinary result on both arms.
        out["is_error"] = True
        envelope = result.get("error") if isinstance(result, dict) else None
        out["error_message"] = (
            envelope.get("message") if isinstance(envelope, dict) else None
        )
    else:
        out["is_error"] = None
        out["error_message"] = None
    return out


def _call_ids(message: Any) -> list[str]:
    if not isinstance(message, Mapping):
        return []
    return [
        call["id"]
        for call in message.get("tool_calls") or []
        if isinstance(call, Mapping) and isinstance(call.get("id"), str)
    ]


def _answer_for(
    trace: Sequence[ChatCompletionMessageParam], call_id: str
) -> Mapping[str, Any] | None:
    for message in trace:
        if (
            isinstance(message, Mapping)
            and message.get("role") == "tool"
            and message.get("tool_call_id") == call_id
        ):
            return message
    return None


def calls_of(message: Any, rules: ScrubRules) -> list[Call]:
    """The tool-call batch of one assistant message, normalized for comparison."""
    calls: list[Call] = []
    for raw in _tool_calls(message):
        function = raw.get("function") or {}
        name = str(function.get("name", ""))
        if name == TASK_RESPONSE_TOOL:
            continue
        arguments = function.get("arguments")
        parsed: Any
        if isinstance(arguments, Mapping):
            parsed = dict(arguments)
        else:
            try:
                parsed = json.loads(arguments) if isinstance(arguments, str) else {}
            except (TypeError, ValueError):
                parsed = {}
        if not isinstance(parsed, dict):
            parsed = {}
        calls.append(Call(name, normalize_arguments(parsed, rules)))
    return calls


def _tool_calls(message: Any) -> list[Mapping[str, Any]]:
    if not isinstance(message, Mapping):
        return []
    return [c for c in message.get("tool_calls") or [] if isinstance(c, Mapping)]


def last_assistant(trace: Sequence[Any] | None) -> Any:
    for message in reversed(list(trace or [])):
        if isinstance(message, Mapping) and message.get("role") == "assistant":
            return message
    return None


async def replay_decision(
    task: Task,
    run_config: TaskRunConfig,
    world: KilnWorld,
    tools: dict[str, OpenEnvTool],
    skills: SkillsDict,
    episode: RecordedEpisode,
    decision_index: int,
    arm: Arm,
    replayed: ReplayedEpisode | None,
    rules: ScrubRules,
    *,
    prefix: PrefixKind = "control",
    reset_kwargs: Mapping[str, JsonValue] = {},
    world_version: str = "decision-replay",
) -> DecisionRecord:
    """One decision, one arm. Never raises: an adapter failure is recorded as an error and
    the pair it belongs to is dropped by the statistic."""
    results = (
        list(replayed.results) if (arm == "world" and replayed is not None) else None
    )
    raw_steps = replayed.skipped_steps if replayed is not None else frozenset()
    prior_trace, model_input = build_prefix(
        episode, decision_index, results, raw_steps=raw_steps
    )
    # `build_prefix` already tolerates an index past the end; so must this, or the
    # "never raises" contract holds only for the first of the two reads.
    recorded = (
        calls_of(episode.trace[episode.assistant_indices[decision_index]], rules)
        if decision_index < len(episode.assistant_indices)
        else []
    )

    token = set_episode(
        EpisodeContext(
            episode=WorldEpisode(
                reset=WorldReset(
                    world_id=str(world.id), reset_kwargs=dict(reset_kwargs)
                ),
                episode_id="decision",
                world_version=world_version,
            ),
            world=world,
            session_manager=RecordingSessionManager(),
            tools=tools,
        )
    )
    try:
        adapter = adapter_for_task(
            task,
            run_config.run_config_properties,
            AdapterConfig(
                allow_saving=False,
                skills=skills,
                return_on_tool_call=True,
                task_run_config_id=str(run_config.id),
            ),
        )
        run = await adapter.invoke(model_input, prior_trace=prior_trace)
    except Exception as error:  # the record carries the failure; the pair is dropped
        return DecisionRecord(
            run_id=episode.run_id,
            configuration=episode.configuration,
            decision_index=decision_index,
            arm=arm,
            prefix=prefix,
            recorded=recorded,
            replayed=[],
            name_match=False,
            args_match=False,
            agree=False,
            usage=None,
            error=_error_name(error),
        )
    finally:
        reset_episode(token)

    replayed_calls = calls_of(last_assistant(run.trace), rules)
    name_match = sorted(c.tool_name for c in recorded) == sorted(
        c.tool_name for c in replayed_calls
    )
    args_match = sorted(c.key() for c in recorded) == sorted(
        c.key() for c in replayed_calls
    )
    return DecisionRecord(
        run_id=episode.run_id,
        configuration=episode.configuration,
        decision_index=decision_index,
        arm=arm,
        prefix=prefix,
        recorded=recorded,
        replayed=replayed_calls,
        name_match=name_match,
        args_match=args_match,
        agree=name_match and args_match,
        usage=run.usage.model_dump(mode="json") if run.usage else None,
        error=None,
    )


def agent_properties(run_config: TaskRunConfig) -> KilnAgentRunConfigProperties:
    """Decision replay drives the model directly, so it needs the agent run config's model
    and temperature; an MCP config carries neither."""
    properties = run_config.run_config_properties
    if not isinstance(properties, KilnAgentRunConfigProperties):
        raise ValueError(
            f"decision replay needs a kiln_agent run config; {run_config.id} is "
            f"{type(properties).__name__}"
        )
    return properties


def _error_name(error: BaseException) -> str:
    """`StopReplay` is what a harness bug looks like, and it arrives wrapped."""
    seen: BaseException | None = error
    while seen is not None:
        if isinstance(seen, StopReplay):
            return "StopReplay"
        original = getattr(seen, "original", None)
        if isinstance(original, BaseException):
            seen = original
            continue
        seen = seen.__cause__
    return type(error).__name__


async def replay_all_decisions(
    task: Task,
    run_config_for: Callable[[RecordedEpisode], TaskRunConfig],
    world: KilnWorld,
    tools: dict[str, OpenEnvTool],
    skills: SkillsDict,
    episodes: Sequence[RecordedEpisode],
    replayed: Mapping[str, ReplayedEpisode],
    selection: DecisionSelection,
    rules: ScrubRules,
    *,
    arms: Sequence[Arm] = ("world", "control"),
    concurrency: int = 8,
    meter: CostMeter | None = None,
    out: Path,
    reset_kwargs: Mapping[str, JsonValue] = {},
    world_version: str = "decision-replay",
) -> list[DecisionRecord]:
    """Every selected decision on every arm, appended to `out` as they complete.

    Resumable: a `(run_id, decision_index, arm)` already in the file is not rerun, and the
    records already there come back alongside the new ones, so the statistic always sees
    the whole set. Stops cleanly on `BudgetExceeded` — the decisions in flight finish and
    are written."""
    by_run = {episode.run_id: episode for episode in episodes}
    work: list[tuple[str, int, Arm, PrefixKind]] = []
    seen: set[tuple[str, int, Arm]] = set()
    for prefix, keys in (
        ("divergent", selection.divergent),
        ("control", selection.control),
    ):
        for run_id, index in keys:
            for arm in arms:
                if (run_id, index, arm) in seen:
                    # An overlapping selection would otherwise pay for the same decision
                    # twice and write it twice.
                    continue
                seen.add((run_id, index, arm))
                work.append((run_id, index, arm, prefix))  # type: ignore[arg-type]

    for run_id in {item[0] for item in work}:
        episode = by_run.get(run_id)
        if episode is None:
            continue
        temperature = agent_properties(run_config_for(episode)).temperature
        if temperature != 0:
            raise ValueError(
                "decision replay requires a temperature-0 run config; "
                f"{episode.run_config_id} is at {temperature}"
            )

    resumed = load_records(out)
    wanted = {(run_id, index) for run_id, index, _, _ in work}
    # A record for a decision the current selection no longer holds is not this run's data:
    # the control arm is a seeded sample, so a resume after any selection change would
    # otherwise contaminate the statistic with pairs outside it.
    resumed = [r for r in resumed if (r.run_id, r.decision_index) in wanted]
    done = _already_written(resumed)
    out.parent.mkdir(parents=True, exist_ok=True)
    _terminate_last_line(out)
    records: list[DecisionRecord] = []
    semaphore = asyncio.Semaphore(concurrency)
    lock = asyncio.Lock()
    stopped = False

    with out.open("a", encoding="utf-8") as handle:

        async def one(run_id: str, index: int, arm: Arm, prefix: PrefixKind) -> None:
            nonlocal stopped
            episode = by_run.get(run_id)
            if episode is None or (run_id, index, arm) in done:
                return
            done.add((run_id, index, arm))
            async with semaphore:
                if stopped:
                    return
                run_config = run_config_for(episode)
                record = await replay_decision(
                    task,
                    run_config,
                    world,
                    tools,
                    skills,
                    episode,
                    index,
                    arm,
                    replayed.get(run_id),
                    rules,
                    prefix=prefix,
                    reset_kwargs=reset_kwargs,
                    world_version=world_version,
                )
            async with lock:
                records.append(record)
                handle.write(
                    json.dumps(
                        _line(record, agent_properties(run_config).temperature),
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                handle.flush()
                if meter is not None and record.usage:
                    try:
                        meter.add(agent_properties(run_config).model_name, record.usage)
                    except BudgetExceeded as exceeded:
                        logger.warning(
                            "decision replay stopped on budget: %s", exceeded
                        )
                        stopped = True

        # return_exceptions so one task's failure cannot close the output file while the
        # others are still writing to it.
        outcomes = await asyncio.gather(
            *(one(*item) for item in work), return_exceptions=True
        )
    for outcome in outcomes:
        if isinstance(outcome, BaseException):
            raise outcome

    # What the file holds, not only what this invocation produced.
    return resumed + records


def _line(record: DecisionRecord, temperature: float) -> dict[str, JsonValue]:
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": record.run_id,
        "configuration": record.configuration,
        "decision_index": record.decision_index,
        "arm": record.arm,
        "prefix": record.prefix,
        "recorded": [
            {"tool_name": c.tool_name, "arguments": as_json(c.arguments)}
            for c in record.recorded
        ],
        "replayed": [
            {"tool_name": c.tool_name, "arguments": as_json(c.arguments)}
            for c in record.replayed
        ],
        "name_match": record.name_match,
        "args_match": record.args_match,
        "agree": record.agree,
        "temperature": temperature,
        "usage": as_json(record.usage),
        "error": record.error,
    }


def load_records(out: Path) -> list[DecisionRecord]:
    """The decisions already in `out`, so a resumed step returns the whole set.

    A resumed run that returned only its new records would hand the statistic a partial,
    non-random subset of the decisions — and a world arm whose control twin was written
    before the crash is dropped by the pairing, which can turn a measurable gate into
    `not_measurable`. Lines that do not parse are skipped rather than fatal: the file is
    append-only and a crash can truncate the last one."""
    if not out.exists():
        return []
    records: list[DecisionRecord] = []
    for line in out.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except ValueError:
            continue
        if not isinstance(raw, dict):
            continue
        run_id = raw.get("run_id")
        index = raw.get("decision_index")
        arm = raw.get("arm")
        prefix = raw.get("prefix", "control")
        if not (
            isinstance(run_id, str)
            and isinstance(index, int)
            and arm in ARMS
            and prefix in PREFIXES
        ):
            continue
        records.append(
            DecisionRecord(
                run_id=run_id,
                configuration=str(raw.get("configuration", "")),
                decision_index=index,
                arm=arm,  # type: ignore[arg-type]
                prefix=prefix,  # type: ignore[arg-type]
                recorded=_calls(raw.get("recorded")),
                replayed=_calls(raw.get("replayed")),
                name_match=bool(raw.get("name_match")),
                args_match=bool(raw.get("args_match")),
                agree=bool(raw.get("agree")),
                usage=raw.get("usage") if isinstance(raw.get("usage"), dict) else None,
                error=raw.get("error") if isinstance(raw.get("error"), str) else None,
            )
        )
    return records


def _calls(raw: Any) -> list[Call]:
    if not isinstance(raw, list):
        return []
    return [
        Call(
            tool_name=str(item.get("tool_name", "")),
            arguments=item.get("arguments")
            if isinstance(item.get("arguments"), dict)
            else {},
        )
        for item in raw
        if isinstance(item, Mapping)
    ]


def _already_written(records: Sequence[DecisionRecord]) -> set[tuple[str, int, str]]:
    return {(r.run_id, r.decision_index, r.arm) for r in records}


def _terminate_last_line(out: Path) -> None:
    """Close off a line a crash left unterminated.

    The file is opened for append. A truncated last line has no newline of its own, so the
    next record would be concatenated onto it and both would be unreadable - the one shape
    a real truncation produces, and the one a test writing garbage plus a newline cannot."""
    if not out.exists() or out.stat().st_size == 0:
        return
    with out.open("rb") as handle:
        handle.seek(-1, 2)
        if handle.read(1) == b"\n":
            return
    with out.open("a", encoding="utf-8") as handle:
        handle.write("\n")
