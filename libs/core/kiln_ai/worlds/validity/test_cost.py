from __future__ import annotations

import pytest

from .cost import BudgetExceeded, CostMeter, Pricing, UnpricedModel, estimate

PRICING = {
    "strong": Pricing(input_usd_per_million=3.0, output_usd_per_million=15.0),
    "small": Pricing(input_usd_per_million=1.0, output_usd_per_million=5.0),
}

PLAN = {
    "repeats": 3,
    "input_pairs": 20,
    "configurations": ["A", "B"],
    "episodes": {"real": 120, "world": 120},
    "decision_calls_estimate": {
        "divergent": "unknown until replay",
        "control": 300,
        "arms": 2,
    },
    "faults": {
        "paired_targeted": 4,
        "episodes_per_paired_fault": 120,
        "faulted_world_episodes": 480,
    },
    "model_ids": {"A": "strong", "B": "small"},
}


def line(model, name):
    return next(item for item in model.lines if item.name == name)


def test_estimate_lines_from_plan_and_pricing():
    model = estimate(
        PLAN,
        PRICING,
        expected_steps_per_episode=6,
        tokens_per_step={"input": 3000, "output": 120},
        judge_calls_per_episode=7,
    )
    assert [item.name for item in model.lines] == [
        "real_episodes",
        "world_episodes",
        "decision_replay",
        "faulted_world_evals",
        "judge_calls",
    ]
    # per episode: 6 steps x 3000 input + 6 x 120 output
    strong_episode = (18000 * 3.0 + 720 * 15.0) / 1_000_000
    small_episode = (18000 * 1.0 + 720 * 5.0) / 1_000_000
    expected_real = 60 * strong_episode + 60 * small_episode
    assert line(model, "real_episodes").count == 120
    assert line(model, "real_episodes").estimate_usd == pytest.approx(expected_real)
    assert line(model, "world_episodes").estimate_usd == pytest.approx(expected_real)
    assert line(model, "faulted_world_evals").count == 480
    assert line(model, "judge_calls").estimate_usd == 0.0
    assert "x 20 inputs x 3 repeats" in line(model, "real_episodes").basis
    # derived from the real episode count, not read from a plan key no producer writes
    assert line(model, "judge_calls").count == 120 * 7
    assert (
        "<= 7 reference-system calls per real episode"
        in line(model, "judge_calls").basis
    )
    assert model.pricing_source == "config"
    assert model.total_observed_usd is None
    assert model.total_estimate_usd == pytest.approx(
        sum(item.estimate_usd for item in model.lines)
    )


def test_estimate_decision_line_counts_control_until_divergences_are_known():
    unknown = estimate(
        PLAN,
        PRICING,
        expected_steps_per_episode=6,
        tokens_per_step={"input": 3000, "output": 120},
    )
    assert line(unknown, "decision_replay").count == 600

    known = dict(PLAN)
    known["decision_calls_estimate"] = {"divergent": 214, "control": 300, "arms": 2}
    resolved = estimate(
        known,
        PRICING,
        expected_steps_per_episode=6,
        tokens_per_step={"input": 3000, "output": 120},
    )
    assert line(resolved, "decision_replay").count == 1028
    assert (
        line(resolved, "decision_replay").estimate_usd
        > line(unknown, "decision_replay").estimate_usd
    )


def test_estimate_survives_a_plan_with_nothing_in_it():
    model = estimate({}, PRICING, expected_steps_per_episode=6, tokens_per_step={})
    assert model.total_estimate_usd == 0.0
    assert all(item.count == 0 for item in model.lines)


def test_cost_meter_accumulates_and_raises_past_budget():
    meter = CostMeter(0.10, PRICING)
    meter.step = "real"
    spent = meter.add("strong", {"input_tokens": 10_000, "output_tokens": 1_000})
    assert spent == pytest.approx((10_000 * 3.0 + 1_000 * 15.0) / 1_000_000)
    assert meter.spent_usd == pytest.approx(spent)

    with pytest.raises(BudgetExceeded) as caught:
        for _ in range(100):
            meter.add("strong", {"input_tokens": 100_000, "output_tokens": 10_000})
    assert caught.value.step == "real"
    assert caught.value.max_usd == 0.10
    assert caught.value.spent_usd > 0.10


def test_cost_meter_unlimited_when_none():
    meter = CostMeter(None, PRICING)
    for _ in range(50):
        meter.add("strong", {"input_tokens": 1_000_000, "output_tokens": 1_000_000})
    assert meter.spent_usd > 100


def test_cost_meter_prefers_recorded_cost():
    """A usage record that carries its own cost is what the provider charged."""
    meter = CostMeter(None, PRICING)
    meter.add("strong", {"input_tokens": 10_000, "output_tokens": 1_000, "cost": 0.5})
    assert meter.spent_usd == pytest.approx(0.5)


def test_cost_meter_prices_an_unknown_model_at_zero_without_a_budget():
    meter = CostMeter(None, PRICING)
    meter.add("never-heard-of-it", {"input_tokens": 10_000, "output_tokens": 1_000})
    assert meter.spent_usd == 0.0
    assert meter.unpriced == {"never-heard-of-it": 1}


def test_cost_meter_refuses_an_unpriced_model_when_a_budget_is_set():
    """A budget that cannot bind is not a budget: the run would be spending real money it
    had stopped counting, which is exactly when --max-cost-usd matters."""
    meter = CostMeter(0.01, PRICING)
    with pytest.raises(UnpricedModel, match="disables the budget"):
        meter.add("mystery", {"input_tokens": 10_000_000, "output_tokens": 10_000_000})
    assert meter.unpriced == {"mystery": 1}


def test_cost_meter_clamps_a_negative_recorded_cost():
    """A negative figure from a provider would otherwise buy budget back."""
    meter = CostMeter(1.0, PRICING)
    meter.add("strong", {"input_tokens": 0, "output_tokens": 0, "cost": -5.0})
    assert meter.spent_usd == 0.0


def test_estimate_honours_an_explicit_zero_arms():
    plan = dict(PLAN)
    plan["decision_calls_estimate"] = {"divergent": 10, "control": 300, "arms": 0}
    model = estimate(
        plan,
        PRICING,
        expected_steps_per_episode=6,
        tokens_per_step={"input": 1, "output": 1},
    )
    assert line(model, "decision_replay").count == 0


def test_estimate_decision_basis_says_the_divergent_set_is_omitted():
    unknown = estimate(
        PLAN,
        PRICING,
        expected_steps_per_episode=6,
        tokens_per_step={"input": 3000, "output": 120},
    )
    basis = line(unknown, "decision_replay").basis
    assert "not estimated and is omitted" in basis
    assert "expected_steps_per_episode" not in basis


def test_cost_meter_refuses_a_pricing_table_that_misses_a_model():
    """A model priced at zero disables --max-cost-usd exactly when a run is going wrong,
    so the table is checked against the models the run will use, before the first call."""
    with pytest.raises(ValueError, match=r"no pricing for \['mystery'\]"):
        CostMeter(1.0, PRICING, model_ids=["strong", "mystery"])
    CostMeter(1.0, PRICING, model_ids=["strong", "small"])


def test_cost_meter_counts_and_caveats_unpriced_calls():
    meter = CostMeter(None, PRICING)
    assert meter.unpriced_caveat() is None
    meter.add("mystery", {"input_tokens": 10, "output_tokens": 10})
    meter.add("mystery", {"input_tokens": 10, "output_tokens": 10})
    assert meter.unpriced == {"mystery": 2}
    caveat = meter.unpriced_caveat()
    assert caveat is not None and "mystery (2 calls)" in caveat
    # a call that carried its own cost was priced, so it is not counted as unpriced
    meter.add("also-unknown", {"input_tokens": 10, "output_tokens": 10, "cost": 0.2})
    assert "also-unknown" not in meter.unpriced
