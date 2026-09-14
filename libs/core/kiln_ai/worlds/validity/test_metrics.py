from __future__ import annotations

import math

import pytest

from .conftest import cell, decision_record, episode, paired_cell, user_message
from .faults import FaultResult
from .metrics import (
    Gate,
    GateThresholds,
    Interval,
    _paired_records,
    agreement,
    average_ranks,
    bootstrap_episodes,
    bootstrap_inputs,
    cell_rates,
    cells,
    config_scores,
    decision_stat,
    delta_value,
    evaluate_gates,
    evaluate_gates_with_stats,
    fault_gate,
    fault_thresholds,
    moved_beyond_interval,
    moved_gates,
    near_neighbour,
    pair_cells,
    paired_delta,
    rank_stat,
    sanity_counts,
    spearman,
)

PASS = {"predicates_pass": 1.0, "collateral_pass": 1.0}
FAIL = {"predicates_pass": 0.0, "collateral_pass": 1.0}


def recorded(system: str, **kwargs):
    return episode(user_message(), system=system, **kwargs)


# ---- cells and pairing ----


def test_cells_fill_missing_episodes_as_reset_anomaly():
    laid_out = cells(
        [recorded("real", scores=PASS)],
        expected=[("A", 1, 1)],
        half_for=lambda n: "tuning",
    )
    by_system = {c.system: c for c in laid_out}
    assert by_system["real"].passed is True
    assert by_system["real"].invalid is None
    assert by_system["world"].run_id is None
    assert by_system["world"].invalid == "reset_anomaly"
    assert by_system["world"].passed is None


def test_cells_read_pass_as_the_conjunction_of_the_scores():
    laid_out = cells(
        [recorded("real", scores=FAIL), recorded("world", scores=PASS)],
        expected=[("A", 1, 1)],
    )
    assert {c.system: c.passed for c in laid_out} == {"real": False, "world": True}


def test_pair_cells_drops_pair_on_either_invalid():
    kept, dropped = pair_cells(
        [
            cell("A", 1, 1, "real"),
            cell("A", 1, 1, "world"),
            cell("A", 2, 1, "real", invalid="upstream_error"),
            cell("A", 2, 1, "world"),
            cell("A", 3, 1, "real"),
            cell("A", 3, 1, "world", invalid="world_gap"),
            cell("A", 4, 1, "real", passed=None),
            cell("A", 4, 1, "world"),
        ]
    )
    assert [k.pair_key for k in kept] == [("A", 1, 1)]
    assert [(d.key, d.reason, d.lane) for d in dropped] == [
        (("A", 2, 1), "upstream_error", "real"),
        (("A", 3, 1), "world_gap", "world"),
        (("A", 4, 1), "judge_failure", "real"),
    ]


def test_pair_cells_drops_a_pair_with_a_missing_side():
    kept, dropped = pair_cells([cell("A", 1, 1, "real")])
    assert kept == []
    assert dropped[0].reason == "reset_anomaly" and dropped[0].lane == "world"


# ---- the paired statistic ----


def test_paired_delta_hand_computed():
    paired = [
        paired_cell("A", 1, 1, real=True, world=True),
        paired_cell("A", 1, 2, real=True, world=False),
        paired_cell("A", 2, 1, real=False, world=False),
        paired_cell("A", 2, 2, real=False, world=False),
    ]
    assert cell_rates(paired) == {("A", 1): (1.0, 0.5), ("A", 2): (0.0, 0.0)}
    stat = paired_delta(paired)
    assert stat.delta == pytest.approx(0.25)
    assert stat.cells == 2
    assert stat.cell_agreement == pytest.approx(0.5)


def test_cell_agreement_majority_rule():
    """A 0.5 cell is undecided: it agrees with another 0.5 and with nothing else."""
    both_undecided = [
        paired_cell("A", 1, 1, real=True, world=False),
        paired_cell("A", 1, 2, real=False, world=True),
    ]
    assert paired_delta(both_undecided).cell_agreement == 1.0

    one_undecided = [
        paired_cell("A", 1, 1, real=True, world=True),
        paired_cell("A", 1, 2, real=False, world=True),
    ]
    assert paired_delta(one_undecided).cell_agreement == 0.0


def test_paired_delta_on_no_pairs_is_empty_not_an_error():
    stat = paired_delta([])
    assert stat.cells == 0 and stat.delta == 0.0


def test_bootstrap_inputs_resamples_by_input_and_is_seeded():
    paired = [paired_cell("A", n, 1, real=True, world=n > 5) for n in range(1, 11)]
    first = bootstrap_inputs(paired, delta_value, resamples=200, seed=3)
    again = bootstrap_inputs(paired, delta_value, resamples=200, seed=3)
    assert (first.low, first.high) == (again.low, again.high)
    assert 0.0 <= first.low <= 0.5 <= first.high <= 1.0
    assert first.resamples == 200 and first.seed == 3


def test_bootstrap_inputs_relabels_each_draw_into_its_own_group():
    """A cluster drawn twice must reach the statistic as two groups, not one.

    `delta_value` re-groups its sample by (configuration, input), so without the relabel a
    duplicate draw collapses and the resample is a ~63% subset of the clusters — an interval
    too narrow, in the direction that makes the one-sided paired gate easier to pass."""
    paired = [paired_cell("A", n, 1, real=True, world=False) for n in range(1, 11)]
    seen: list[int] = []

    def count_groups(sample):
        seen.append(len({(c.configuration, c.input_no) for c in sample}))
        return 0.0

    bootstrap_inputs(paired, count_groups, resamples=50, seed=0)
    assert seen and all(n == 10 for n in seen), f"collapsed draws: {sorted(set(seen))}"


def test_bootstrap_episodes_relabels_each_draw_into_its_own_pair():
    """`_paired_records` keys a dict by (run_id, decision_index), so an episode drawn twice
    would overwrite itself and vanish from the resample."""
    records = [
        decision_record(f"run-{n}", 0, arm, prefix="divergent", agree=True)
        for n in range(10)
        for arm in ("world", "control")
    ]
    seen: list[int] = []

    def count_pairs(sample):
        seen.append(len(_paired_records(sample)))
        return 0.0

    bootstrap_episodes(records, count_pairs, resamples=50, seed=0)
    assert seen and all(n == 10 for n in seen), f"collapsed draws: {sorted(set(seen))}"


# ---- per-configuration scores ----


def test_config_scores_usable_threshold_and_se():
    laid_out = [
        cell("A", n, 1, system, passed=(n != 3), scores=PASS if n != 3 else FAIL)
        for n in (1, 2, 3)
        for system in ("real", "world")
    ]
    paired, _ = pair_cells(laid_out)
    scores = config_scores(laid_out, paired, min_valid=3)
    real = next(s for s in scores if s.system == "real")
    assert real.episodes == 3 and real.valid == 3 and real.invalid == 0
    assert real.pass_rate == pytest.approx(2 / 3)
    assert real.se == pytest.approx(math.sqrt((2 / 3) * (1 / 3) / 3))
    assert real.predicates_rate == pytest.approx(2 / 3)
    assert real.collateral_rate == pytest.approx(1.0)
    assert real.mean_steps == pytest.approx(3.0)
    assert real.usable is True
    assert real.half is None

    assert config_scores(laid_out, paired, min_valid=4)[0].usable is False


def test_config_scores_counts_invalid_by_reason_and_skipped():
    laid_out = [
        cell("A", 1, 1, "real", invalid="upstream_error", passed=None),
        cell("A", 1, 1, "world"),
        cell("A", 2, 1, "real", invalid="upstream_error", passed=None),
        cell("A", 2, 1, "world"),
        cell("A", 3, 1, "real", passed=None),
        cell("A", 3, 1, "world"),
    ]
    paired, _ = pair_cells(laid_out)
    real = next(s for s in config_scores(laid_out, paired) if s.system == "real")
    assert real.invalid == 2
    assert real.invalid_by_reason == {"upstream_error": 2}
    assert real.skipped == 1
    assert real.valid == 0
    assert real.pass_rate is None and real.se is None


def test_config_scores_by_half():
    laid_out = [
        cell("A", n, 1, system, half="tuning" if n <= 2 else "sealed")
        for n in (1, 2, 3, 4)
        for system in ("real", "world")
    ]
    paired, _ = pair_cells(laid_out)
    by_half = config_scores(laid_out, paired, min_valid=1, by_half=True)
    assert {(s.configuration, s.system, s.half) for s in by_half} == {
        ("A", "real", "tuning"),
        ("A", "real", "sealed"),
        ("A", "world", "tuning"),
        ("A", "world", "sealed"),
    }
    assert all(s.episodes == 2 for s in by_half)


# ---- ranks ----


def test_average_ranks_ties_get_mean_rank():
    assert average_ranks([0.9, 0.8, 0.8, 0.5]) == [1.0, 2.5, 2.5, 4.0]
    assert average_ranks([0.5, 0.5, 0.5]) == [2.0, 2.0, 2.0]


def test_spearman_no_ties_matches_closed_form():
    assert spearman([3.0, 2.0, 1.0], [1.0, 2.0, 3.0]) == pytest.approx(-1.0)
    assert spearman([3.0, 2.0, 1.0], [3.0, 2.0, 1.0]) == pytest.approx(1.0)


def test_spearman_with_ties_known_value():
    # ranks are [1, 2.5, 2.5] and [1, 2, 3]; Pearson on those is 1.5 / sqrt(1.5 * 2)
    assert spearman([1.0, 0.5, 0.5], [1.0, 0.5, 0.0]) == pytest.approx(
        1.5 / math.sqrt(3.0)
    )


def test_spearman_zero_variance_is_none():
    assert spearman([0.5, 0.5, 0.5], [1.0, 0.5, 0.0]) is None
    assert spearman([1.0], [1.0]) is None


def separated_pairs(real_rate: dict[str, int], world_rate: dict[str, int]):
    """Ten inputs per configuration; `rate` is how many of the ten pass."""
    return [
        paired_cell(
            name,
            n,
            1,
            real=n <= real_rate[name],
            world=n <= world_rate[name],
        )
        for name in real_rate
        for n in range(1, 11)
    ]


def test_rank_stat_orders_configurations_the_same_way():
    paired = separated_pairs({"A": 9, "B": 5, "C": 1}, {"A": 8, "B": 6, "C": 2})
    stat = rank_stat(paired, spearman_min=0.8, resamples=200)
    assert stat.rho == pytest.approx(1.0)
    assert stat.outcome == "passed"
    assert stat.real_ranks == {"A": 1.0, "B": 2.0, "C": 3.0}
    assert stat.interval is not None


def test_rank_stat_real_zero_variance_inconclusive_world_failed():
    flat_real = separated_pairs({"A": 5, "B": 5, "C": 5}, {"A": 9, "B": 5, "C": 1})
    inconclusive = rank_stat(flat_real, spearman_min=0.8, resamples=50)
    assert inconclusive.outcome == "inconclusive"
    assert inconclusive.reason == "inputs do not separate configurations"

    flat_world = separated_pairs({"A": 9, "B": 5, "C": 1}, {"A": 5, "B": 5, "C": 5})
    failed = rank_stat(flat_world, spearman_min=0.8, resamples=50)
    assert failed.outcome == "failed"
    assert failed.reason == "the world does not separate configurations"


def test_rank_stat_tie_band_from_difference_interval():
    paired = separated_pairs({"A": 5, "B": 5, "C": 1}, {"A": 5, "B": 5, "C": 1})
    stat = rank_stat(paired, spearman_min=0.8, resamples=200)
    band = {(a, b) for a, b, _ in stat.indistinguishable}
    assert ("A", "B") in band
    assert ("A", "C") not in band
    assert ("A", "B") in stat.ties["real"]


def test_rank_stat_needs_two_configurations():
    stat = rank_stat(
        separated_pairs({"A": 5}, {"A": 5}), spearman_min=0.8, resamples=10
    )
    assert stat.outcome == "inconclusive"
    assert stat.reason == "fewer than two configurations"


def test_near_neighbour_order_reproduced():
    paired = separated_pairs({"A": 10, "F": 0}, {"A": 10, "F": 0})
    near = near_neighbour(paired, resamples=100)
    assert (near.real_order, near.world_order, near.reproduced) == ("a>f", "a>f", True)

    flipped = separated_pairs({"A": 10, "F": 0}, {"A": 0, "F": 10})
    assert near_neighbour(flipped, resamples=100).reproduced is False

    tied = separated_pairs({"A": 5, "F": 5}, {"A": 5, "F": 5})
    assert near_neighbour(tied, resamples=100).real_order == "tie"


# ---- decisions ----


def test_agreement_ignores_errored_records_and_filters_prefix():
    records = [
        decision_record("run-1", 0, "world", prefix="divergent", agree=True),
        decision_record("run-1", 1, "world", prefix="control", agree=False),
        decision_record(
            "run-1", 2, "world", prefix="divergent", agree=False, error="boom"
        ),
        decision_record("run-1", 3, "control", prefix="divergent", agree=True),
    ]
    assert agreement(records, "world") == pytest.approx(0.5)
    assert agreement(records, "world", prefix="divergent") == pytest.approx(1.0)
    assert agreement(records, "control") == pytest.approx(1.0)
    assert agreement([], "world") is None


def test_decision_stat_pairs_by_run_and_index():
    records = []
    for n in range(10):
        records.append(
            decision_record(f"run-{n}", 0, "world", prefix="divergent", agree=n > 1)
        )
        records.append(
            decision_record(f"run-{n}", 0, "control", prefix="divergent", agree=True)
        )
    stat = decision_stat(records)
    assert stat.measurable is True
    assert stat.divergent_decisions == 10
    assert stat.world_conditional == pytest.approx(0.8)
    assert stat.control_conditional == pytest.approx(1.0)
    assert stat.difference == pytest.approx(-0.2)
    assert stat.per_configuration["A"]["world"] == pytest.approx(0.8)


def test_decision_stat_needs_both_arms_error_free():
    records = [
        decision_record("run-1", 0, "world", prefix="divergent"),
        decision_record("run-1", 0, "control", prefix="divergent", error="boom"),
    ]
    assert decision_stat(records).measurable is False


def test_decision_stat_empty_divergent_not_measurable():
    records = [
        decision_record("run-1", 0, arm, prefix="control")
        for arm in ("world", "control")
    ]
    stat = decision_stat(records)
    assert stat.measurable is False
    assert stat.difference is None and stat.interval is None
    assert stat.control_decisions == 1
    assert stat.world_unconditional == pytest.approx(1.0)


# ---- sanity ----


def test_sanity_counts_per_lane_and_reason():
    laid_out = [
        cell("A", 1, 1, "real", invalid="upstream_error", passed=None),
        cell("A", 1, 1, "world", invalid="world_gap", passed=None),
        cell("B", 1, 1, "real"),
        cell("B", 1, 1, "world", invalid="settle_error", passed=None),
    ]
    _, dropped = pair_cells(laid_out)
    counts = sanity_counts(laid_out, dropped)
    assert counts.invalid == {"real": {"A": 1, "B": 0}, "world": {"A": 1, "B": 1}}
    assert counts.world_gaps == 1
    assert counts.settle_errors == 1
    assert counts.dropped_pairs == 2


# ---- gates ----


THRESHOLDS = GateThresholds()


def good_paired():
    return separated_pairs({"A": 9, "B": 5, "C": 1}, {"A": 9, "B": 5, "C": 1})


def good_scores(paired):
    laid_out = [
        cell(p.configuration, p.input_no, p.repeat, system, passed=True)
        for p in paired
        for system in ("real", "world")
    ]
    return config_scores(laid_out, paired, min_valid=1)


def test_gates_none_input_is_skipped_null():
    gates = evaluate_gates(
        mismatches=None,
        paired=None,
        scores=None,
        decisions=None,
        thresholds=THRESHOLDS,
        replay_steps=None,
    )
    assert [g.name for g in gates] == ["replay", "paired", "rank", "decision"]
    assert all(g.outcome == "skipped" for g in gates)
    assert all(g.value is None and g.passed is None for g in gates)


def test_gates_empty_input_is_inconclusive():
    gates = evaluate_gates(
        mismatches=[],
        paired=[],
        scores=[],
        decisions=[],
        thresholds=THRESHOLDS,
        replay_steps=0,
    )
    assert all(g.outcome == "inconclusive" for g in gates)
    assert all(g.reason for g in gates)
    assert all(g.passed is None for g in gates)


def test_gates_thresholds_and_inputs():
    paired = good_paired()
    decisions = [
        decision_record(f"run-{n}", 0, arm, prefix="divergent", agree=True)
        for n in range(6)
        for arm in ("world", "control")
    ]
    gates = {
        g.name: g
        for g in evaluate_gates(
            mismatches=[],
            paired=paired,
            scores=good_scores(paired),
            decisions=decisions,
            thresholds=THRESHOLDS,
            replay_steps=120,
        )
    }
    assert gates["replay"].outcome == "passed"
    assert gates["replay"].value == 0.0
    assert gates["replay"].inputs["steps"] == 120
    assert gates["replay"].inputs["ok"] == 120

    assert gates["paired"].outcome == "passed"
    assert gates["paired"].value == pytest.approx(0.0)
    assert gates["paired"].threshold == 0.10
    assert gates["paired"].inputs["cell_agreement"] == 1.0

    assert gates["rank"].outcome == "passed"
    assert gates["rank"].value == pytest.approx(1.0)
    assert "discreteness" in gates["rank"].inputs

    assert gates["decision"].outcome == "passed"
    assert gates["decision"].inputs["divergent_decisions"] == 6


def test_replay_gate_fails_on_an_undeclared_class():
    from .replay import Mismatch

    mismatch = Mismatch(
        run_id="r",
        configuration="A",
        step_index=0,
        tool_name="list_notes",
        arguments={},
        recorded=None,
        replayed=None,
        diffs=[],
        kind="mismatch",
        declared=(),
        classes=(("list_notes", "/results"),),
    )
    gate = evaluate_gates(
        mismatches=[mismatch],
        paired=None,
        scores=good_scores(good_paired()),
        decisions=None,
        thresholds=THRESHOLDS,
        replay_steps=10,
    )[0]
    assert gate.outcome == "failed" and gate.value == 1.0
    assert gate.inputs["undeclared_classes"] == [["list_notes", "/results"]]
    assert gate.inputs["mismatch"] == 1


def test_gates_unusable_configuration_inconclusive():
    paired = good_paired()
    scores = config_scores(
        [
            cell(p.configuration, p.input_no, p.repeat, system)
            for p in paired
            for system in ("real", "world")
        ],
        paired,
        min_valid=40,
    )
    gates = {
        g.name: g
        for g in evaluate_gates(
            mismatches=[],
            paired=paired,
            scores=scores,
            decisions=[],
            thresholds=THRESHOLDS,
            replay_steps=5,
        )
    }
    assert gates["paired"].outcome == "inconclusive"
    assert gates["paired"].reason == "configuration A unusable: 10 of 60 valid"
    assert gates["rank"].outcome == "inconclusive"


def test_gates_without_scores_cannot_check_usability():
    """`scores=None` is "not checked", which is a reason to doubt the gate, not to trust
    it — the same rule as a gate passing on no data."""
    paired = good_paired()
    gates = {
        g.name: g
        for g in evaluate_gates(
            mismatches=[],
            paired=paired,
            scores=None,
            decisions=[],
            thresholds=THRESHOLDS,
            replay_steps=50,
        )
    }
    assert gates["paired"].outcome == "inconclusive"
    assert "usability was not checked" in (gates["paired"].reason or "")
    assert gates["rank"].outcome == "inconclusive"


def test_gates_replay_without_a_step_count_is_inconclusive():
    gate = evaluate_gates(
        mismatches=[],
        paired=None,
        scores=None,
        decisions=None,
        thresholds=THRESHOLDS,
        replay_steps=None,
    )[0]
    assert gate.outcome == "inconclusive"
    assert gate.passed is None
    assert gate.reason == "no replayed steps"


def test_evaluate_gates_with_stats_returns_what_the_gate_was_judged_on():
    paired = good_paired()
    results = evaluate_gates_with_stats(
        mismatches=[],
        paired=paired,
        scores=good_scores(paired),
        decisions=[],
        thresholds=THRESHOLDS,
        replay_steps=10,
        resamples=100,
        seed=5,
    )
    paired_gate = next(g for g in results.gates if g.name == "paired")
    assert results.paired is not None
    assert paired_gate.interval == results.paired.interval
    assert results.paired.interval.seed == 5
    assert results.paired.interval.resamples == 100


def test_fault_thresholds_rescale_to_the_fault_run_volume():
    base = GateThresholds()
    scaled = fault_thresholds(base, episodes_per_config=20)
    assert scaled.episodes_per_config == 20
    assert scaled.min_valid_per_config == 14  # ceil(40/60 x 20)
    assert scaled.paired_delta_max == base.paired_delta_max


def test_decision_gate_one_sided_lower_bound():
    same = [
        decision_record(f"run-{n}", 0, arm, prefix="divergent", agree=True)
        for n in range(8)
        for arm in ("world", "control")
    ]
    passed = evaluate_gates(
        mismatches=None,
        paired=None,
        scores=None,
        decisions=same,
        thresholds=THRESHOLDS,
        replay_steps=None,
    )[3]
    assert passed.outcome == "passed"
    assert passed.interval is not None and passed.interval.low >= -0.05

    worse = [
        decision_record(f"run-{n}", 0, "world", prefix="divergent", agree=False)
        for n in range(8)
    ] + [
        decision_record(f"run-{n}", 0, "control", prefix="divergent", agree=True)
        for n in range(8)
    ]
    failed = evaluate_gates(
        mismatches=None,
        paired=None,
        scores=None,
        decisions=worse,
        thresholds=THRESHOLDS,
        replay_steps=None,
    )[3]
    assert failed.outcome == "failed"
    assert failed.value == pytest.approx(-1.0)

    better = [
        decision_record(f"run-{n}", 0, "world", prefix="divergent", agree=True)
        for n in range(8)
    ] + [
        decision_record(f"run-{n}", 0, "control", prefix="divergent", agree=False)
        for n in range(8)
    ]
    better_gate = evaluate_gates(
        mismatches=None,
        paired=None,
        scores=None,
        decisions=better,
        thresholds=THRESHOLDS,
        replay_steps=None,
    )[3]
    assert better_gate.outcome == "passed"


def test_decision_gate_not_measurable_without_divergences():
    records = [
        decision_record("run-1", 0, arm, prefix="control")
        for arm in ("world", "control")
    ]
    gate = evaluate_gates(
        mismatches=None,
        paired=None,
        scores=None,
        decisions=records,
        thresholds=THRESHOLDS,
        replay_steps=None,
    )[3]
    assert gate.outcome == "not_measurable"
    assert gate.reason == "no divergences"
    assert gate.passed is None


# ---- fault gate ----


def fault_result(
    name: str, *, detected: bool, inconclusive: bool = False
) -> FaultResult:
    return FaultResult(
        fault=name,
        target="paired",
        port=8011,
        world_version="w",
        triggers=0 if inconclusive else 10,
        gates=[],
        moved=["paired"] if detected else [],
        statistic_moved=False,
        detected=detected,
        inconclusive=inconclusive,
        reason="never fired" if inconclusive else None,
    )


def test_fault_gate_needs_four_detected_and_zero_inconclusive():
    detected_five = [fault_result(f"f{n}", detected=n < 5) for n in range(6)]
    gate = fault_gate(detected_five, THRESHOLDS)
    assert gate.outcome == "passed" and gate.value == 5.0
    assert gate.inputs["undetected"] == ["f5"]

    too_few = [fault_result(f"f{n}", detected=n < 3) for n in range(6)]
    assert fault_gate(too_few, THRESHOLDS).outcome == "failed"

    with_untriggered = [fault_result(f"f{n}", detected=n < 5) for n in range(5)] + [
        fault_result("f5", detected=False, inconclusive=True)
    ]
    blocked = fault_gate(with_untriggered, THRESHOLDS)
    assert blocked.outcome == "failed"
    assert blocked.inputs["inconclusive"] == ["f5"]
    assert blocked.reason is not None


def test_fault_gate_skipped_and_inconclusive_on_empty():
    assert fault_gate(None, THRESHOLDS).outcome == "skipped"
    assert fault_gate([], THRESHOLDS).outcome == "inconclusive"


def gate(name: str, passed: bool | None) -> Gate:
    return Gate(
        name=name,  # type: ignore[arg-type]
        value=0.0,
        threshold=0.0,
        passed=passed,
        outcome="passed" if passed else "failed",
        interval=None,
        inputs={},
        reason=None,
    )


def test_moved_gates_only_pass_to_fail():
    clean = [gate("replay", True), gate("paired", True), gate("rank", False)]
    faulted = [gate("replay", False), gate("paired", True), gate("rank", False)]
    assert moved_gates(clean, faulted) == ["replay"]
    assert moved_gates(clean, clean) == []


def test_moved_beyond_interval():
    clean = paired_delta(
        [paired_cell("A", n, 1, real=True, world=True) for n in range(1, 11)],
        resamples=50,
    )
    assert clean.interval == Interval(0.0, 0.0, resamples=50, seed=0)
    faulted = paired_delta(
        [paired_cell("A", n, 1, real=True, world=False) for n in range(1, 11)],
        resamples=50,
    )
    assert moved_beyond_interval(clean, faulted) is True
    assert moved_beyond_interval(clean, clean) is False
