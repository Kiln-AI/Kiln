"""`validity.json` and `validity.md`: the run's result, and everything needed to argue with it.

Two rules shape the schema. **A number is never shown without what it was computed from**:
every gate carries its inputs, so a reader can recompute the value or say why it is wrong.
And **an incomplete run says so**: `executed_steps` lists what actually ran, `complete` is
true only when the whole pipeline did, and a gate whose step did not run is emitted with a
null value and the outcome `skipped` rather than being left out.

The markdown is the same object rendered; nothing is computed here that is not in the JSON.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import JsonValue

from .cost import CostModel
from .faults import FaultResult
from .metrics import (
    Cell,
    ConfigScore,
    DecisionStat,
    DroppedPair,
    Gate,
    NearNeighbour,
    PairedCell,
    PairedStat,
    RankStat,
    SanityCounts,
)
from .replay import Mismatch, undeclared_classes
from .traces import Half

SCHEMA_VERSION = 2

Step = Literal["real", "world", "replay", "decision", "faults", "report"]

ALL_STEPS: tuple[Step, ...] = (
    "real",
    "world",
    "replay",
    "decision",
    "faults",
    "report",
)

DECISION_RULES: list[dict[str, str]] = [
    {
        "outcome": "replay clean, paired_delta over gate",
        "meaning": "world faithful on visited paths but eval outcome differs",
        "action": "thesis at risk; escalate before fixing",
    },
    {
        "outcome": "replay has undeclared classes",
        "meaning": "named tools diverge",
        "action": "fix the named tools, rerun the tuning half, report both runs",
    },
    {
        "outcome": "real-side zero variance",
        "meaning": "inputs do not discriminate",
        "action": "re-author inputs, not the world",
    },
    {
        "outcome": "conditional decision set empty",
        "meaning": "nothing to measure",
        "action": "report, no gate",
    },
    {
        "outcome": "any configuration unusable (< 40 of 60 valid)",
        "meaning": "too few pairs",
        "action": "run inconclusive; fix the invalidity source, rerun",
    },
    {
        "outcome": "a fault inconclusive (0 triggers)",
        "meaning": "the inputs never exercised the faulted line",
        "action": "add or repair the guaranteeing input; not a world fault",
    },
]

WHAT_THIS_DOES_NOT_PROVE: list[str] = [
    "generated worlds",
    "more than one resource family",
    "off-trajectory behaviour beyond the paired-targeted faults",
    "near-neighbour sensitivity beyond A/F",
]


@dataclass(frozen=True)
class Deviation:
    date: str
    item: str
    reasoning: str


@dataclass(frozen=True)
class RunMeta:
    run_id: str
    started_at: str
    finished_at: str
    world_version: str
    fixture_id: str
    fixture_exported_at: str
    fixture_age_days: int
    allow_stale: bool
    reference_version: str
    model_ids: dict[str, str]
    repeats: int
    input_pairs: int
    inputs: int
    configurations: list[str]
    halves: list[Half]
    sealed_world_version: str | None
    sealed_voided: bool
    decision_temperature: float
    world_ports: dict[str, int]
    reset_seconds: list[float]
    observed_429s: int
    deviations: list[Deviation]


def build_report(
    meta: RunMeta,
    *,
    executed_steps: Sequence[Step],
    gates: Sequence[Gate],
    cells: Sequence[Cell],
    paired: Sequence[PairedCell],
    dropped: Sequence[DroppedPair],
    scores: Sequence[ConfigScore],
    paired_stat: PairedStat | None,
    rank: RankStat | None,
    near: NearNeighbour | None,
    decision: DecisionStat | None,
    sanity: SanityCounts,
    mismatches: Sequence[Mismatch],
    caveats: Sequence[str],
    faults: Sequence[FaultResult],
    cost: CostModel,
    replay_steps: int | None = None,
    decision_records: int | None = None,
) -> dict[str, JsonValue]:
    """The report object.

    `scores` carries both shapes: the entries with a `half` are the per-half tables and the
    entries without are the combined ones, which is how `config_scores` distinguishes them."""
    executed = list(executed_steps)
    kinds: dict[str, int] = {}
    for mismatch in mismatches or []:
        kinds[mismatch.kind] = kinds.get(mismatch.kind, 0) + 1
    # Never invented. A step count nobody supplied is unknown, and `_replay_gate` says so
    # too; guessing `len(mismatches)` would publish "0 matching steps" for a clean replay.
    steps = replay_steps
    _check_gates(gates, executed, replay_steps)
    if steps is not None and steps < len(mismatches or []):
        raise ValueError(
            f"{len(mismatches or [])} mismatches were recorded across {steps} replayed "
            "steps, which cannot be: one of the two is not this run's"
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "meta": _plain(asdict(meta)),
        "executed_steps": executed,
        "complete": all(step in executed for step in ALL_STEPS),
        "gates": [_plain(asdict(gate)) for gate in gates],
        "cells": [_plain(asdict(cell)) for cell in cells],
        "pairs": {
            "kept": len(paired),
            "dropped": [
                {
                    "key": list(item.key),
                    "reason": item.reason,
                    "lane": item.lane,
                }
                for item in dropped
            ],
        },
        "scores": [_plain(asdict(s)) for s in scores if s.half is None],
        "scores_by_half": [_plain(asdict(s)) for s in scores if s.half is not None],
        "paired": _plain(asdict(paired_stat)) if paired_stat else None,
        "near_neighbour": _plain(asdict(near)) if near else None,
        "rank": _plain(asdict(rank)) if rank else None,
        "tie_band": (
            [
                [a, b, _plain(asdict(interval))]
                for a, b, interval in rank.indistinguishable
            ]
            if rank
            else []
        ),
        "ties": _plain(rank.ties) if rank else {"real": [], "world": []},
        "replay": {
            "steps": steps,
            "ok": None if steps is None else steps - len(mismatches or []),
            "declared": kinds.get("declared", 0),
            "unserved": kinds.get("unserved", 0),
            "transport": kinds.get("transport", 0),
            "mismatches": [_plain(asdict(m)) for m in mismatches or []],
            "undeclared_classes": [
                list(item) for item in undeclared_classes(mismatches or [])
            ],
        },
        "decision": _decision(decision, decision_records),
        "sanity": _plain(asdict(sanity)),
        "faults": [_plain(asdict(result)) for result in faults],
        "cost": _plain(asdict(cost)),
        "caveats": list(caveats),
        "decision_rules": DECISION_RULES,
        "what_this_does_not_prove": WHAT_THIS_DOES_NOT_PROVE,
    }


GATE_STEPS: dict[str, Step] = {
    "replay": "replay",
    "paired": "world",
    "rank": "world",
    "decision": "decision",
    "faults": "faults",
}
"""The pipeline step each gate is computed from. The paired and rank gates need both
arms, and the real step always precedes the world one, so the world step stands for both."""


def _check_gates(
    gates: Sequence[Gate], executed: Sequence[str], replay_steps: int | None
) -> None:
    """A gate whose step did not run must be null and `skipped`, and the replay counts the
    report publishes must be the ones the gate was judged on.

    The rule is stated in three places — `evaluate_gates`, `fault_gate` and the report —
    and this is the one place that can see both halves, so it is the one place that can
    catch a driver assembling a report from a gate list and a step list that disagree."""
    ran = set(executed)
    for gate in gates:
        if gate.name not in GATE_STEPS:
            raise ValueError(
                f"gate '{gate.name}' is not one this report knows how to place; "
                f"known gates are {sorted(GATE_STEPS)}"
            )
        step = GATE_STEPS[gate.name]
        if step not in ran:
            if (
                gate.outcome != "skipped"
                or gate.value is not None
                or gate.passed is not None
            ):
                raise ValueError(
                    f"gate '{gate.name}' reports {gate.outcome} with value "
                    f"{gate.value!r}, but step '{step}' is not in executed_steps "
                    f"{list(executed)}"
                )
            continue
        if gate.name == "replay":
            judged = gate.inputs.get("steps")
            if judged != replay_steps:
                raise ValueError(
                    f"the replay gate was judged on {judged!r} steps but the report was "
                    f"given {replay_steps!r}; one of the two is not this run's"
                )


def _decision(stat: DecisionStat | None, records: int | None) -> JsonValue:
    if stat is None:
        return None
    out = _plain(asdict(stat))
    if isinstance(out, dict):
        out["records"] = records
    return out


def _plain(value: Any) -> Any:
    """Dataclass output reduced to JSON: tuple keys and non-serializable leaves become
    strings rather than breaking the write at the end of a long run.

    A non-finite float becomes null. `json.dumps` writes bare `NaN` and `Infinity`, which
    are not JSON and which every strict reader rejects — including the regrade step that
    reads this file back."""
    if isinstance(value, dict):
        return {_key(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if isinstance(value, float):
        return value
    return str(value)


def _key(key: Any) -> str:
    if isinstance(key, tuple):
        return ":".join(str(part) for part in key)
    return str(key)


def write_report(report: dict[str, JsonValue], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "validity.json"
    md_path = out_dir / "validity.md"
    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path


# ---- markdown ----


def _fmt(value: Any, places: int = 3) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.{places}f}"
    return str(value)


def _interval(interval: Any) -> str:
    if not isinstance(interval, dict):
        return "—"
    return f"[{_fmt(interval.get('low'))}, {_fmt(interval.get('high'))}]"


def _cell(text: str) -> str:
    """A markdown table cell. A `|` or a newline in a value — an error message, a tool
    argument — would otherwise split the row into the wrong number of columns."""
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    lines = ["| " + " | ".join(_cell(h) for h in headers) + " |"]
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    for row in rows:
        lines.append("| " + " | ".join(_cell(value) for value in row) + " |")
    return lines


def render_markdown(report: dict[str, JsonValue]) -> str:
    meta = report.get("meta") or {}
    meta = meta if isinstance(meta, dict) else {}
    out: list[str] = [
        f"# Validity report: {meta.get('run_id', 'unknown run')}",
        "",
        f"Complete: {_fmt(report.get('complete'))}. "
        f"Steps executed: {', '.join(str(s) for s in _items(report.get('executed_steps'))) or 'none'}.",
        "",
        "## Gates",
        "",
    ]
    out += _table(
        ["gate", "value", "threshold", "interval", "outcome", "reason"],
        [
            [
                str(gate.get("name")),
                _fmt(gate.get("value")),
                _fmt(gate.get("threshold")),
                _interval(gate.get("interval")),
                str(gate.get("outcome")),
                str(gate.get("reason") or ""),
            ]
            for gate in _dicts(report.get("gates"))
        ],
    )

    out += ["", "## Failure decision rules", ""]
    out += _table(
        ["outcome", "meaning", "action"],
        [
            [rule.get("outcome", ""), rule.get("meaning", ""), rule.get("action", "")]
            for rule in _dicts(report.get("decision_rules"))
        ],
    )

    for title, key in (
        ("Per-configuration scores (combined)", "scores"),
        ("Per-configuration scores (by half)", "scores_by_half"),
    ):
        rows = _dicts(report.get(key))
        if not rows:
            continue
        out += ["", f"## {title}", ""]
        out += _table(
            [
                "cfg",
                "system",
                "half",
                "episodes",
                "valid",
                "invalid",
                "skipped",
                "pass ± se",
                "predicates",
                "collateral",
                "steps",
                "usable",
            ],
            [
                [
                    str(row.get("configuration")),
                    str(row.get("system")),
                    str(row.get("half") or "all"),
                    _fmt(row.get("episodes")),
                    _fmt(row.get("valid")),
                    _fmt(row.get("invalid")),
                    _fmt(row.get("skipped")),
                    f"{_fmt(row.get('pass_rate'))} ± {_fmt(row.get('se'))}",
                    _fmt(row.get("predicates_rate")),
                    _fmt(row.get("collateral_rate")),
                    _fmt(row.get("mean_steps"), 2),
                    _fmt(row.get("usable")),
                ]
                for row in rows
            ],
        )

    near = report.get("near_neighbour")
    if isinstance(near, dict):
        out += [
            "",
            "## Near neighbour",
            "",
            f"{near.get('a')} vs {near.get('f')}: real {near.get('real_order')}, "
            f"world {near.get('world_order')} — reproduced: {_fmt(near.get('reproduced'))}.",
        ]

    band = report.get("tie_band")
    out += ["", "## Tie band", ""]
    if isinstance(band, list) and band:
        out += _table(
            ["a", "b", "real difference interval"],
            [
                [str(item[0]), str(item[1]), _interval(item[2])]
                for item in band
                if isinstance(item, (list, tuple)) and len(item) == 3
            ],
        )
    else:
        out += ["No pair of configurations is indistinguishable on the real arm."]

    paired = report.get("paired")
    if isinstance(paired, dict):
        out += [
            "",
            "## Paired cells",
            "",
            f"delta {_fmt(paired.get('delta'))} over {_fmt(paired.get('cells'))} cells, "
            f"interval {_interval(paired.get('interval'))}, "
            f"cell agreement {_fmt(paired.get('cell_agreement'))}.",
        ]
        gate = _gate(report, "paired")
        rates = (gate.get("inputs") or {}).get("cell_rates") if gate else None
        if isinstance(rates, dict) and rates:
            out += [""]
            out += _table(
                ["cell", "p_real", "p_world"],
                [
                    [str(key), _fmt(value[0]), _fmt(value[1])]
                    for key, value in sorted(rates.items())
                    if isinstance(value, list) and len(value) == 2
                ],
            )

    replay = report.get("replay")
    if isinstance(replay, dict):
        out += [
            "",
            "## Replay",
            "",
            f"{_fmt(replay.get('steps'))} steps, {_fmt(replay.get('ok'))} matching, "
            f"{_fmt(replay.get('declared'))} declared, {_fmt(replay.get('unserved'))} unserved, "
            f"{_fmt(replay.get('transport'))} transport-excluded.",
            "",
        ]
        undeclared = replay.get("undeclared_classes")
        if isinstance(undeclared, list) and undeclared:
            out += ["Undeclared divergence classes:", ""]
            out += [f"- `{item[0]}` at `{item[1]}`" for item in undeclared]
        else:
            out += ["No undeclared divergence classes."]
        grouped: dict[str, list[dict[str, Any]]] = {}
        for mismatch in _dicts(replay.get("mismatches")):
            grouped.setdefault(str(mismatch.get("tool_name")), []).append(mismatch)
        for tool in sorted(grouped):
            out += ["", f"### {tool}", ""]
            out += _table(
                ["run", "step", "kind", "declared", "classes"],
                [
                    [
                        str(m.get("run_id")),
                        _fmt(m.get("step_index")),
                        str(m.get("kind")),
                        ", ".join(str(d) for d in m.get("declared") or []) or "—",
                        ", ".join(
                            str(c[1])
                            for c in m.get("classes") or []
                            if isinstance(c, (list, tuple)) and len(c) == 2
                        )
                        or "—",
                    ]
                    for m in grouped[tool]
                ],
            )

    decision = report.get("decision")
    if isinstance(decision, dict):
        out += [
            "",
            "## Decision replay",
            "",
            f"Conditional: world {_fmt(decision.get('world_conditional'))}, "
            f"control {_fmt(decision.get('control_conditional'))}, "
            f"difference {_fmt(decision.get('difference'))} "
            f"{_interval(decision.get('interval'))}.",
            f"Unconditional: world {_fmt(decision.get('world_unconditional'))}, "
            f"control {_fmt(decision.get('control_unconditional'))}. "
            f"{_fmt(decision.get('divergent_decisions'))} divergent-prefix decisions, "
            f"{_fmt(decision.get('control_decisions'))} control-prefix.",
            "",
        ]
        per_configuration = decision.get("per_configuration")
        if isinstance(per_configuration, dict) and per_configuration:
            out += _table(
                ["cfg", "world", "control"],
                [
                    [
                        str(name),
                        _fmt((arms or {}).get("world")),
                        _fmt((arms or {}).get("control")),
                    ]
                    for name, arms in sorted(per_configuration.items())
                ],
            )

    sanity = report.get("sanity")
    if isinstance(sanity, dict):
        invalid = sanity.get("invalid")
        out += [
            "",
            "## Sanity counts",
            "",
            f"Dropped pairs {_fmt(sanity.get('dropped_pairs'))}, "
            f"world gaps {_fmt(sanity.get('world_gaps'))}, "
            f"settle errors {_fmt(sanity.get('settle_errors'))}.",
        ]
        unscored = sanity.get("unscored")
        if isinstance(unscored, int) and unscored:
            out += [
                "",
                f"{unscored} episodes ran, came back with no score and were not flagged "
                "invalid. Their pairs are dropped under `judge_failure`, the closest "
                "reason the taxonomy has, but no judge traceback was written for them.",
            ]
        if isinstance(invalid, dict):
            out += [""]
            out += _table(
                ["lane", "configuration", "invalid"],
                [
                    [str(lane), str(name), _fmt(count)]
                    for lane, counts in sorted(invalid.items())
                    for name, count in sorted((counts or {}).items())
                ],
            )

    faults = _dicts(report.get("faults"))
    out += ["", "## Faults", ""]
    if faults:
        out += _table(
            [
                "fault",
                "target",
                "port",
                "version",
                "triggers",
                "moved",
                "statistic",
                "outcome",
            ],
            [
                [
                    str(f.get("fault")),
                    str(f.get("target")),
                    _fmt(f.get("port")),
                    str(f.get("world_version")),
                    _fmt(f.get("triggers")),
                    ", ".join(str(m) for m in f.get("moved") or []) or "—",
                    _fmt(f.get("statistic_moved")),
                    "inconclusive"
                    if f.get("inconclusive")
                    else ("detected" if f.get("detected") else "undetected"),
                ]
                for f in faults
            ],
        )
    else:
        out += ["The fault step did not run."]

    cost = report.get("cost")
    if isinstance(cost, dict):
        out += ["", "## Cost", ""]
        out += _table(
            ["line", "count", "estimate", "observed", "basis"],
            [
                [
                    str(line.get("name")),
                    _fmt(line.get("count")),
                    f"${_fmt(line.get('estimate_usd'), 2)}",
                    f"${_fmt(line.get('observed_usd'), 2)}",
                    str(line.get("basis")),
                ]
                for line in _dicts(cost.get("lines"))
            ],
        )
        out += [
            "",
            f"Total estimate ${_fmt(cost.get('total_estimate_usd'), 2)}, "
            f"observed ${_fmt(cost.get('total_observed_usd'), 2)}, "
            f"pricing from {cost.get('pricing_source')}.",
        ]

    caveats = report.get("caveats")
    out += ["", "## Caveats", ""]
    out += (
        [f"- {item}" for item in caveats]
        if isinstance(caveats, list) and caveats
        else ["None."]
    )

    out += ["", "## What this does not prove", ""]
    out += [f"- {item}" for item in _items(report.get("what_this_does_not_prove"))]

    deviations = _dicts(meta.get("deviations"))
    out += ["", "## Deviations", ""]
    if deviations:
        out += _table(
            ["date", "item", "reasoning"],
            [
                [str(d.get("date")), str(d.get("item")), str(d.get("reasoning"))]
                for d in deviations
            ],
        )
    else:
        out += ["None recorded."]

    out += [
        "",
        "## Run metadata",
        "",
        f"- World version: {meta.get('world_version')}",
        f"- Fixture: {meta.get('fixture_id')} exported {meta.get('fixture_exported_at')} "
        f"({meta.get('fixture_age_days')} days old, allow_stale={_fmt(meta.get('allow_stale'))})",
        f"- Reference version: {meta.get('reference_version')}",
        f"- Design: {meta.get('input_pairs')} input pairs, {meta.get('inputs')} inputs, "
        f"{meta.get('repeats')} repeats, configurations "
        f"{', '.join(str(c) for c in _items(meta.get('configurations')))}",
        f"- Halves: {', '.join(str(h) for h in _items(meta.get('halves')))}; "
        f"sealed world version {meta.get('sealed_world_version')}, "
        f"voided={_fmt(meta.get('sealed_voided'))}",
        f"- Decision temperature: {_fmt(meta.get('decision_temperature'))}",
        f"- Observed 429s: {_fmt(meta.get('observed_429s'))}",
        f"- Started {meta.get('started_at')}, finished {meta.get('finished_at')}",
        "",
    ]
    return "\n".join(out)


def _items(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _gate(report: dict[str, JsonValue], name: str) -> dict[str, Any] | None:
    for gate in _dicts(report.get("gates")):
        if gate.get("name") == name:
            return gate
    return None
