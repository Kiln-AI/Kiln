"""Tests for the built-in statistics tools.

Regression anchors are known worked examples (86.4% pass, n=147 -> SE ~2.8pp;
McNemar discordant counts b=13, c=6, n=104 -> exact two-sided p=0.1671).
"""

import json

import pytest

from kiln_ai.datamodel.tool_id import KilnBuiltInToolId
from kiln_ai.tools.built_in_tools.stats_tools import (
    ComparePairedTool,
    CompareProportionsTool,
    McNemarPairedTool,
    ProportionCITool,
)
from kiln_ai.tools.tool_registry import tool_from_id


async def _run(tool, **kwargs) -> dict:
    result = await tool.run(**kwargs)
    return json.loads(result.output)


class TestProportionCI:
    async def test_proportion_regression_anchor(self):
        out = await _run(ProportionCITool(), proportion=0.864, n=147)
        assert out["successes"] == 127
        assert out["percent"] == 86.4
        assert out["standard_error"] == pytest.approx(0.0283, abs=5e-4)
        assert out["standard_error_pct"] == pytest.approx(2.8, abs=0.1)
        assert out["method"] == "wilson"
        assert out["ci_low_pct"] < out["percent"] < out["ci_high_pct"]

    async def test_successes_path_equals_proportion_path(self):
        a = await _run(ProportionCITool(), proportion=0.864, n=147)
        b = await _run(ProportionCITool(), successes=127, n=147)
        assert a == b

    async def test_extreme_proportion_clamped(self):
        out = await _run(ProportionCITool(), proportion=0.99, n=104)
        assert out["ci_high"] <= 1.0
        assert out["ci_low"] > 0.9

    async def test_higher_confidence_widens_interval(self):
        narrow = await _run(ProportionCITool(), proportion=0.864, n=147)
        wide = await _run(ProportionCITool(), proportion=0.864, n=147, confidence=0.99)
        assert (wide["ci_high_pct"] - wide["ci_low_pct"]) > (
            narrow["ci_high_pct"] - narrow["ci_low_pct"]
        )

    async def test_missing_n_errors(self):
        result = await ProportionCITool().run(proportion=0.5)
        assert result.is_error is True
        assert "n" in (result.error_message or "")

    async def test_proportion_out_of_range_errors(self):
        result = await ProportionCITool().run(proportion=1.4, n=10)
        assert result.is_error is True


class TestCompareProportions:
    async def test_significant_difference(self):
        out = await _run(
            CompareProportionsTool(),
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
            CompareProportionsTool(),
            proportion_a=0.50,
            n_a=20,
            proportion_b=0.55,
            n_b=20,
        )
        assert out["significant"] is False
        assert out["ci_low"] < 0 < out["ci_high"]

    async def test_negative_delta_sign(self):
        out = await _run(
            CompareProportionsTool(),
            successes_a=90,
            n_a=100,
            successes_b=80,
            n_b=100,
        )
        assert out["delta_pct"] < 0

    async def test_missing_n_errors(self):
        result = await CompareProportionsTool().run(
            proportion_a=0.8, proportion_b=0.9, n_b=100
        )
        assert result.is_error is True


class TestMcNemarPaired:
    async def test_counts_form_gold(self):
        out = await _run(McNemarPairedTool(), b=13, c=6, n=104)
        assert out["p_exact"] == pytest.approx(0.1671, abs=1e-4)
        assert out["chi2_cc"] == pytest.approx(1.895, abs=1e-3)
        assert out["significant"] is False
        assert out["ci_method"] == "mcnemar_wald"
        assert out["delta_pct"] == pytest.approx(-6.7, abs=0.1)
        assert "pooling_warning" in out

    async def test_arrays_match_counts(self):
        # 3 both-pass, 2 both-fail, 4 (A pass / B fail) -> b, 1 (A fail / B pass) -> c.
        outcomes_a = [1, 1, 1, 0, 0, 1, 1, 1, 1, 0]
        outcomes_b = [1, 1, 1, 0, 0, 0, 0, 0, 0, 1]
        from_arrays = await _run(
            McNemarPairedTool(), outcomes_a=outcomes_a, outcomes_b=outcomes_b
        )
        assert from_arrays["table"] == {"n11": 3, "n10": 4, "n01": 1, "n00": 2}
        assert from_arrays["discordant_hurt_b"] == 4
        assert from_arrays["discordant_helped_c"] == 1
        from_counts = await _run(McNemarPairedTool(), b=4, c=1, n=10)
        assert from_arrays["p_exact"] == from_counts["p_exact"]

    async def test_full_table_uses_newcombe_paired(self):
        out = await _run(McNemarPairedTool(), n11=51, n10=13, n01=6, n00=34)
        assert out["ci_method"] == "newcombe_paired"
        assert out["p_a_pct"] is not None
        assert out["p_b_pct"] is not None
        assert out["delta_pct"] == pytest.approx(-6.7, abs=0.1)

    async def test_no_discordant(self):
        out = await _run(McNemarPairedTool(), b=0, c=0, n=50)
        assert out["p_exact"] == 1.0
        assert out["significant"] is False

    async def test_counts_without_n_omits_delta(self):
        out = await _run(McNemarPairedTool(), b=8, c=3)
        assert out["delta"] is None
        assert out["ci_method"] is None
        assert out["p_exact"] == pytest.approx(0.2266, abs=1e-3)

    async def test_array_length_mismatch_errors(self):
        result = await McNemarPairedTool().run(outcomes_a=[1, 0, 1], outcomes_b=[1, 0])
        assert result.is_error is True
        assert "length" in (result.error_message or "").lower()

    async def test_non_binary_entry_errors(self):
        result = await McNemarPairedTool().run(
            outcomes_a=[1, 0, 2], outcomes_b=[1, 0, 1]
        )
        assert result.is_error is True

    async def test_no_input_errors(self):
        result = await McNemarPairedTool().run(confidence=0.95)
        assert result.is_error is True


class TestComparePaired:
    async def test_significant_shift(self):
        out = await _run(
            ComparePairedTool(),
            values_a=[1, 2, 3, 4, 5, 6, 7],
            values_b=[1.5, 2.6, 3.4, 4.7, 5.5, 6.8, 7.6],
        )
        assert out["wilcoxon_p"] is not None
        assert out["wilcoxon_p"] < 0.05
        assert out["significant"] is True
        assert out["n_pairs_used"] == 7

    async def test_few_nonzero_omits_wilcoxon(self):
        out = await _run(
            ComparePairedTool(), values_a=[1, 2, 3, 4], values_b=[2, 3, 4, 5]
        )
        assert out["wilcoxon_p"] is None
        assert out["wilcoxon_note"] is not None

    async def test_drops_nan_pairs(self):
        out = await _run(
            ComparePairedTool(),
            values_a=[1.0, 2.0, 3.0],
            values_b=[2.0, float("nan"), 4.0],
        )
        assert out["n_pairs"] == 3
        assert out["n_pairs_used"] == 2

    async def test_no_usable_pairs(self):
        out = await _run(
            ComparePairedTool(), values_a=[None, None], values_b=[1.0, 2.0]
        )
        assert out["n_pairs_used"] == 0
        assert out["significant"] is None

    async def test_length_mismatch_errors(self):
        result = await ComparePairedTool().run(values_a=[1, 2, 3], values_b=[1, 2])
        assert result.is_error is True

    async def test_deterministic(self):
        first = await ComparePairedTool().run(
            values_a=[1, 2, 3, 4, 5], values_b=[1.4, 2.6, 2.9, 4.2, 5.5]
        )
        second = await ComparePairedTool().run(
            values_a=[1, 2, 3, 4, 5], values_b=[1.4, 2.6, 2.9, 4.2, 5.5]
        )
        assert first.output == second.output


class TestRegistryWiring:
    @pytest.mark.parametrize(
        "tool_id,expected_name",
        [
            (KilnBuiltInToolId.PROPORTION_CI, "proportion_ci"),
            (KilnBuiltInToolId.COMPARE_PROPORTIONS, "compare_proportions"),
            (KilnBuiltInToolId.MCNEMAR_PAIRED, "mcnemar_paired"),
            (KilnBuiltInToolId.COMPARE_PAIRED, "compare_paired"),
        ],
    )
    async def test_resolves_from_registry(self, tool_id, expected_name):
        tool = tool_from_id(tool_id.value)
        assert await tool.id() == tool_id
        assert await tool.name() == expected_name
        definition = await tool.toolcall_definition()
        assert definition["function"]["name"] == expected_name
        assert "properties" in definition["function"]["parameters"]
