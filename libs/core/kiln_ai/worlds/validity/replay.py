"""Tool-level replay: send every call a recorded episode made to the world instead, and
compare what comes back.

This is the cheapest and sharpest fidelity measurement in the harness — no model, no
grader, one shim instance per episode — and the only one that names the tool and the field
that diverged. The gate is not the number of mismatching steps but the number of
*undeclared divergence classes*: a `(tool name, path signature)` pair that the world's own
evidence file does not already declare. One page-size bug reports as one class however many
steps it touches.

Steps that cannot be replayed are counted, never scored: a recorded transport error
(`upstream_error`, `rate_limited`) never reached the modelled product at all, and a tool
the world does not serve (a distractor in the run config) has nothing to answer with.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import JsonValue

from kiln_ai.worlds.shim.errors import ToolError
from kiln_ai.worlds.shim.world import World

from .idmap import IdMap, created_id, id_strings
from .scrub import (
    MISSING,
    Diff,
    ScrubRules,
    as_json,
    compare,
    is_declared,
)
from .traces import RecordedEpisode, error_code

SCHEMA_VERSION = 1

MismatchKind = Literal[
    "mismatch",
    "declared",
    "error_code",
    "ambiguous_id",
    "unknown_id",
    "unserved",
    "transport",
]

StepKind = Literal["ok"] | MismatchKind
"""A replayed step's outcome, including the steps that matched."""

GATING_KINDS: frozenset[str] = frozenset({"mismatch", "error_code"})
"""The kinds that count against the replay gate. Everything else is reported."""

DivergenceClass = tuple[str, str]


@dataclass(frozen=True)
class Mismatch:
    run_id: str
    configuration: str
    step_index: int
    tool_name: str
    arguments: dict[str, JsonValue]
    recorded: JsonValue
    replayed: JsonValue
    diffs: list[Diff]
    kind: MismatchKind
    declared: tuple[str, ...]
    classes: tuple[DivergenceClass, ...]


@dataclass(frozen=True)
class ReplayedEpisode:
    run_id: str
    results: list[JsonValue]
    mismatches: list[Mismatch]
    id_pairs: list[tuple[str, str]]
    divergent_steps: frozenset[int]
    records: list[dict[str, JsonValue]] = field(default_factory=list)
    """One replay.jsonl record per step, including the steps that matched: the report
    counts steps, and a matching step leaves no Mismatch behind to count."""

    @property
    def skipped_steps(self) -> frozenset[int]:
        """Steps the world was never asked to answer (unserved or transport-excluded).
        Distinct from a step whose world result happens to be null."""
        return frozenset(
            m.step_index for m in self.mismatches if m.kind in ("unserved", "transport")
        )


def argument_ids(episode: RecordedEpisode, after_step: int) -> frozenset[str]:
    """The id-shaped strings a later call in this episode passes as an argument.

    An id in a result only has to map when the episode went on to use it; every other
    server-minted id is compared by presence."""
    found: set[str] = set()
    for step in episode.steps:
        if step.index <= after_step:
            continue
        found.update(id_strings(step.arguments))
    return frozenset(found)


def replay_episode(
    world: World,
    fixture: str,
    episode: RecordedEpisode,
    rules: ScrubRules,
    id_map: IdMap,
    *,
    served_tools: frozenset[str],
    startup_kwargs: Mapping[str, Any] = {},
    known_ids: frozenset[str] = frozenset(),
) -> ReplayedEpisode:
    """Replay one recorded episode against a fresh instance of `fixture`.

    `known_ids` is the fixture's own id set (from the world's export), so `unknown_id` means
    "an id that is neither the fixture's nor created here". It defaults to empty, in which
    case every id-shaped argument the episode did not create is reported as unknown; pass
    the fixture's ids to make the check meaningful."""
    results: list[JsonValue] = []
    mismatches: list[Mismatch] = []
    records: list[dict[str, JsonValue]] = []
    divergent: set[int] = set()
    ambiguous = _ambiguous_steps(episode, id_map.create_tools)

    instance = world.instance(fixture, **dict(startup_kwargs))
    try:
        for step in episode.steps:
            if step.error_code is not None and step.error_code in rules.transport_codes:
                results.append(None)
                _add(
                    mismatches,
                    records,
                    episode,
                    step,
                    dict(step.arguments),
                    None,
                    [],
                    "transport",
                    (),
                    [],
                )
                continue
            if step.tool_name not in served_tools:
                results.append(None)
                _add(
                    mismatches,
                    records,
                    episode,
                    step,
                    dict(step.arguments),
                    None,
                    [],
                    "unserved",
                    (),
                    [],
                )
                continue

            # `to_world` preserves shape, so a dict in is a dict out.
            arguments = id_map.to_world(dict(step.arguments))
            assert isinstance(arguments, dict)
            unknown = id_map.unknown_ids(arguments, known_ids)
            result = _call(instance, step.tool_name, arguments)

            recorded_new = created_id(step.tool_name, step.result, id_map.create_tools)
            replayed_new = created_id(step.tool_name, result, id_map.create_tools)
            step_pairs: list[tuple[str, str]] = []
            if recorded_new and replayed_new:
                id_map.record(recorded_new, replayed_new)
                step_pairs.append((recorded_new, replayed_new))

            back = id_map.to_recorded(result)
            results.append(back)
            exact = argument_ids(episode, step.index) | {
                recorded for recorded, _ in id_map.pairs
            }
            diffs = compare(step.result, back, rules, exact_ids=exact)
            if bool(recorded_new) != bool(replayed_new):
                diffs = _ensure_id_diff(diffs, recorded_new, replayed_new)

            declared = is_declared(step.tool_name, diffs, rules) if diffs else ()
            kind = _kind(
                diffs,
                declared,
                step.result,
                back,
                ambiguous=step.index in ambiguous,
                unknown=bool(unknown),
            )
            if kind in GATING_KINDS:
                divergent.add(step.index)
            _add(
                mismatches,
                records,
                episode,
                step,
                arguments,
                back,
                diffs,
                kind,
                declared,
                step_pairs,
                unknown=unknown,
            )
    finally:
        instance.destroy()

    return ReplayedEpisode(
        run_id=episode.run_id,
        results=results,
        mismatches=mismatches,
        id_pairs=id_map.pairs,
        divergent_steps=frozenset(divergent),
        records=records,
    )


def _call(instance: Any, tool_name: str, arguments: dict[str, JsonValue]) -> JsonValue:
    """The world's answer, with a tool error rendered as the same envelope the real tool
    would have returned, so the two compare as results rather than as an exception."""
    try:
        return instance.call(tool_name, **arguments)
    except ToolError as error:
        return {"error": error.to_dict()}


def _ensure_id_diff(
    diffs: list[Diff], recorded_new: str | None, replayed_new: str | None
) -> list[Diff]:
    """One side created a row and the other did not. The comparison may already say so
    (a missing key, a null against a string); if it does not, say it here."""
    if any(diff.path == "/id" for diff in diffs):
        return diffs
    return [*diffs, Diff("/id", recorded_new or MISSING, replayed_new or MISSING)]


def _kind(
    diffs: Sequence[Diff],
    declared: tuple[str, ...],
    recorded: JsonValue,
    replayed: JsonValue,
    *,
    ambiguous: bool,
    unknown: bool,
) -> StepKind:
    if diffs:
        if declared:
            return "declared"
        recorded_code = error_code(recorded)
        replayed_code = error_code(replayed)
        if recorded_code and replayed_code and recorded_code != replayed_code:
            return "error_code"
        return "mismatch"
    if ambiguous:
        return "ambiguous_id"
    if unknown:
        return "unknown_id"
    return "ok"


def _ambiguous_steps(
    episode: RecordedEpisode, create_tools: frozenset[str]
) -> set[int]:
    """Two creates in one parallel group: the reference system's application order is
    unknown, so the pairing is by `tool_calls` order and the steps are flagged."""
    by_message: dict[int, list[int]] = {}
    for step in episode.steps:
        if step.tool_name in create_tools:
            by_message.setdefault(step.message_index, []).append(step.index)
    return {
        index
        for indices in by_message.values()
        if len(indices) > 1
        for index in indices
    }


def _add(
    mismatches: list[Mismatch],
    records: list[dict[str, JsonValue]],
    episode: RecordedEpisode,
    step: Any,
    arguments: dict[str, JsonValue],
    replayed: JsonValue,
    diffs: list[Diff],
    kind: StepKind,
    declared: tuple[str, ...],
    step_pairs: list[tuple[str, str]],
    unknown: Sequence[str] = (),
) -> None:
    classes = tuple(
        dict.fromkeys((step.tool_name, diff.divergence_signature) for diff in diffs)
    )
    if kind != "ok":
        mismatches.append(
            Mismatch(
                run_id=episode.run_id,
                configuration=episode.configuration,
                step_index=step.index,
                tool_name=step.tool_name,
                arguments=arguments,
                recorded=step.result,
                replayed=replayed,
                diffs=list(diffs),
                kind=kind,  # type: ignore[arg-type]
                declared=declared,
                classes=classes,
            )
        )
    records.append(
        {
            "schema_version": SCHEMA_VERSION,
            "run_id": episode.run_id,
            "configuration": episode.configuration,
            "repeat": episode.repeat,
            "eval_input_id": episode.eval_input_id,
            "input_no": episode.input_no,
            "half": episode.half,
            "step_index": step.index,
            "tool_name": step.tool_name,
            "arguments": as_json(arguments),
            "recorded": as_json(step.result),
            "replayed": as_json(replayed),
            "kind": kind,
            "declared": list(declared),
            "classes": [list(c) for c in classes],
            "diffs": [
                {
                    "path": diff.path,
                    "recorded": as_json(diff.recorded),
                    "replayed": as_json(diff.replayed),
                }
                for diff in diffs
            ],
            "id_pairs": [list(pair) for pair in step_pairs],
            "unknown_ids": list(unknown),
        }
    )


def replay_all(
    world: World,
    fixture: str,
    episodes: Iterable[RecordedEpisode],
    rules: ScrubRules,
    *,
    create_tools: frozenset[str],
    served_tools: frozenset[str],
    out: Path,
    startup_kwargs: Mapping[str, Any] = {},
    known_ids: frozenset[str] = frozenset(),
) -> list[ReplayedEpisode]:
    """Replay every episode, appending one line per step to `out`.

    `known_ids` defaults to empty, in which case every id-shaped argument the episode did
    not create is reported as `unknown_id`; pass the fixture's ids to make the check
    meaningful. Non-gating either way, but an empty set inflates the mismatch list and
    drives the reported `ok` count down."""
    out.parent.mkdir(parents=True, exist_ok=True)
    replayed: list[ReplayedEpisode] = []
    with out.open("a", encoding="utf-8") as handle:
        for episode in episodes:
            one = replay_episode(
                world,
                fixture,
                episode,
                rules,
                IdMap(create_tools),
                served_tools=served_tools,
                startup_kwargs=startup_kwargs,
                known_ids=known_ids,
            )
            for record in one.records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            replayed.append(one)
    return replayed


def undeclared_classes(mismatches: Sequence[Mismatch]) -> list[DivergenceClass]:
    """The divergence classes the world has not declared: the replay gate's value."""
    classes: dict[DivergenceClass, None] = {}
    for mismatch in mismatches:
        if mismatch.kind not in GATING_KINDS:
            continue
        for item in mismatch.classes:
            classes.setdefault(item, None)
    return sorted(classes)
