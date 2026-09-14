"""Recorded episodes: reading what a run of the eval left in a Kiln project, and turning
each trace into the ordered list of tool calls the replay and decision steps work from.

A trace is `TaskRun.trace`. A model turn that asked for tools is one assistant message
carrying `tool_calls`, followed by one `role: "tool"` message per call, appended in
`tool_calls` order (the adapter runs a turn's calls concurrently and joins them in order).
`extract_steps` walks that structure and pairs the two; a `tool_call_id` with no answer, or
an answer with no call, is a malformed trace and the episode is excluded.

Invalidity is symmetric. The world arm is invalid on a world gap or a settle error, the
real arm on a transport-coded error reaching the agent, and either arm on a provider error,
a judge failure, a reset anomaly or a malformed trace. The first three of those are not
visible in the trace, so the driver passes them in as markers keyed by run id; this module
holds no knowledge of where the driver keeps its files.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, get_args

from pydantic import JsonValue

from kiln_ai.datamodel.eval import EvalConfig, EvalInput
from kiln_ai.datamodel.task import Task
from kiln_ai.utils.open_ai_types import ChatCompletionMessageParam

System = Literal["real", "world"]
Half = Literal["tuning", "sealed"]
ConfigKey = tuple[str, System, int]
"""(configuration, system, repeat): what one TaskRunConfig stands for."""

PairKey = tuple[str, int, int]
"""(configuration, input_no, repeat): the unit the two systems are paired on."""

InvalidReason = Literal[
    "world_gap",
    "settle_error",
    "upstream_error",
    "rate_limited",
    "reset_anomaly",
    "judge_failure",
    "provider_error",
    "malformed_trace",
]

INVALID_REASONS: frozenset[str] = frozenset(get_args(InvalidReason))
"""Every reason the taxonomy admits. Exported for a driver validating the markers it writes
into `invalid.jsonl` before handing them to `load_episodes`, which takes them on trust."""

MARKER_REASONS: frozenset[str] = frozenset(
    {"reset_anomaly", "judge_failure", "provider_error"}
)
"""The reasons that are invisible in a trace and travel from the driver as markers. The
complement — everything `invalid_reason` derives itself — is what a driver must not send."""

REAL_LANE_REASONS: frozenset[str] = frozenset({"upstream_error", "rate_limited"})
"""The reasons a transport-coded step may report. A world-side code configured as a
transport code is bucketed here rather than crossing lanes."""


@dataclass(frozen=True)
class ToolStep:
    index: int
    message_index: int
    call_id: str
    tool_name: str
    arguments: dict[str, JsonValue]
    raw_content: str
    result: JsonValue
    is_error: bool
    error_code: str | None
    parallel: bool


@dataclass(frozen=True)
class RecordedEpisode:
    run_id: str
    eval_input_id: str
    run_config_id: str
    configuration: str
    system: System
    repeat: int
    input_no: int
    half: Half
    trace: list[ChatCompletionMessageParam]
    steps: list[ToolStep]
    assistant_indices: list[int]
    final_message: str
    world_episode: dict[str, JsonValue] | None = None
    scores: dict[str, float] | None = None
    skipped_reason: str | None = None
    invalid: InvalidReason | None = None
    usage: dict[str, JsonValue] | None = None

    @property
    def pair_key(self) -> PairKey:
        return (self.configuration, self.input_no, self.repeat)


@dataclass
class _Message:
    """One trace message, normalized enough to read without caring how it was stored."""

    index: int
    role: str
    raw: Mapping[str, Any]
    tool_calls: list[Mapping[str, Any]] = field(default_factory=list)


def message_text(message: Mapping[str, Any]) -> str:
    """A message's content as text, whether it was stored as a string or as content parts."""
    content = message.get("content")
    return content_text(content)


def content_text(content: Any) -> str:
    """A message's content as text: a string, or the text of its content parts.

    A Mapping is `str()`-ed rather than iterated: iterating one yields its keys, which
    would silently render every such message as the empty string."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, Iterable) and not isinstance(content, Mapping):
        parts = [
            str(part.get("text", ""))
            for part in content
            if isinstance(part, Mapping) and part.get("type", "text") == "text"
        ]
        return "".join(parts)
    return str(content)


def _messages(trace: Sequence[ChatCompletionMessageParam]) -> list[_Message]:
    messages: list[_Message] = []
    for index, raw in enumerate(trace):
        if not isinstance(raw, Mapping):
            raise ValueError(f"trace message {index} is not an object")
        calls = raw.get("tool_calls") or []
        if not isinstance(calls, (list, tuple)):
            # Every other structural defect raises; this one degrading to zero steps would
            # silently make an episode look like a pure-conversation trace.
            raise ValueError(f"trace message {index} has a non-list tool_calls")
        messages.append(
            _Message(
                index=index,
                role=str(raw.get("role", "")),
                raw=raw,
                tool_calls=[c for c in calls if isinstance(c, Mapping)],
            )
        )
    return messages


def extract_steps(trace: Sequence[ChatCompletionMessageParam]) -> list[ToolStep]:
    """Every tool call of the trace, in the order the model asked for them.

    Raises ValueError when a `tool_call_id` has no tool message or a tool message answers
    no call: such a trace cannot be replayed and the episode is invalid."""
    messages = _messages(trace)
    answers: dict[str, Mapping[str, Any]] = {}
    for message in messages:
        if message.role != "tool":
            continue
        call_id = message.raw.get("tool_call_id")
        if not isinstance(call_id, str) or not call_id:
            raise ValueError(f"tool message {message.index} has no tool_call_id")
        if call_id in answers:
            # Two answers to one call: which one the model saw is unknowable, so the
            # trace cannot be replayed or teacher-forced.
            raise ValueError(
                f"tool_call_id {call_id} is answered twice (message {message.index})"
            )
        answers[call_id] = message.raw

    answered: set[str] = set()
    steps: list[ToolStep] = []
    for message in messages:
        if message.role != "assistant" or not message.tool_calls:
            continue
        parallel = len(message.tool_calls) > 1
        for call in message.tool_calls:
            call_id = call.get("id")
            if not isinstance(call_id, str) or not call_id:
                raise ValueError(
                    f"assistant message {message.index} has a call with no id"
                )
            if call_id in answered:
                raise ValueError(
                    f"tool_call_id {call_id} is requested twice (message {message.index})"
                )
            answer = answers.get(call_id)
            if answer is None:
                raise ValueError(
                    f"tool call {call_id} in message {message.index} has no tool message"
                )
            answered.add(call_id)
            function = call.get("function") or {}
            name = str(function.get("name", ""))
            raw_content = content_text(answer.get("content"))
            result = _parse(raw_content)
            steps.append(
                ToolStep(
                    index=len(steps),
                    message_index=message.index,
                    call_id=call_id,
                    tool_name=name,
                    arguments=_parse_arguments(function.get("arguments")),
                    raw_content=raw_content,
                    result=result,
                    is_error=bool(answer.get("is_error")),
                    error_code=error_code(result),
                    parallel=parallel,
                )
            )
    orphans = sorted(set(answers) - answered)
    if orphans:
        raise ValueError(
            f"tool messages answer calls that are not in the trace: {orphans}"
        )
    return steps


def _parse(raw_content: str) -> JsonValue:
    try:
        return json.loads(raw_content)
    except (TypeError, ValueError):
        return raw_content


def _parse_arguments(raw: Any) -> dict[str, JsonValue]:
    """A tool call's arguments. A model that emitted arguments that are not a JSON object
    made a malformed *call*, not a malformed trace: the recorded answer is the error the
    system returned, the episode is still scored, and the replay sends no arguments."""
    if isinstance(raw, Mapping):
        return dict(raw)
    if not isinstance(raw, str):
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def error_code(result: JsonValue) -> str | None:
    """The code of an error envelope (`{"error": {"code", "message", "details"}}`), which
    both systems answer with, or None for an ordinary result."""
    if not isinstance(result, dict):
        return None
    envelope = result.get("error")
    if not isinstance(envelope, dict):
        return None
    code = envelope.get("code")
    return code if isinstance(code, str) else None


def step_count(trace: Sequence[ChatCompletionMessageParam]) -> int:
    """How many tool calls the trace contains. Reported beside the scores, never scored:
    output-score types admit no raw count.

    Counts assistant messages only, so this and `len(extract_steps(trace))` cannot drift
    apart on a trace that carries `tool_calls` on some other role."""
    return sum(
        len(message.tool_calls)
        for message in _messages(trace)
        if message.role == "assistant"
    )


def assistant_indices(trace: Sequence[ChatCompletionMessageParam]) -> list[int]:
    return [m.index for m in _messages(trace) if m.role == "assistant"]


def system_message(trace: Sequence[ChatCompletionMessageParam]) -> str:
    for message in _messages(trace):
        if message.role in ("system", "developer"):
            return message_text(message.raw)
    return ""


def user_message(trace: Sequence[ChatCompletionMessageParam]) -> str:
    for message in _messages(trace):
        if message.role == "user":
            return message_text(message.raw)
    return ""


def final_state(episode: "RecordedEpisode") -> dict[str, JsonValue]:
    """The world episode's `final_state`, or {} when the episode had none."""
    if not episode.world_episode:
        return {}
    state = episode.world_episode.get("final_state")
    return state if isinstance(state, dict) else {}


def settle_error(episode: "RecordedEpisode") -> JsonValue | None:
    """`final_state.settle_error` when the key is present with a value.

    Presence is the rule, not shape: the settle step writes a `{tool, code, message}`
    object today, and an episode that recorded something else there still failed to
    settle."""
    state = final_state(episode)
    if "settle_error" not in state:
        return None
    return state["settle_error"]


def changes(episode: "RecordedEpisode") -> list[JsonValue] | None:
    """`final_state.changes` when it is a list, and None when the key is absent *or null*.

    Both are "no changes were recorded". A settle call that succeeded with a null result
    writes `changes: null`, which reads as present; a caller that asked for a length would
    get a TypeError instead of the missing-key it was ready for.

    Because the two collapse here, a caller that has to tell them apart — the judge, which
    must fail loudly when a world episode's `final_state` lacks `changes` — reads
    `final_state(episode)` and tests membership itself."""
    value = final_state(episode).get("changes")
    return value if isinstance(value, list) else None


def world_gap(episode: "RecordedEpisode") -> ToolStep | None:
    for step in episode.steps:
        if step.error_code == "world_gap":
            return step
    return None


def invalid_reason(
    *,
    system: System,
    steps: Sequence[ToolStep],
    world_episode: Mapping[str, JsonValue] | None,
    marker: InvalidReason | None,
    malformed: bool,
    transport_codes: frozenset[str],
) -> InvalidReason | None:
    """The symmetric invalidity rule. Returns None when the episode counts.

    Order matters: a trace we could not parse says nothing about the rest, and a marker the
    driver saw (a reset anomaly, a judge failure, a provider error) happened outside the
    trace, so both outrank anything read from the steps."""
    if malformed:
        return "malformed_trace"
    if marker is not None:
        return marker
    if system == "world":
        for step in steps:
            if step.error_code == "world_gap":
                return "world_gap"
        state = (world_episode or {}).get("final_state")
        if isinstance(state, dict) and state.get("settle_error") is not None:
            return "settle_error"
        return None
    for step in steps:
        if step.error_code is not None and step.error_code in transport_codes:
            # A transport code names a real-lane reason. Anything else configured there —
            # a world-side code, most dangerously — is bucketed as `upstream_error` rather
            # than reported as a world-arm reason on the real lane, which would make the
            # two lanes' counts incomparable.
            return (
                step.error_code  # type: ignore[return-value]
                if step.error_code in REAL_LANE_REASONS
                else "upstream_error"
            )
    return None


def load_episodes(
    task: Task,
    eval_config: EvalConfig,
    run_configs: Mapping[str, ConfigKey],
    *,
    input_no_for: Callable[[EvalInput], int],
    half_for: Callable[[int], Half],
    invalid_markers: Mapping[str, InvalidReason] = {},
    transport_codes: frozenset[str],
) -> list[RecordedEpisode]:
    """Every episode this eval config recorded for the given run configs.

    Scores are joined to traces through `EvalRun.scored_run_id`; the run config a trace
    came from is read off the run's own output source, so a trace that was reused for a
    different config cannot be silently mis-keyed. A scored run the project cannot
    resolve — a missing trace, no run config id, a dangling `scored_run_id`, an eval input
    that is not there — raises rather than being dropped. The report step never guesses,
    and a silent drop would be worse than an error: `metrics.cells` fills the hole as a
    missing episode and labels it `reset_anomaly`, laundering a data-integrity bug into a
    plausible invalidity count."""
    runs_by_id = {
        run.id: run
        for run in task.runs(readonly=True, include_eval_generated=True)
        if run.eval_source is not None
    }
    inputs_by_id = {item.id: item for item in task.eval_inputs(readonly=True)}

    episodes: list[RecordedEpisode] = []
    for eval_run in eval_config.runs(readonly=True):
        if eval_run.scored_run_id is None:
            # A skip before generation: there is no trace to load and no episode to make.
            # `metrics.cells` fills the hole as a missing episode, which is what it is.
            continue
        run = runs_by_id.get(eval_run.scored_run_id)
        if run is None:
            raise ValueError(
                f"eval run {eval_run.id} scores task run {eval_run.scored_run_id}, "
                "which is missing or was not generated by an eval"
            )
        run_config_id = run.output.source.run_config_id if run.output.source else None
        if run_config_id is None:
            raise ValueError(
                f"task run {run.id} has no run_config_id on its output source"
            )
        key = run_configs.get(run_config_id)
        if key is None:
            continue
        if run.trace is None:
            raise ValueError(f"task run {run.id} has no trace")

        configuration, system, repeat = key
        eval_input = inputs_by_id.get(eval_run.eval_input_id)
        if eval_input is None:
            raise ValueError(
                f"eval run {eval_run.id} names eval input {eval_run.eval_input_id}, which is missing"
            )
        input_no = input_no_for(eval_input)

        malformed = False
        try:
            steps = extract_steps(run.trace)
        except ValueError:
            malformed = True
            steps = []

        world_episode = (
            run.world_episode.to_sandbox_dict()
            if run.world_episode is not None
            else None
        )
        marker = invalid_markers.get(str(run.id))
        episodes.append(
            RecordedEpisode(
                run_id=str(run.id),
                eval_input_id=str(eval_run.eval_input_id),
                run_config_id=run_config_id,
                configuration=configuration,
                system=system,
                repeat=repeat,
                input_no=input_no,
                half=half_for(input_no),
                trace=list(run.trace),
                steps=steps,
                assistant_indices=assistant_indices(run.trace),
                final_message=run.output.output,
                world_episode=world_episode,
                scores=dict(eval_run.scores) if eval_run.scores else None,
                skipped_reason=eval_run.skipped_reason,
                invalid=invalid_reason(
                    system=system,
                    steps=steps,
                    world_episode=world_episode,
                    marker=marker,
                    malformed=malformed,
                    transport_codes=transport_codes,
                ),
                usage=run.usage.model_dump(mode="json") if run.usage else None,
            )
        )
    return episodes
