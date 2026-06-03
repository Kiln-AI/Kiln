"""Tests for the built-in statistics tool (one tool, dispatched by `operation`).

Regression anchors are known worked examples (86.4% pass, n=147 -> SE ~2.8pp;
McNemar discordant counts b=13, c=6, n=104 -> exact two-sided p=0.1671).
"""

import json

import pytest

from kiln_ai.datamodel.tool_id import KilnBuiltInToolId
from kiln_ai.tools.built_in_tools.stats_tools import StatisticsTool
from kiln_ai.tools.tool_registry import tool_from_id


async def _run(operation, **kwargs) -> dict:
    result = await StatisticsTool().run(operation=operation, **kwargs)
    return json.loads(result.output)


def _outcomes(n11, n10, n01, n00):
    """Build two aligned 0/1 arrays with the given 2x2 cell counts."""
    a = [1] * n11 + [1] * n10 + [0] * n01 + [0] * n00
    b = [1] * n11 + [0] * n10 + [1] * n01 + [0] * n00
    return a, b


class TestOperationDispatch:
    async def test_unknown_operation_errors(self):
        result = await StatisticsTool().run(operation="ttest", n=10)
        assert result.is_error is True
        assert "operation" in (result.error_message or "")

    async def test_missing_operation_errors(self):
        result = await StatisticsTool().run(n=10)
        assert result.is_error is True


class TestProportionCI:
    async def test_trace_regression_anchor(self):
        out = await _run("proportion_ci", proportion=0.864, n=147)
        assert out["operation"] == "proportion_ci"
        assert out["successes"] == 127
        assert out["percent"] == 86.4
        assert out["standard_error"] == pytest.approx(0.0283, abs=5e-4)
        assert out["standard_error_pct"] == pytest.approx(2.8, abs=0.1)
        assert out["method"] == "wilson"
        assert out["ci_low_pct"] < out["percent"] < out["ci_high_pct"]

    async def test_extreme_proportion_clamped(self):
        out = await _run("proportion_ci", proportion=0.99, n=104)
        assert out["ci_high"] <= 1.0
        assert out["ci_low"] > 0.9

    async def test_higher_confidence_widens_interval(self):
        narrow = await _run("proportion_ci", proportion=0.864, n=147)
        wide = await _run("proportion_ci", proportion=0.864, n=147, confidence=0.99)
        assert (wide["ci_high_pct"] - wide["ci_low_pct"]) > (
            narrow["ci_high_pct"] - narrow["ci_low_pct"]
        )

    async def test_missing_n_errors(self):
        result = await StatisticsTool().run(operation="proportion_ci", proportion=0.5)
        assert result.is_error is True
        assert "n" in (result.error_message or "")

    async def test_missing_proportion_errors(self):
        result = await StatisticsTool().run(operation="proportion_ci", n=100)
        assert result.is_error is True
        assert "proportion" in (result.error_message or "")

    async def test_proportion_out_of_range_errors(self):
        result = await StatisticsTool().run(
            operation="proportion_ci", proportion=1.4, n=10
        )
        assert result.is_error is True

    async def test_non_numeric_proportion_errors(self):
        result = await StatisticsTool().run(
            operation="proportion_ci", proportion="abc", n=10
        )
        assert result.is_error is True
        assert "proportion" in (result.error_message or "")


class TestCompareProportions:
    async def test_significant_difference(self):
        out = await _run(
            "compare_proportions",
            proportion_a=0.864,
            n_a=147,
            proportion_b=0.951,
            n_b=104,
        )
        assert out["method"] == "newcombe_wilson"
        assert out["delta_pct"] > 0
        assert out["ci_low"] > 0
        assert out["significant"] is True
        assert out["bootstrap"] is not None
        assert "mcnemar_paired" in out["note"]

    async def test_not_significant(self):
        out = await _run(
            "compare_proportions", proportion_a=0.50, n_a=20, proportion_b=0.55, n_b=20
        )
        assert out["significant"] is False
        assert out["ci_low"] < 0 < out["ci_high"]

    async def test_negative_delta_sign(self):
        out = await _run(
            "compare_proportions",
            proportion_a=0.90,
            n_a=100,
            proportion_b=0.80,
            n_b=100,
        )
        assert out["delta_pct"] < 0

    async def test_missing_n_errors(self):
        result = await StatisticsTool().run(
            operation="compare_proportions", proportion_a=0.8, proportion_b=0.9, n_b=100
        )
        assert result.is_error is True


class TestMcNemarPaired:
    async def test_gold_anchor(self):
        # 2x2: n11=51, n10=13 (b), n01=6 (c), n00=34 (n=104) -> exact p=0.1671.
        a, b = _outcomes(51, 13, 6, 34)
        out = await _run("mcnemar_paired", outcomes_a=a, outcomes_b=b)
        assert out["table"] == {"n11": 51, "n10": 13, "n01": 6, "n00": 34}
        assert out["discordant_hurt_b"] == 13
        assert out["discordant_helped_c"] == 6
        assert out["p_exact"] == pytest.approx(0.1671, abs=1e-4)
        assert out["chi2_cc"] == pytest.approx(1.895, abs=1e-3)
        assert out["significant"] is False
        assert out["ci_method"] == "newcombe_paired"
        assert out["delta_pct"] == pytest.approx(-6.7, abs=0.1)
        assert "pooling_warning" in out

    async def test_significant_when_discordant_lopsided(self):
        a, b = _outcomes(60, 2, 30, 50)  # b=2, c=30 -> clearly significant
        out = await _run("mcnemar_paired", outcomes_a=a, outcomes_b=b)
        assert out["significant"] is True
        assert out["p_exact"] < 0.05

    async def test_no_discordant(self):
        a, b = _outcomes(40, 0, 0, 10)
        out = await _run("mcnemar_paired", outcomes_a=a, outcomes_b=b)
        assert out["p_exact"] == 1.0
        assert out["significant"] is False

    async def test_array_length_mismatch_errors(self):
        result = await StatisticsTool().run(
            operation="mcnemar_paired", outcomes_a=[1, 0, 1], outcomes_b=[1, 0]
        )
        assert result.is_error is True
        assert "length" in (result.error_message or "").lower()

    async def test_non_binary_entry_errors(self):
        result = await StatisticsTool().run(
            operation="mcnemar_paired", outcomes_a=[1, 0, 2], outcomes_b=[1, 0, 1]
        )
        assert result.is_error is True

    async def test_no_input_errors(self):
        result = await StatisticsTool().run(operation="mcnemar_paired", confidence=0.95)
        assert result.is_error is True


class TestComparePaired:
    async def test_significant_shift(self):
        out = await _run(
            "compare_paired",
            values_a=[1, 2, 3, 4, 5, 6, 7],
            values_b=[1.5, 2.6, 3.4, 4.7, 5.5, 6.8, 7.6],
        )
        assert out["wilcoxon_p"] is not None
        assert out["wilcoxon_p"] < 0.05
        assert out["significant"] is True
        assert out["n_pairs_used"] == 7

    async def test_few_nonzero_omits_wilcoxon(self):
        out = await _run("compare_paired", values_a=[1, 2, 3, 4], values_b=[2, 3, 4, 5])
        assert out["wilcoxon_p"] is None
        assert out["wilcoxon_note"] is not None

    async def test_drops_nan_pairs(self):
        out = await _run(
            "compare_paired",
            values_a=[1.0, 2.0, 3.0],
            values_b=[2.0, float("nan"), 4.0],
        )
        assert out["n_pairs"] == 3
        assert out["n_pairs_used"] == 2

    async def test_no_usable_pairs(self):
        out = await _run("compare_paired", values_a=[None, None], values_b=[1.0, 2.0])
        assert out["n_pairs_used"] == 0
        assert out["significant"] is None

    async def test_length_mismatch_errors(self):
        result = await StatisticsTool().run(
            operation="compare_paired", values_a=[1, 2, 3], values_b=[1, 2]
        )
        assert result.is_error is True

    async def test_deterministic(self):
        first = await StatisticsTool().run(
            operation="compare_paired",
            values_a=[1, 2, 3, 4, 5],
            values_b=[1.4, 2.6, 2.9, 4.2, 5.5],
        )
        second = await StatisticsTool().run(
            operation="compare_paired",
            values_a=[1, 2, 3, 4, 5],
            values_b=[1.4, 2.6, 2.9, 4.2, 5.5],
        )
        assert first.output == second.output


class TestRegistryWiring:
    async def test_resolves_from_registry(self):
        tool = tool_from_id(KilnBuiltInToolId.STATISTICS.value)
        assert await tool.id() == KilnBuiltInToolId.STATISTICS
        assert await tool.name() == "statistics"
        definition = await tool.toolcall_definition()
        assert definition["function"]["name"] == "statistics"
        params = definition["function"]["parameters"]
        assert set(params["properties"]["operation"]["enum"]) == {
            "proportion_ci",
            "compare_proportions",
            "mcnemar_paired",
            "compare_paired",
        }
        assert params["required"] == ["operation"]
        # Boiled down to one input form per operation — keep the surface small.
        assert len(params["properties"]) == 12
