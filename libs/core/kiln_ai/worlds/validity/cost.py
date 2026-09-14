"""What a run will cost before it starts, and what it has cost so far.

The estimate exists so a dry run can print a number a person can refuse. The meter exists
so a run that is going wrong stops at a budget instead of at the end: `--max-cost-usd` ends
the current step, the unit in flight finishes and is written, and the report runs on what
exists with `complete: false`.

Pricing is data. This module has no model ids and no rates of its own; both arrive from the
driver's config, and a model the table does not name is refused rather than metered at zero
whenever a budget is set.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import JsonValue

logger = logging.getLogger(__name__)

LineName = Literal[
    "real_episodes",
    "world_episodes",
    "decision_replay",
    "faulted_world_evals",
    "judge_calls",
]

PER_MILLION = 1_000_000.0


@dataclass(frozen=True)
class Pricing:
    input_usd_per_million: float
    output_usd_per_million: float


@dataclass(frozen=True)
class CostLine:
    name: LineName
    count: int
    estimate_usd: float
    observed_usd: float | None
    basis: str


@dataclass(frozen=True)
class CostModel:
    lines: list[CostLine]
    total_estimate_usd: float
    total_observed_usd: float | None
    pricing_source: str


def call_cost(
    model_id: str,
    input_tokens: float,
    output_tokens: float,
    pricing: Mapping[str, Pricing],
) -> float:
    """One call's cost, or 0.0 for a model the table does not name.

    Silent by design: an unpriced model is reported by `CostMeter`, which sees every call
    and can say so once, rather than by a line per call in a run that makes thousands."""
    rates = pricing.get(model_id)
    if rates is None:
        return 0.0
    return (
        input_tokens * rates.input_usd_per_million
        + output_tokens * rates.output_usd_per_million
    ) / PER_MILLION


def estimate(
    plan: Mapping[str, JsonValue],
    pricing: Mapping[str, Pricing],
    expected_steps_per_episode: float,
    tokens_per_step: Mapping[str, float],
    *,
    pricing_source: str = "config",
    judge_calls_per_episode: int = 10,
) -> CostModel:
    """The five cost lines of the plan.

    An episode is priced as `expected_steps_per_episode` model calls at the configured
    per-step token averages, spread evenly over the configurations so each is priced at its
    own model. A decision is priced as one call. The judge's line is derived from the real
    episode count rather than read from the plan — the plan does not carry it — and costs
    nothing: it reads the reference system, not a model."""
    configurations = _strings(plan.get("configurations"))
    models = _mapping(plan.get("model_ids"))
    input_tokens = float(tokens_per_step.get("input", 0.0))
    output_tokens = float(tokens_per_step.get("output", 0.0))

    def per_episode(model_id: str) -> float:
        return call_cost(
            model_id,
            input_tokens * expected_steps_per_episode,
            output_tokens * expected_steps_per_episode,
            pricing,
        )

    def spread(count: int) -> float:
        if not configurations:
            return 0.0
        share = count / len(configurations)
        return sum(
            share * per_episode(str(models.get(name, ""))) for name in configurations
        )

    episodes = _mapping(plan.get("episodes"))
    real = _count(episodes.get("real"))
    world = _count(episodes.get("world"))

    faults = _mapping(plan.get("faults"))
    faulted = _count(faults.get("faulted_world_episodes"))

    decisions = _mapping(plan.get("decision_calls_estimate"))
    arms = _count(decisions.get("arms")) if "arms" in decisions else 1
    divergent = decisions.get("divergent")
    control = _count(decisions.get("control"))
    decision_count = (
        (_count(divergent) + control) * arms
        if isinstance(divergent, int)
        else control * arms
    )
    decision_usd = (
        decision_count
        / max(len(configurations), 1)
        * sum(
            call_cost(str(models.get(name, "")), input_tokens, output_tokens, pricing)
            for name in configurations
        )
    )

    lines = [
        CostLine(
            "real_episodes",
            real,
            spread(real),
            None,
            f"{len(configurations)} configurations x {_count(plan.get('input_pairs'))} inputs "
            f"x {_count(plan.get('repeats'))} repeats, sequential, one reset each",
        ),
        CostLine(
            "world_episodes", world, spread(world), None, "same volume, concurrent"
        ),
        CostLine(
            "decision_replay",
            decision_count,
            decision_usd,
            None,
            (
                f"{divergent} divergent-prefix + {control} control decisions, {arms} arms, "
                "temperature 0; one model call each, priced at one step of context"
                if isinstance(divergent, int)
                else f"{control} control decisions, {arms} arms, temperature 0; one model "
                "call each, priced at one step of context. The divergent set is not "
                "estimated and is omitted here: it is known only after replay, and the "
                "driver re-prints this line then"
            ),
        ),
        CostLine(
            "faulted_world_evals",
            faulted,
            spread(faulted),
            None,
            f"{_count(faults.get('paired_targeted'))} paired-targeted faults x "
            f"{_count(faults.get('episodes_per_paired_fault'))} episodes",
        ),
        CostLine(
            "judge_calls",
            real * judge_calls_per_episode,
            0.0,
            None,
            f"<= {judge_calls_per_episode} reference-system calls per real episode; "
            "no model cost",
        ),
    ]
    return CostModel(
        lines=lines,
        total_estimate_usd=sum(line.estimate_usd for line in lines),
        total_observed_usd=None,
        pricing_source=pricing_source,
    )


def _mapping(value: JsonValue) -> dict[str, JsonValue]:
    return value if isinstance(value, dict) else {}


def _count(value: JsonValue) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _strings(value: JsonValue) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return []
    return [str(item) for item in value]


class UnpricedModel(RuntimeError):
    """A model with no price was metered while a budget was set, so the budget could no
    longer bind. Raised on the first such call rather than at the end of the run."""

    def __init__(self, model_id: str, max_usd: float) -> None:
        super().__init__(
            f"no pricing for model {model_id!r}; it would be metered at $0 against a "
            f"budget of ${max_usd:.4f}, which disables the budget"
        )
        self.model_id = model_id
        self.max_usd = max_usd


class BudgetExceeded(RuntimeError):
    """The run has spent its budget. The step ends after the unit in flight."""

    def __init__(self, step: str, spent_usd: float, max_usd: float) -> None:
        super().__init__(
            f"step '{step}' passed the budget: ${spent_usd:.4f} of ${max_usd:.4f}"
        )
        self.step = step
        self.spent_usd = spent_usd
        self.max_usd = max_usd


class CostMeter:
    """Running spend across the paid steps.

    A usage record that carries its own `cost` is believed — it is what the provider
    charged. Otherwise the configured pricing is applied to the token counts.

    A model the pricing table does not name costs nothing, which would quietly remove the
    budget guard exactly when a run is going wrong. Two defences: `model_ids` validates
    the table against the models the run will actually use, before the first call; and
    every unpriced call is counted so `unpriced_caveat` can say so in the report."""

    def __init__(
        self,
        max_usd: float | None,
        pricing: Mapping[str, Pricing],
        *,
        model_ids: Sequence[str] = (),
    ) -> None:
        missing = sorted({model for model in model_ids if model not in pricing})
        if missing:
            raise ValueError(
                f"no pricing for {missing}; a model the table does not name is metered "
                "at zero, which disables --max-cost-usd"
            )
        self._max_usd = max_usd
        self._pricing = dict(pricing)
        self._spent = 0.0
        self.unpriced: dict[str, int] = {}
        self.step = "run"

    def add(self, model_id: str, usage: Mapping[str, JsonValue]) -> float:
        self._spent += self._cost_of(model_id, usage)
        if self._max_usd is not None and self._spent > self._max_usd:
            raise BudgetExceeded(self.step, self._spent, self._max_usd)
        return self._spent

    def _unpriced(self, model_id: str) -> None:
        """A call metered at zero. With a budget set this is fatal on the first one: a
        budget that cannot bind is not a budget, and the run is spending real money it is
        no longer counting. Without a budget it is counted for the caveat."""
        self.unpriced[model_id] = self.unpriced.get(model_id, 0) + 1
        if self._max_usd is not None:
            raise UnpricedModel(model_id, self._max_usd)
        if self.unpriced[model_id] == 1:
            logger.warning("no pricing for model %s; costing it at zero", model_id)

    def _cost_of(self, model_id: str, usage: Mapping[str, JsonValue]) -> float:
        recorded = usage.get("cost")
        if isinstance(recorded, (int, float)) and not isinstance(recorded, bool):
            # Clamped: a negative figure from a provider would otherwise buy back budget.
            return max(0.0, float(recorded))
        if model_id not in self._pricing:
            self._unpriced(model_id)
            return 0.0
        return call_cost(
            model_id,
            _tokens(usage.get("input_tokens")),
            _tokens(usage.get("output_tokens")),
            self._pricing,
        )

    def unpriced_caveat(self) -> str | None:
        """The caveat for calls that were metered at zero, or None when there were none."""
        if not self.unpriced:
            return None
        listed = ", ".join(
            f"{model} ({count} calls)" for model, count in sorted(self.unpriced.items())
        )
        return (
            f"no pricing was configured for {listed}; those calls were metered at $0 and "
            "did not count against the budget"
        )

    @property
    def spent_usd(self) -> float:
        return self._spent


def _tokens(value: JsonValue) -> float:
    return (
        float(value)
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        else 0.0
    )
