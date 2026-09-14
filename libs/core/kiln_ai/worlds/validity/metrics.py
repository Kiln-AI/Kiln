"""The numbers and the gates.

Every statistic runs on *kept pairs*: an episode on one arm counts only when its twin on
the other arm counts too, so the two systems are always scored on the same inputs and an
invalid episode can never flatter either one. What an episode was dropped for is reported
per lane and per reason instead of being folded into a score.

Three properties are deliberate:

- **Clustering.** The repeats of one input are not independent, so the paired bootstrap
  resamples inputs, and the decision bootstrap resamples episodes.
- **Emptiness never passes.** A step that did not run gives `skipped` gates with null
  values; a step that ran on nothing gives `inconclusive` gates with a reason. Nothing
  raises on empty input and nothing passes on it.
- **Zero variance is read by side.** The real arm not separating the configurations is a
  fact about the inputs; the world arm not separating them is a fact about the world.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Literal

from pydantic import JsonValue

from .decision import Arm, DecisionRecord, PrefixKind
from .replay import Mismatch, undeclared_classes
from .traces import Half, InvalidReason, PairKey, RecordedEpisode, System

if TYPE_CHECKING:  # faults imports the gate types from here; the cycle is types only
    from .faults import FaultResult

SYSTEMS: tuple[System, ...] = ("real", "world")

DEFAULT_SCORE_NAMES: tuple[str, str] = ("predicates_pass", "collateral_pass")
"""The two output scores an episode passes on. Names, not meanings: the eval defines them."""


def _passed(score: float | None) -> bool | None:
    return None if score is None else score >= 0.5


@dataclass(frozen=True)
class Cell:
    configuration: str
    input_no: int
    repeat: int
    system: System
    half: Half
    run_id: str | None
    passed: bool | None
    invalid: InvalidReason | None
    steps: int | None
    scores: dict[str, float] | None = None
    """The episode's raw output scores, so the per-configuration tables can report the
    components beside the combined verdict."""

    @property
    def pair_key(self) -> PairKey:
        return (self.configuration, self.input_no, self.repeat)

    @property
    def skipped(self) -> bool:
        """Ran, was not scored, and was not flagged invalid."""
        return self.invalid is None and self.passed is None and self.run_id is not None


@dataclass(frozen=True)
class PairedCell:
    configuration: str
    input_no: int
    repeat: int
    half: Half
    real: bool
    world: bool

    @property
    def pair_key(self) -> PairKey:
        return (self.configuration, self.input_no, self.repeat)


@dataclass(frozen=True)
class DroppedPair:
    key: PairKey
    reason: InvalidReason
    lane: System


@dataclass(frozen=True)
class Interval:
    low: float
    high: float
    level: float = 0.95
    resamples: int = 2000
    seed: int = 0

    def spans(self, value: float) -> bool:
        return self.low <= value <= self.high


def cells(
    episodes: Sequence[RecordedEpisode],
    *,
    expected: Sequence[PairKey],
    score_names: tuple[str, str] = DEFAULT_SCORE_NAMES,
    half_for: Callable[[int], Half] | None = None,
) -> list[Cell]:
    """The full design, one cell per expected (configuration, input, repeat) per system.

    An episode that was never generated — a reset anomaly that aborted before the run, a
    budget stop — is a cell with no run id, so the design's shape is visible in the report
    rather than being inferred from what happens to be present."""
    by_key: dict[tuple[str, System, int, int], RecordedEpisode] = {
        (e.configuration, e.system, e.input_no, e.repeat): e for e in episodes
    }
    halves: dict[int, Half] = {e.input_no: e.half for e in episodes}
    out: list[Cell] = []
    for configuration, input_no, repeat in expected:
        for system in SYSTEMS:
            episode = by_key.get((configuration, system, input_no, repeat))
            if episode is None:
                half: Half = (
                    half_for(input_no)
                    if half_for is not None
                    else halves.get(input_no, "tuning")
                )
                out.append(
                    Cell(
                        configuration=configuration,
                        input_no=input_no,
                        repeat=repeat,
                        system=system,
                        half=half,
                        run_id=None,
                        passed=None,
                        invalid="reset_anomaly",
                        steps=None,
                    )
                )
                continue
            scores = episode.scores
            passed: bool | None = None
            if scores is not None and all(name in scores for name in score_names):
                passed = all(bool(_passed(scores[name])) for name in score_names)
            out.append(
                Cell(
                    configuration=configuration,
                    input_no=input_no,
                    repeat=repeat,
                    system=system,
                    half=episode.half,
                    run_id=episode.run_id,
                    passed=passed,
                    invalid=episode.invalid,
                    steps=len(episode.steps),
                    scores=dict(scores) if scores else None,
                )
            )
    return out


def pair_cells(
    cells: Sequence[Cell],
) -> tuple[list[PairedCell], list[DroppedPair]]:
    """Kept pairs and the pairs that were dropped, with the lane and reason that dropped
    them. A pair goes when either member is invalid, missing, or was never scored."""
    by_key: dict[PairKey, dict[System, Cell]] = {}
    for cell in cells:
        by_key.setdefault(cell.pair_key, {})[cell.system] = cell

    kept: list[PairedCell] = []
    dropped: list[DroppedPair] = []
    for key in sorted(by_key):
        members = by_key[key]
        bad: tuple[System, InvalidReason] | None = None
        for system in SYSTEMS:
            cell = members.get(system)
            if cell is None:
                bad = (system, "reset_anomaly")
                break
            if cell.invalid is not None:
                bad = (system, cell.invalid)
                break
            if cell.passed is None:
                # Ran, came back unscored and unflagged: the judge produced nothing.
                bad = (system, "judge_failure")
                break
        if bad is not None:
            dropped.append(DroppedPair(key=key, reason=bad[1], lane=bad[0]))
            continue
        real = members["real"]
        world = members["world"]
        kept.append(
            PairedCell(
                configuration=key[0],
                input_no=key[1],
                repeat=key[2],
                half=real.half,
                real=bool(real.passed),
                world=bool(world.passed),
            )
        )
    return kept, dropped


# ---- bootstraps ----


def _percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = fraction * (len(ordered) - 1)
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _interval(
    values: Sequence[float], *, level: float, resamples: int, seed: int
) -> Interval:
    usable = [v for v in values if not math.isnan(v)]
    if not usable:
        return Interval(0.0, 0.0, level=level, resamples=resamples, seed=seed)
    tail = (1.0 - level) / 2.0
    return Interval(
        low=_percentile(usable, tail),
        high=_percentile(usable, 1.0 - tail),
        level=level,
        resamples=resamples,
        seed=seed,
    )


def _clustered(
    clusters: Mapping[object, Sequence[object]],
    statistic: Callable[[Sequence[object]], float],
    relabel: Callable[[object, int], object],
    *,
    resamples: int,
    seed: int,
    level: float = 0.95,
) -> Interval:
    """A percentile interval over `resamples` draws of the clusters, with replacement.

    `relabel` gives each *draw* its own cluster identity. Without it the resample is not a
    bootstrap at all: every statistic here re-groups its input by the clustering key, so a
    cluster drawn twice either collapses back into one group (the paired rates) or
    overwrites itself in a dict (the decision pairs). The duplicates would vanish, leaving
    a random subset of the clusters rather than a weighted draw — and an interval too
    narrow, in the direction that makes a one-sided gate easier to pass."""
    keys = sorted(clusters, key=repr)
    if not keys:
        return Interval(0.0, 0.0, level=level, resamples=resamples, seed=seed)
    rng = random.Random(seed)
    values: list[float] = []
    for _ in range(resamples):
        sample: list[object] = []
        for draw in range(len(keys)):
            key = keys[rng.randrange(len(keys))]
            sample.extend(relabel(member, draw) for member in clusters[key])
        try:
            values.append(statistic(sample))
        except (ValueError, ZeroDivisionError):
            continue
    return _interval(values, level=level, resamples=resamples, seed=seed)


def bootstrap_inputs(
    paired: Sequence[PairedCell],
    statistic: Callable[[Sequence[PairedCell]], float],
    *,
    resamples: int = 2000,
    seed: int = 0,
) -> Interval:
    """A percentile interval resampling *inputs* with replacement: the repeats of one
    input move together, because they are not independent observations."""
    clusters: dict[object, list[object]] = {}
    for cell in paired:
        clusters.setdefault(cell.input_no, []).append(cell)
    return _clustered(
        clusters,
        statistic,  # type: ignore[arg-type]
        lambda cell, draw: replace(cell, input_no=-1 - draw),  # type: ignore[arg-type]
        resamples=resamples,
        seed=seed,
    )


def bootstrap_episodes(
    records: Sequence[DecisionRecord],
    statistic: Callable[[Sequence[DecisionRecord]], float],
    *,
    resamples: int = 2000,
    seed: int = 0,
) -> Interval:
    """A percentile interval resampling *episodes*: the decisions of one episode share a
    prefix and a trajectory."""
    clusters: dict[object, list[object]] = {}
    for record in records:
        clusters.setdefault(record.run_id, []).append(record)
    return _clustered(
        clusters,
        statistic,  # type: ignore[arg-type]
        lambda record, draw: replace(record, run_id=f"__draw_{draw}"),  # type: ignore[arg-type]
        resamples=resamples,
        seed=seed,
    )


# ---- the paired statistic ----


@dataclass(frozen=True)
class PairedStat:
    delta: float
    interval: Interval
    cell_agreement: float
    cells: int


def cell_rates(
    paired: Sequence[PairedCell],
) -> dict[tuple[str, int], tuple[float, float]]:
    """Pass rates per (configuration, input) over the repeats that survived pairing."""
    grouped: dict[tuple[str, int], list[PairedCell]] = {}
    for cell in paired:
        grouped.setdefault((cell.configuration, cell.input_no), []).append(cell)
    return {
        key: (
            sum(1 for c in group if c.real) / len(group),
            sum(1 for c in group if c.world) / len(group),
        )
        for key, group in grouped.items()
    }


def delta_value(paired: Sequence[PairedCell]) -> float:
    rates = cell_rates(paired)
    if not rates:
        return float("nan")
    return sum(abs(world - real) for real, world in rates.values()) / len(rates)


def _verdict(rate: float) -> float:
    """A cell's majority verdict: 1, 0, or 0.5 for undecided, which agrees only with 0.5."""
    if rate > 0.5:
        return 1.0
    if rate < 0.5:
        return 0.0
    return 0.5


def paired_delta(
    paired: Sequence[PairedCell], *, resamples: int = 2000, seed: int = 0
) -> PairedStat:
    rates = cell_rates(paired)
    if not rates:
        return PairedStat(
            delta=0.0,
            interval=Interval(0.0, 0.0, resamples=resamples, seed=seed),
            cell_agreement=0.0,
            cells=0,
        )
    agree = sum(
        1 for real, world in rates.values() if _verdict(real) == _verdict(world)
    )
    return PairedStat(
        delta=delta_value(paired),
        interval=bootstrap_inputs(paired, delta_value, resamples=resamples, seed=seed),
        cell_agreement=agree / len(rates),
        cells=len(rates),
    )


# ---- per-configuration scores ----


@dataclass(frozen=True)
class ConfigScore:
    configuration: str
    system: System
    half: Half | None
    episodes: int
    valid: int
    invalid: int
    invalid_by_reason: dict[str, int]
    skipped: int
    pass_rate: float | None
    se: float | None
    predicates_rate: float | None
    collateral_rate: float | None
    mean_steps: float | None
    usable: bool


def config_scores(
    cells: Sequence[Cell],
    paired: Sequence[PairedCell],
    *,
    min_valid: int = 40,
    by_half: bool = False,
    score_names: tuple[str, str] = DEFAULT_SCORE_NAMES,
) -> list[ConfigScore]:
    kept = {cell.pair_key for cell in paired}
    grouped: dict[tuple[str, System, Half | None], list[Cell]] = {}
    for cell in cells:
        key = (cell.configuration, cell.system, cell.half if by_half else None)
        grouped.setdefault(key, []).append(cell)

    out: list[ConfigScore] = []
    for key in sorted(grouped, key=lambda k: (k[0], k[1], k[2] or "")):
        configuration, system, half = key
        group = grouped[key]
        valid_cells = [cell for cell in group if cell.pair_key in kept]
        invalid_by_reason: dict[str, int] = {}
        for cell in group:
            if cell.invalid is not None:
                invalid_by_reason[cell.invalid] = (
                    invalid_by_reason.get(cell.invalid, 0) + 1
                )
        passes = [cell for cell in valid_cells if cell.passed]
        rate = len(passes) / len(valid_cells) if valid_cells else None
        steps = [cell.steps for cell in valid_cells if cell.steps is not None]
        out.append(
            ConfigScore(
                configuration=configuration,
                system=system,
                half=half,
                episodes=len(group),
                valid=len(valid_cells),
                invalid=sum(1 for cell in group if cell.invalid is not None),
                invalid_by_reason=invalid_by_reason,
                skipped=sum(1 for cell in group if cell.skipped),
                pass_rate=rate,
                se=(
                    math.sqrt(rate * (1 - rate) / len(valid_cells))
                    if rate is not None and valid_cells
                    else None
                ),
                predicates_rate=_score_rate(valid_cells, score_names[0]),
                collateral_rate=_score_rate(valid_cells, score_names[1]),
                mean_steps=sum(steps) / len(steps) if steps else None,
                usable=len(valid_cells) >= min_valid,
            )
        )
    return out


def _score_rate(cells: Sequence[Cell], name: str) -> float | None:
    values = [
        cell.scores[name] for cell in cells if cell.scores and name in cell.scores
    ]
    if not values:
        return None
    return sum(1 for value in values if value >= 0.5) / len(values)


# ---- ranks ----


def average_ranks(values: Sequence[float]) -> list[float]:
    """Ranks with 1 as the best, a tied block taking the mean of the positions it spans."""
    order = sorted(range(len(values)), key=lambda i: -values[i])
    ranks = [0.0] * len(values)
    position = 0
    while position < len(order):
        end = position
        while (
            end + 1 < len(order) and values[order[end + 1]] == values[order[position]]
        ):
            end += 1
        mean_rank = (position + end) / 2.0 + 1.0
        for index in range(position, end + 1):
            ranks[order[index]] = mean_rank
        position = end + 1
    return ranks


def spearman(x: Sequence[float], y: Sequence[float]) -> float | None:
    """Pearson's correlation on average ranks, which handles ties; None when either side
    has no rank variance at all (every configuration tied)."""
    if len(x) != len(y) or len(x) < 2:
        return None
    rx = average_ranks(x)
    ry = average_ranks(y)
    mx = sum(rx) / len(rx)
    my = sum(ry) / len(ry)
    sx = sum((value - mx) ** 2 for value in rx)
    sy = sum((value - my) ** 2 for value in ry)
    if sx == 0 or sy == 0:
        return None
    covariance = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    return covariance / math.sqrt(sx * sy)


RankOutcome = Literal["passed", "failed", "inconclusive"]


@dataclass(frozen=True)
class RankStat:
    rho: float | None
    interval: Interval | None
    real_means: dict[str, float]
    world_means: dict[str, float]
    real_ranks: dict[str, float]
    world_ranks: dict[str, float]
    ties: dict[System, list[tuple[str, str]]]
    indistinguishable: list[tuple[str, str, Interval]]
    outcome: RankOutcome
    reason: str | None


def _means(paired: Sequence[PairedCell]) -> tuple[dict[str, float], dict[str, float]]:
    grouped: dict[str, list[PairedCell]] = {}
    for cell in paired:
        grouped.setdefault(cell.configuration, []).append(cell)
    real = {
        name: sum(1 for c in group if c.real) / len(group)
        for name, group in grouped.items()
    }
    world = {
        name: sum(1 for c in group if c.world) / len(group)
        for name, group in grouped.items()
    }
    return real, world


def _exact_ties(means: Mapping[str, float]) -> list[tuple[str, str]]:
    names = sorted(means)
    return [
        (a, b)
        for index, a in enumerate(names)
        for b in names[index + 1 :]
        if means[a] == means[b]
    ]


def _difference_interval(
    paired: Sequence[PairedCell],
    a: str,
    b: str,
    system: System,
    *,
    resamples: int,
    seed: int,
) -> Interval:
    def statistic(sample: Sequence[PairedCell]) -> float:
        left = [c for c in sample if c.configuration == a]
        right = [c for c in sample if c.configuration == b]
        if not left or not right:
            return float("nan")
        pick = (lambda c: c.real) if system == "real" else (lambda c: c.world)
        return sum(1 for c in left if pick(c)) / len(left) - sum(
            1 for c in right if pick(c)
        ) / len(right)

    return bootstrap_inputs(paired, statistic, resamples=resamples, seed=seed)


def rank_stat(
    paired: Sequence[PairedCell],
    *,
    spearman_min: float,
    resamples: int = 2000,
    seed: int = 0,
) -> RankStat:
    real_means, world_means = _means(paired)
    names = sorted(real_means)
    empty = RankStat(
        rho=None,
        interval=None,
        real_means=real_means,
        world_means=world_means,
        real_ranks={},
        world_ranks={},
        ties={"real": [], "world": []},
        indistinguishable=[],
        outcome="inconclusive",
        reason=None,
    )
    if len(names) < 2:
        return replace(empty, reason="fewer than two configurations")

    real_values = [real_means[name] for name in names]
    world_values = [world_means[name] for name in names]
    real_ranks = dict(zip(names, average_ranks(real_values)))
    world_ranks = dict(zip(names, average_ranks(world_values)))
    ties: dict[System, list[tuple[str, str]]] = {
        "real": _exact_ties(real_means),
        "world": _exact_ties(world_means),
    }
    band = [
        (a, b, interval)
        for index, a in enumerate(names)
        for b in names[index + 1 :]
        for interval in [
            _difference_interval(paired, a, b, "real", resamples=resamples, seed=seed)
        ]
        if interval.spans(0.0)
    ]

    rho = spearman(real_values, world_values)
    if rho is None:
        real_flat = len(set(real_values)) == 1
        return RankStat(
            rho=None,
            interval=None,
            real_means=real_means,
            world_means=world_means,
            real_ranks=real_ranks,
            world_ranks=world_ranks,
            ties=ties,
            indistinguishable=band,
            outcome="inconclusive" if real_flat else "failed",
            reason=(
                "inputs do not separate configurations"
                if real_flat
                else "the world does not separate configurations"
            ),
        )

    def statistic(sample: Sequence[PairedCell]) -> float:
        sampled_real, sampled_world = _means(sample)
        shared = sorted(set(sampled_real) & set(sampled_world))
        value = spearman(
            [sampled_real[name] for name in shared],
            [sampled_world[name] for name in shared],
        )
        return float("nan") if value is None else value

    return RankStat(
        rho=rho,
        interval=bootstrap_inputs(paired, statistic, resamples=resamples, seed=seed),
        real_means=real_means,
        world_means=world_means,
        real_ranks=real_ranks,
        world_ranks=world_ranks,
        ties=ties,
        indistinguishable=band,
        outcome="passed" if rho >= spearman_min else "failed",
        reason=None,
    )


PairOrder = Literal["a>f", "f>a", "tie"]


@dataclass(frozen=True)
class NearNeighbour:
    a: str
    f: str
    real_order: PairOrder
    world_order: PairOrder
    reproduced: bool


def near_neighbour(
    paired: Sequence[PairedCell],
    a: str = "A",
    f: str = "F",
    *,
    resamples: int = 2000,
    seed: int = 0,
) -> NearNeighbour:
    """Whether the two systems put the near-neighbour pair in the same order. Reported,
    never gated: it is the sensitivity question, and one pair cannot settle it."""

    def order(system: System) -> PairOrder:
        interval = _difference_interval(
            paired, a, f, system, resamples=resamples, seed=seed
        )
        if interval.spans(0.0):
            return "tie"
        return "a>f" if interval.low > 0 else "f>a"

    real_order = order("real")
    world_order = order("world")
    return NearNeighbour(
        a=a,
        f=f,
        real_order=real_order,
        world_order=world_order,
        reproduced=real_order == world_order,
    )


# ---- decisions ----


@dataclass(frozen=True)
class DecisionStat:
    measurable: bool
    world_conditional: float | None
    control_conditional: float | None
    difference: float | None
    interval: Interval | None
    world_unconditional: float | None
    control_unconditional: float | None
    divergent_decisions: int
    control_decisions: int
    per_configuration: dict[str, dict[Arm, float | None]] = field(default_factory=dict)


def agreement(
    records: Sequence[DecisionRecord],
    arm: Arm,
    *,
    prefix: PrefixKind | None = None,
) -> float | None:
    chosen = [
        record
        for record in records
        if record.arm == arm
        and record.error is None
        and (prefix is None or record.prefix == prefix)
    ]
    if not chosen:
        return None
    return sum(1 for record in chosen if record.agree) / len(chosen)


def _paired_records(
    records: Sequence[DecisionRecord],
) -> list[tuple[DecisionRecord, DecisionRecord]]:
    """(world, control) for every decision both arms answered without error."""
    by_key: dict[tuple[str, int], dict[Arm, DecisionRecord]] = {}
    for record in records:
        if record.error is not None:
            continue
        by_key.setdefault((record.run_id, record.decision_index), {})[record.arm] = (
            record
        )
    return [
        (arms["world"], arms["control"])
        for _, arms in sorted(by_key.items())
        if "world" in arms and "control" in arms
    ]


def _difference(pairs: Sequence[tuple[DecisionRecord, DecisionRecord]]) -> float:
    if not pairs:
        return float("nan")
    return sum(
        (1 if world.agree else 0) - (1 if control.agree else 0)
        for world, control in pairs
    ) / len(pairs)


def decision_stat(
    records: Sequence[DecisionRecord], *, resamples: int = 2000, seed: int = 0
) -> DecisionStat:
    """Conditional agreement on the divergent-prefix decisions, against the control arm.

    The comparison is paired by (run_id, decision_index) and one-sided: a world arm that
    agrees at least as often as the control arm cannot fail. An empty divergent set is not
    measurable, and is never reported as passed."""
    pairs = _paired_records(records)
    divergent = [p for p in pairs if p[0].prefix == "divergent"]
    control_prefix = [p for p in pairs if p[0].prefix == "control"]

    per_configuration: dict[str, dict[Arm, float | None]] = {}
    configurations: set[str] = {record.configuration for record in records}
    for configuration in sorted(configurations):
        subset = [r for r in records if r.configuration == configuration]
        arms: dict[Arm, float | None] = {
            "world": agreement(subset, "world"),
            "control": agreement(subset, "control"),
        }
        per_configuration[configuration] = arms

    if not divergent:
        return DecisionStat(
            measurable=False,
            world_conditional=None,
            control_conditional=None,
            difference=None,
            interval=None,
            world_unconditional=agreement(records, "world"),
            control_unconditional=agreement(records, "control"),
            divergent_decisions=0,
            control_decisions=len(control_prefix),
            per_configuration=per_configuration,
        )

    flat = [record for pair in divergent for record in pair]

    def statistic(sample: Sequence[DecisionRecord]) -> float:
        return _difference(_paired_records(sample))

    world_conditional = sum(1 for w, _ in divergent if w.agree) / len(divergent)
    control_conditional = sum(1 for _, c in divergent if c.agree) / len(divergent)
    return DecisionStat(
        measurable=True,
        world_conditional=world_conditional,
        control_conditional=control_conditional,
        difference=world_conditional - control_conditional,
        interval=bootstrap_episodes(flat, statistic, resamples=resamples, seed=seed),
        world_unconditional=agreement(records, "world"),
        control_unconditional=agreement(records, "control"),
        divergent_decisions=len(divergent),
        control_decisions=len(control_prefix),
        per_configuration=per_configuration,
    )


# ---- sanity ----


@dataclass(frozen=True)
class SanityCounts:
    invalid: dict[System, dict[str, int]]
    dropped_pairs: int
    world_gaps: int
    settle_errors: int
    unscored: int = 0
    """Episodes that ran, came back with no score and were not flagged invalid. Their
    pairs drop as `judge_failure` — the closest reason the taxonomy has — but no judge
    traceback was written for them, so the report says so rather than sending a reader
    looking for one."""


def sanity_counts(
    cells: Sequence[Cell], dropped: Sequence[DroppedPair]
) -> SanityCounts:
    invalid: dict[System, dict[str, int]] = {"real": {}, "world": {}}
    for cell in cells:
        lane = invalid.setdefault(cell.system, {})
        lane.setdefault(cell.configuration, 0)
        if cell.invalid is not None:
            lane[cell.configuration] += 1
    return SanityCounts(
        invalid=invalid,
        dropped_pairs=len(dropped),
        world_gaps=sum(1 for cell in cells if cell.invalid == "world_gap"),
        settle_errors=sum(1 for cell in cells if cell.invalid == "settle_error"),
        unscored=sum(1 for cell in cells if cell.skipped),
    )


# ---- gates ----


@dataclass(frozen=True)
class GateThresholds:
    paired_delta_max: float = 0.10
    paired_upper_max: float = 0.15
    spearman_min: float = 0.8
    decision_lower_min: float = -0.05
    min_valid_per_config: int = 40
    episodes_per_config: int = 60
    faults_min_detected: int = 4


GateName = Literal["replay", "paired", "rank", "decision", "faults"]
GateOutcome = Literal["passed", "failed", "inconclusive", "not_measurable", "skipped"]


@dataclass(frozen=True)
class Gate:
    name: GateName
    value: float | None
    threshold: float | None
    passed: bool | None
    outcome: GateOutcome
    interval: Interval | None
    inputs: dict[str, JsonValue]
    reason: str | None


def _skipped(name: GateName, reason: str) -> Gate:
    return Gate(
        name=name,
        value=None,
        threshold=None,
        passed=None,
        outcome="skipped",
        interval=None,
        inputs={},
        reason=reason,
    )


def _inconclusive(
    name: GateName, reason: str, inputs: dict[str, JsonValue] | None = None
) -> Gate:
    return Gate(
        name=name,
        value=None,
        threshold=None,
        passed=None,
        outcome="inconclusive",
        interval=None,
        inputs=inputs or {},
        reason=reason,
    )


def _unusable(
    scores: Sequence[ConfigScore] | None, thresholds: GateThresholds
) -> str | None:
    """Why the paired and rank gates cannot be believed, or None when they can.

    `None` scores means the usability of the configurations was never checked, which is a
    reason for `inconclusive` and not a reason to proceed: silently skipping the check is
    the same failure as a gate passing on no data.

    Pass the *combined* scores (`by_half=False`). A per-half list counts at most half the
    episodes per configuration, so every configuration would read as unusable."""
    if scores is None:
        return "configuration usability was not checked: no per-configuration scores"
    for score in scores:
        if not score.usable:
            return (
                f"configuration {score.configuration} unusable: "
                f"{score.valid} of {thresholds.episodes_per_config} valid"
            )
    return None


def _replay_gate(
    mismatches: Sequence[Mismatch] | None, replay_steps: int | None
) -> Gate:
    if mismatches is None:
        return _skipped("replay", "step did not run")
    if not replay_steps:
        # None (never counted) and 0 (nothing replayed) are the same answer here: the
        # gate has no evidence that any step was compared, and a clean mismatch list
        # proves nothing on its own.
        return _inconclusive("replay", "no replayed steps", {"steps": replay_steps})
    classes = undeclared_classes(mismatches)
    kinds: dict[str, int] = {}
    for mismatch in mismatches:
        kinds[mismatch.kind] = kinds.get(mismatch.kind, 0) + 1
    inputs: dict[str, JsonValue] = {
        "undeclared_classes": [list(item) for item in classes],
        "steps": replay_steps,
        "ok": replay_steps - len(mismatches),
    }
    inputs.update({kind: count for kind, count in sorted(kinds.items())})
    return Gate(
        name="replay",
        value=float(len(classes)),
        threshold=0.0,
        passed=not classes,
        outcome="passed" if not classes else "failed",
        interval=None,
        inputs=inputs,
        reason=None,
    )


def _paired_gate(
    paired: Sequence[PairedCell] | None,
    scores: Sequence[ConfigScore] | None,
    thresholds: GateThresholds,
    *,
    resamples: int,
    seed: int,
) -> tuple[Gate, PairedStat | None]:
    if paired is None:
        return _skipped("paired", "step did not run"), None
    if not paired:
        return _inconclusive("paired", "no kept pairs"), None
    unusable = _unusable(scores, thresholds)
    stat = paired_delta(paired, resamples=resamples, seed=seed)
    if unusable is not None:
        return _inconclusive("paired", unusable, {"cells": stat.cells}), stat
    passed = (
        stat.delta <= thresholds.paired_delta_max
        and stat.interval.high <= thresholds.paired_upper_max
    )
    return (
        Gate(
            name="paired",
            value=stat.delta,
            threshold=thresholds.paired_delta_max,
            passed=passed,
            outcome="passed" if passed else "failed",
            interval=stat.interval,
            inputs={
                "upper_max": thresholds.paired_upper_max,
                "cell_agreement": stat.cell_agreement,
                "cells": stat.cells,
                "cell_rates": {
                    f"{configuration}:{input_no}": [real, world]
                    for (configuration, input_no), (real, world) in sorted(
                        cell_rates(paired).items()
                    )
                },
            },
            reason=None,
        ),
        stat,
    )


def _rank_gate(
    paired: Sequence[PairedCell] | None,
    scores: Sequence[ConfigScore] | None,
    thresholds: GateThresholds,
    *,
    resamples: int,
    seed: int,
) -> tuple[Gate, RankStat | None]:
    if paired is None:
        return _skipped("rank", "step did not run"), None
    if not paired:
        return _inconclusive("rank", "no kept pairs"), None
    unusable = _unusable(scores, thresholds)
    stat = rank_stat(
        paired, spearman_min=thresholds.spearman_min, resamples=resamples, seed=seed
    )
    if unusable is not None:
        return _inconclusive("rank", unusable), stat
    inputs: dict[str, JsonValue] = {
        "real_means": stat.real_means,
        "world_means": stat.world_means,
        "real_ranks": stat.real_ranks,
        "world_ranks": stat.world_ranks,
        "n": len(stat.real_means),
        "discreteness": (
            "rho at n=6 takes 26 distinct values; the interval is wide by construction"
        ),
    }
    if stat.outcome == "inconclusive":
        return (
            Gate(
                name="rank",
                value=stat.rho,
                threshold=thresholds.spearman_min,
                passed=None,
                outcome="inconclusive",
                interval=stat.interval,
                inputs=inputs,
                reason=stat.reason,
            ),
            stat,
        )
    return (
        Gate(
            name="rank",
            value=stat.rho,
            threshold=thresholds.spearman_min,
            passed=stat.outcome == "passed",
            outcome=stat.outcome,
            interval=stat.interval,
            inputs=inputs,
            reason=stat.reason,
        ),
        stat,
    )


def _decision_gate(
    decisions: Sequence[DecisionRecord] | None,
    thresholds: GateThresholds,
    *,
    resamples: int,
    seed: int,
) -> tuple[Gate, DecisionStat | None]:
    if decisions is None:
        return _skipped("decision", "step did not run"), None
    if not decisions:
        return _inconclusive("decision", "no decisions replayed"), None
    stat = decision_stat(decisions, resamples=resamples, seed=seed)
    inputs: dict[str, JsonValue] = {
        "world_conditional": stat.world_conditional,
        "control_conditional": stat.control_conditional,
        "world_unconditional": stat.world_unconditional,
        "control_unconditional": stat.control_unconditional,
        "divergent_decisions": stat.divergent_decisions,
        "control_decisions": stat.control_decisions,
    }
    if not stat.measurable:
        return (
            Gate(
                name="decision",
                value=None,
                threshold=thresholds.decision_lower_min,
                passed=None,
                outcome="not_measurable",
                interval=None,
                inputs=inputs,
                reason="no divergences",
            ),
            stat,
        )
    interval = stat.interval
    passed = interval is not None and interval.low >= thresholds.decision_lower_min
    return (
        Gate(
            name="decision",
            value=stat.difference,
            threshold=thresholds.decision_lower_min,
            passed=passed,
            outcome="passed" if passed else "failed",
            interval=interval,
            inputs=inputs,
            reason=None,
        ),
        stat,
    )


@dataclass(frozen=True)
class GateResults:
    """The four gates and the statistics they were computed from.

    The statistics come back so the report publishes the same interval the gate was
    judged on. Recomputing them beside the gate would give a second interval from a
    second bootstrap — at a different seed, if the run used `--bootstrap-seed` — and a
    report that disagrees with its own gate table is worse than no interval at all."""

    gates: list[Gate]
    paired: PairedStat | None
    rank: RankStat | None
    decision: DecisionStat | None


def evaluate_gates_with_stats(
    *,
    mismatches: Sequence[Mismatch] | None,
    paired: Sequence[PairedCell] | None,
    scores: Sequence[ConfigScore] | None,
    decisions: Sequence[DecisionRecord] | None,
    thresholds: GateThresholds,
    replay_steps: int | None,
    resamples: int = 2000,
    seed: int = 0,
) -> GateResults:
    """The four non-fault gates, with the statistics behind them.

    A None argument means the step did not run and gives a `skipped` gate; an empty one
    means the step ran on nothing and gives `inconclusive`. `scores` is the *combined*
    per-configuration list — None there is "usability unchecked", not "usable"."""
    paired_gate, paired_stat = _paired_gate(
        paired, scores, thresholds, resamples=resamples, seed=seed
    )
    rank_gate, rank = _rank_gate(
        paired, scores, thresholds, resamples=resamples, seed=seed
    )
    decision_gate, decision = _decision_gate(
        decisions, thresholds, resamples=resamples, seed=seed
    )
    return GateResults(
        gates=[
            _replay_gate(mismatches, replay_steps),
            paired_gate,
            rank_gate,
            decision_gate,
        ],
        paired=paired_stat,
        rank=rank,
        decision=decision,
    )


def evaluate_gates(
    *,
    mismatches: Sequence[Mismatch] | None,
    paired: Sequence[PairedCell] | None,
    scores: Sequence[ConfigScore] | None,
    decisions: Sequence[DecisionRecord] | None,
    thresholds: GateThresholds,
    replay_steps: int | None,
    resamples: int = 2000,
    seed: int = 0,
) -> list[Gate]:
    """The four non-fault gates. A None argument means the step did not run."""
    return evaluate_gates_with_stats(
        mismatches=mismatches,
        paired=paired,
        scores=scores,
        decisions=decisions,
        thresholds=thresholds,
        replay_steps=replay_steps,
        resamples=resamples,
        seed=seed,
    ).gates


def fault_thresholds(
    base: GateThresholds, *, episodes_per_config: int
) -> GateThresholds:
    """`base` rescaled to a smaller run, keeping the same usable fraction.

    A fault run is deliberately shorter than the clean run, so judging it against the
    clean run's episode count would make every configuration unusable and every gate
    inconclusive — and a gate that cannot move cannot detect anything."""
    if base.episodes_per_config <= 0:
        raise ValueError("episodes_per_config must be positive")
    fraction = base.min_valid_per_config / base.episodes_per_config
    return replace(
        base,
        episodes_per_config=episodes_per_config,
        min_valid_per_config=math.ceil(fraction * episodes_per_config),
    )


def fault_gate(
    results: "Sequence[FaultResult] | None", thresholds: GateThresholds
) -> Gate:
    """Detection across the seeded faults: at least `faults_min_detected` detected, and no
    fault left inconclusive. A fault that never triggered says nothing about detection, so
    it cannot be counted either way — it is a missing input, and it blocks the gate."""
    if results is None:
        return _skipped("faults", "step did not run")
    if not results:
        return _inconclusive("faults", "no faults run")
    detected = [result.fault for result in results if result.detected]
    inconclusive = [result.fault for result in results if result.inconclusive]
    undetected = [
        result.fault
        for result in results
        if not result.detected and not result.inconclusive
    ]
    passed = len(detected) >= thresholds.faults_min_detected and not inconclusive
    return Gate(
        name="faults",
        value=float(len(detected)),
        threshold=float(thresholds.faults_min_detected),
        passed=passed,
        outcome="passed" if passed else "failed",
        interval=None,
        inputs={
            "detected": detected,
            "undetected": undetected,
            "inconclusive": inconclusive,
        },
        reason=(
            (
                "inconclusive faults (never triggered, or the comparison could not be "
                "made): "
                + ", ".join(
                    f"{result.fault} ({result.reason or 'no reason given'})"
                    for result in results
                    if result.inconclusive
                )
            )
            if inconclusive
            else None
        ),
    )


def moved_gates(clean: Sequence[Gate], faulted: Sequence[Gate]) -> list[str]:
    """Gate names that passed clean and fail under the fault: the detection signal."""
    faulted_by_name = {gate.name: gate for gate in faulted}
    return [
        gate.name
        for gate in clean
        if gate.passed is True
        and faulted_by_name.get(gate.name) is not None
        and faulted_by_name[gate.name].passed is False
    ]


def moved_beyond_interval(clean: PairedStat, faulted: PairedStat) -> bool:
    """The faulted paired delta sits outside the clean run's bootstrap interval."""
    return not clean.interval.spans(faulted.delta)
