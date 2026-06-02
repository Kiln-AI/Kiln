"""Built-in statistics tools: confidence intervals and significance tests.

These let a Kiln agent compute standard errors, confidence intervals, and
significance reliably instead of doing the arithmetic in its own reasoning. The
pure math lives in ``stats_lib.py``; this module wraps it as ``KilnTool``s.

Method-selection guide for the agent:
- one proportion (a "86.4% pass, n=147" cell) -> ``proportion_ci``
- two proportions over the SAME items (e.g. with vs without a change) -> ``mcnemar_paired``
- two independent proportions / only marginals available -> ``compare_proportions``
- a continuous/count metric, paired per case -> ``compare_paired``
"""

import json
import math
import statistics

from kiln_ai.datamodel.tool_id import KilnBuiltInToolId
from kiln_ai.tools.base_tool import KilnTool, ToolCallContext, ToolCallResult
from kiln_ai.tools.built_in_tools.stats_lib import (
    bootstrap_difference_ci,
    mcnemar_chi2_cc,
    mcnemar_exact_p,
    paired_bootstrap_diff_ci,
    paired_proportion_diff_ci,
    wilcoxon_signed_rank_p,
    wilson_ci,
    wilson_difference_ci,
    z_for_confidence,
)

_CONFIDENCE_SCHEMA = {
    "type": "number",
    "description": "Confidence level in (0,1). Default 0.95.",
    "default": 0.95,
    "exclusiveMinimum": 0,
    "exclusiveMaximum": 1,
}


def _error(msg: str) -> ToolCallResult:
    return ToolCallResult(
        output=json.dumps({"error": msg}, ensure_ascii=False),
        is_error=True,
        error_message=msg,
    )


def resolve_successes(proportion, successes, n: int) -> int:
    """Resolve an integer success count from either a fraction or an explicit count.

    ``successes`` wins when both are given. The fraction path rounds and clamps to
    [0, n] (a 1.0 proportion legitimately yields n). Raises ValueError on bad input.
    """
    if successes is not None:
        s = int(successes)
        if s < 0 or s > n:
            raise ValueError(f"successes ({s}) must be between 0 and n ({n}).")
        return s
    if proportion is not None:
        p = float(proportion)
        if not (0.0 <= p <= 1.0):
            raise ValueError(f"proportion must be in [0,1] (got {p}).")
        return max(0, min(n, round(p * n)))
    raise ValueError(
        "Provide either 'proportion' (a fraction) or 'successes' (a count)."
    )


# ---------------------------------------------------------------------------
# proportion_ci
# ---------------------------------------------------------------------------

_PROPORTION_CI_DESCRIPTION = """Confidence interval and standard error for a single proportion (e.g. one eval cell like "85% pass, n=200"). Use this INSTEAD of computing the standard error by hand. Pass the proportion as a fraction (0.85) OR the integer count of successes, always with the sample size n. Returns the Wilson score interval (robust near 0% and 100%), the normal-approximation standard error, and a one-sentence interpretation. Confidence defaults to 0.95."""


class ProportionCITool(KilnTool):
    def __init__(self) -> None:
        super().__init__(
            tool_id=KilnBuiltInToolId.PROPORTION_CI,
            name="proportion_ci",
            description=_PROPORTION_CI_DESCRIPTION,
            parameters_schema={
                "type": "object",
                "properties": {
                    "proportion": {
                        "type": "number",
                        "description": "The proportion as a fraction in [0,1] (e.g. 0.85 for 85%). Provide this OR 'successes'.",
                        "minimum": 0,
                        "maximum": 1,
                    },
                    "successes": {
                        "type": "integer",
                        "description": "Integer count of successes. Provide this OR 'proportion'.",
                        "minimum": 0,
                    },
                    "n": {
                        "type": "integer",
                        "description": "Sample size (total count). Must be > 0.",
                        "minimum": 1,
                    },
                    "confidence": _CONFIDENCE_SCHEMA,
                },
                "required": ["n"],
            },
        )

    async def run(
        self, context: ToolCallContext | None = None, **kwargs
    ) -> ToolCallResult:
        _ = context
        try:
            n = kwargs.get("n")
            if n is None:
                raise ValueError("'n' (sample size) is required.")
            n = int(n)
            if n <= 0:
                raise ValueError(f"n must be a positive integer (got {n}).")
            confidence = float(kwargs.get("confidence", 0.95))
            successes = resolve_successes(
                kwargs.get("proportion"), kwargs.get("successes"), n
            )
            z = z_for_confidence(confidence)
        except (ValueError, TypeError) as e:
            return _error(str(e))

        p = successes / n
        low, high = wilson_ci(successes, n, z)
        se = math.sqrt(p * (1 - p) / n)
        conf_pct = round(confidence * 100)
        out = {
            "operation": "proportion_ci",
            "proportion": round(p, 4),
            "percent": round(p * 100, 1),
            "n": n,
            "successes": successes,
            "method": "wilson",
            "ci_low": low,
            "ci_high": high,
            "ci_low_pct": round(low * 100, 1),
            "ci_high_pct": round(high * 100, 1),
            "standard_error": round(se, 4),
            "standard_error_pct": round(se * 100, 1),
            "confidence": confidence,
            "interpretation": (
                f"{round(p * 100, 1)}% (n={n}); {conf_pct}% Wilson CI "
                f"{round(low * 100, 1)}% to {round(high * 100, 1)}%. "
                f"Normal-approx standard error {round(se * 100, 1)}pp."
            ),
        }
        return ToolCallResult(output=json.dumps(out, ensure_ascii=False))


# ---------------------------------------------------------------------------
# compare_proportions (unpaired)
# ---------------------------------------------------------------------------

_COMPARE_PROPORTIONS_DESCRIPTION = """Compare two INDEPENDENT proportions and test whether they differ (e.g. an impact column: a metric with vs without some condition). Use this INSTEAD of hand-computing the standard error of a difference. Returns the difference in percentage points, a Newcombe (Wilson) confidence interval, a bootstrap cross-check, and a boolean `significant`.

IMPORTANT: this is the UNPAIRED test and is conservative. If both proportions come from the SAME eval items (the usual case when comparing run configs on one dataset), the results are paired — prefer `mcnemar_paired`, which is more powerful. Pass each side as a fraction (proportion_a / proportion_b) OR integer successes, with its sample size. Confidence defaults to 0.95."""


class CompareProportionsTool(KilnTool):
    def __init__(self) -> None:
        super().__init__(
            tool_id=KilnBuiltInToolId.COMPARE_PROPORTIONS,
            name="compare_proportions",
            description=_COMPARE_PROPORTIONS_DESCRIPTION,
            parameters_schema={
                "type": "object",
                "properties": {
                    "proportion_a": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                        "description": "Baseline proportion in [0,1]. Provide this OR 'successes_a'.",
                    },
                    "successes_a": {
                        "type": "integer",
                        "minimum": 0,
                        "description": "Baseline integer successes. Provide this OR 'proportion_a'.",
                    },
                    "n_a": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Baseline sample size (> 0).",
                    },
                    "proportion_b": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                        "description": "Treatment proportion in [0,1]. Provide this OR 'successes_b'.",
                    },
                    "successes_b": {
                        "type": "integer",
                        "minimum": 0,
                        "description": "Treatment integer successes. Provide this OR 'proportion_b'.",
                    },
                    "n_b": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Treatment sample size (> 0).",
                    },
                    "confidence": _CONFIDENCE_SCHEMA,
                },
                "required": ["n_a", "n_b"],
            },
        )

    async def run(
        self, context: ToolCallContext | None = None, **kwargs
    ) -> ToolCallResult:
        _ = context
        try:
            n_a, n_b = kwargs.get("n_a"), kwargs.get("n_b")
            if n_a is None or n_b is None:
                raise ValueError("Both 'n_a' and 'n_b' (sample sizes) are required.")
            n_a, n_b = int(n_a), int(n_b)
            if n_a <= 0 or n_b <= 0:
                raise ValueError("n_a and n_b must be positive integers.")
            confidence = float(kwargs.get("confidence", 0.95))
            s_a = resolve_successes(
                kwargs.get("proportion_a"), kwargs.get("successes_a"), n_a
            )
            s_b = resolve_successes(
                kwargs.get("proportion_b"), kwargs.get("successes_b"), n_b
            )
            z = z_for_confidence(confidence)
        except (ValueError, TypeError) as e:
            return _error(str(e))

        p_a, p_b = s_a / n_a, s_b / n_b
        newcombe = wilson_difference_ci(s_a, n_a, s_b, n_b, z)
        assert newcombe is not None  # n_a, n_b > 0, so never None
        delta, low, high = newcombe
        se_diff = math.sqrt(p_a * (1 - p_a) / n_a + p_b * (1 - p_b) / n_b)
        z_score = delta / se_diff if se_diff > 0 else None
        significant = (low > 0) or (high < 0)

        boot = bootstrap_difference_ci(s_a, n_a, s_b, n_b, confidence=confidence)
        bootstrap_block = None
        if boot is not None:
            _, b_low, b_high = boot
            bootstrap_block = {
                "method": "percentile_bootstrap",
                "ci_low_pct": round(b_low * 100, 1),
                "ci_high_pct": round(b_high * 100, 1),
                "significant": (b_low > 0) or (b_high < 0),
                "note": "Percentile bootstrap; under-states uncertainty at extreme proportions — Wilson is the headline.",
            }

        conf_pct = round(confidence * 100)
        verdict = (
            "statistically significant"
            if significant
            else "not statistically significant"
        )
        out = {
            "operation": "compare_proportions",
            "p_a": round(p_a, 4),
            "p_b": round(p_b, 4),
            "p_a_pct": round(p_a * 100, 1),
            "p_b_pct": round(p_b * 100, 1),
            "n_a": n_a,
            "n_b": n_b,
            "delta": delta,
            "delta_pct": round(delta * 100, 1),
            "method": "newcombe_wilson",
            "ci_low": low,
            "ci_high": high,
            "ci_low_pct": round(low * 100, 1),
            "ci_high_pct": round(high * 100, 1),
            "se_diff": round(se_diff, 4),
            "se_diff_pct": round(se_diff * 100, 1),
            "z_score": round(z_score, 2) if z_score is not None else None,
            "significant": significant,
            "confidence": confidence,
            "bootstrap": bootstrap_block,
            "note": "Unpaired test (conservative). If both proportions come from the same eval items, use mcnemar_paired instead.",
            "interpretation": (
                f"Treatment {round(p_b * 100, 1)}% vs baseline {round(p_a * 100, 1)}% "
                f"(delta {round(delta * 100, 1):+}pp). {conf_pct}% Newcombe CI "
                f"{round(low * 100, 1):+}pp to {round(high * 100, 1):+}pp — {verdict} "
                f"(unpaired test)."
            ),
        }
        return ToolCallResult(output=json.dumps(out, ensure_ascii=False))


# ---------------------------------------------------------------------------
# mcnemar_paired
# ---------------------------------------------------------------------------

_MCNEMAR_DESCRIPTION = """Compare two binary (pass/fail) conditions evaluated over the SAME items — the right test for "did changing X help?" on one eval dataset. This is the PAIRED test (McNemar): it conditions on the items that flip between conditions, so it is more powerful than comparing summary pass-rates with compare_proportions, especially at the ~100-200 sample sizes typical of LLM-as-judge evals. Uses the exact two-sided binomial (reliable when the number of flipped items is small) plus a chi-square cross-check and a paired-difference confidence interval.

Provide EITHER two aligned 0/1 arrays (outcomes_a baseline, outcomes_b treatment, same item per index — fetch per-item eval results and pair on dataset_id) OR the discordant counts b (treatment hurt) and c (treatment helped), optionally with n for a delta/CI, OR the full 2x2 table (n11/n10/n01/n00). Confidence defaults to 0.95. Do NOT pool the same items across multiple run configs — run one paired test per pair."""

_POOLING_WARNING = (
    "Do not pool the same items across multiple run configs/formats — that double-counts "
    "each item and is anti-conservative. Run one paired test per condition pair, or use an "
    "item-level (cluster-correct) analysis offline."
)


def _coerce_binary(values, label: str) -> list[int]:
    out: list[int] = []
    for x in values:
        try:
            v = round(float(x))
        except (TypeError, ValueError):
            raise ValueError(f"{label} must contain only 0/1 values (got {x!r}).")
        if v not in (0, 1):
            raise ValueError(f"{label} must contain only 0/1 values (got {x!r}).")
        out.append(v)
    return out


def _resolve_table(
    kwargs,
) -> tuple[tuple[int, int, int, int] | None, int, int, int | None]:
    """Return (table_or_None, b, c, n_pairs_or_None) from whichever input form was given."""
    oa, ob = kwargs.get("outcomes_a"), kwargs.get("outcomes_b")
    cells = [kwargs.get(k) for k in ("n11", "n10", "n01", "n00")]
    b_in, c_in, n_in = kwargs.get("b"), kwargs.get("c"), kwargs.get("n")

    if oa is not None or ob is not None:
        if oa is None or ob is None:
            raise ValueError("Provide both 'outcomes_a' and 'outcomes_b'.")
        if not isinstance(oa, list) or not isinstance(ob, list):
            raise ValueError("'outcomes_a' and 'outcomes_b' must be arrays.")
        if len(oa) != len(ob):
            raise ValueError(
                f"Paired arrays must be equal length (got {len(oa)} vs {len(ob)})."
            )
        if len(oa) == 0:
            raise ValueError("Paired arrays are empty.")
        a = _coerce_binary(oa, "outcomes_a")
        bb = _coerce_binary(ob, "outcomes_b")
        n11 = n10 = n01 = n00 = 0
        for x, y in zip(a, bb):
            if x == 1 and y == 1:
                n11 += 1
            elif x == 1 and y == 0:
                n10 += 1
            elif x == 0 and y == 1:
                n01 += 1
            else:
                n00 += 1
        return ((n11, n10, n01, n00), n10, n01, n11 + n10 + n01 + n00)

    if all(v is not None for v in cells):
        n11, n10, n01, n00 = (int(v) for v in cells)
        if min(n11, n10, n01, n00) < 0:
            raise ValueError("2x2 counts must be non-negative.")
        return ((n11, n10, n01, n00), n10, n01, n11 + n10 + n01 + n00)

    if b_in is not None and c_in is not None:
        b, c = int(b_in), int(c_in)
        if b < 0 or c < 0:
            raise ValueError("'b' and 'c' must be non-negative.")
        n_pairs = int(n_in) if n_in is not None else None
        if n_pairs is not None and n_pairs < b + c:
            raise ValueError(f"n ({n_pairs}) cannot be less than b + c ({b + c}).")
        return (None, b, c, n_pairs)

    raise ValueError(
        "Provide one of: two aligned 0/1 arrays (outcomes_a, outcomes_b); the discordant "
        "counts b and c; or the full 2x2 table (n11, n10, n01, n00)."
    )


class McNemarPairedTool(KilnTool):
    def __init__(self) -> None:
        super().__init__(
            tool_id=KilnBuiltInToolId.MCNEMAR_PAIRED,
            name="mcnemar_paired",
            description=_MCNEMAR_DESCRIPTION,
            parameters_schema={
                "type": "object",
                "properties": {
                    "outcomes_a": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Per-item baseline outcomes (0=fail, 1=pass). outcomes_a[i] and outcomes_b[i] must be the SAME item.",
                    },
                    "outcomes_b": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Per-item treatment outcomes (0/1), positionally paired with outcomes_a.",
                    },
                    "n11": {
                        "type": "integer",
                        "minimum": 0,
                        "description": "2x2 count: both passed.",
                    },
                    "n10": {
                        "type": "integer",
                        "minimum": 0,
                        "description": "2x2 count: baseline passed, treatment failed (treatment hurt). Same as b.",
                    },
                    "n01": {
                        "type": "integer",
                        "minimum": 0,
                        "description": "2x2 count: baseline failed, treatment passed (treatment helped). Same as c.",
                    },
                    "n00": {
                        "type": "integer",
                        "minimum": 0,
                        "description": "2x2 count: both failed.",
                    },
                    "b": {
                        "type": "integer",
                        "minimum": 0,
                        "description": "Discordant count where treatment HURT (baseline pass, treatment fail). Provide with 'c'.",
                    },
                    "c": {
                        "type": "integer",
                        "minimum": 0,
                        "description": "Discordant count where treatment HELPED (baseline fail, treatment pass). Provide with 'b'.",
                    },
                    "n": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Total paired items (only needed with the b/c form, to report a delta and CI).",
                    },
                    "confidence": _CONFIDENCE_SCHEMA,
                },
                "required": [],
            },
        )

    async def run(
        self, context: ToolCallContext | None = None, **kwargs
    ) -> ToolCallResult:
        _ = context
        try:
            confidence = float(kwargs.get("confidence", 0.95))
            z = z_for_confidence(confidence)
            table, b, c, n_pairs = _resolve_table(kwargs)
        except (ValueError, TypeError) as e:
            return _error(str(e))

        p_exact = mcnemar_exact_p(b, c)
        chi2, p_cc = mcnemar_chi2_cc(b, c)
        significant = p_exact < (1.0 - confidence)
        conf_pct = round(confidence * 100)

        p_a = p_b = delta = ci_low = ci_high = None
        ci_method = None
        if table is not None:
            assert n_pairs is not None  # a built table always carries a pair count
            n11, n10, n01, n00 = table
            p_a = (n11 + n10) / n_pairs
            p_b = (n11 + n01) / n_pairs
            diff_ci = paired_proportion_diff_ci(n11, n10, n01, n00, z)
            if diff_ci is not None:
                delta, ci_low, ci_high = diff_ci
                ci_method = "newcombe_paired"
        elif n_pairs is not None:
            delta = (c - b) / n_pairs
            se = math.sqrt(max(0.0, b + c - (b - c) ** 2 / n_pairs)) / n_pairs
            ci_low = round(max(-1.0, delta - z * se), 4)
            ci_high = round(min(1.0, delta + z * se), 4)
            delta = round(delta, 4)
            ci_method = "mcnemar_wald"

        verdict = (
            "statistically significant"
            if significant
            else "not statistically significant"
        )
        if delta is not None:
            interpretation = (
                f"Treatment helped c={c} item(s) and hurt b={b} (n={n_pairs} paired). "
                f"McNemar exact two-sided p={round(p_exact, 4)} — {verdict} at {conf_pct}%. "
                f"Net delta {round(delta * 100, 1):+}pp."
            )
        else:
            interpretation = (
                f"Treatment helped c={c} item(s) and hurt b={b}. McNemar exact two-sided "
                f"p={round(p_exact, 4)} — {verdict} at {conf_pct}%. Provide n or the full 2x2 "
                f"table for a delta and CI."
            )

        out = {
            "operation": "mcnemar_paired",
            "n_pairs": n_pairs,
            "table": (
                {"n11": table[0], "n10": table[1], "n01": table[2], "n00": table[3]}
                if table is not None
                else None
            ),
            "discordant_hurt_b": b,
            "discordant_helped_c": c,
            "p_a": round(p_a, 4) if p_a is not None else None,
            "p_b": round(p_b, 4) if p_b is not None else None,
            "p_a_pct": round(p_a * 100, 1) if p_a is not None else None,
            "p_b_pct": round(p_b * 100, 1) if p_b is not None else None,
            "delta": delta,
            "delta_pct": round(delta * 100, 1) if delta is not None else None,
            "p_exact": round(p_exact, 4),
            "chi2_cc": round(chi2, 3),
            "p_chi2_cc": round(p_cc, 4),
            "ci_method": ci_method,
            "ci_low": ci_low,
            "ci_high": ci_high,
            "ci_low_pct": round(ci_low * 100, 1) if ci_low is not None else None,
            "ci_high_pct": round(ci_high * 100, 1) if ci_high is not None else None,
            "significant": significant,
            "confidence": confidence,
            "pooling_warning": _POOLING_WARNING,
            "interpretation": interpretation,
        }
        return ToolCallResult(output=json.dumps(out, ensure_ascii=False))


# ---------------------------------------------------------------------------
# compare_paired (continuous / count metrics)
# ---------------------------------------------------------------------------

_COMPARE_PAIRED_DESCRIPTION = """Compare two paired numeric arrays from the SAME matched cases — for continuous or count metrics (latency, tokens, cost, tool-call counts, mean-of-per-case scores), NOT binary pass/fail (use mcnemar_paired for those). Use this INSTEAD of eyeballing means. Pass values_a (baseline) and values_b (treatment), positionally paired so values_a[i] and values_b[i] are the same case. Returns the mean paired difference, a paired-bootstrap confidence interval, a Wilcoxon signed-rank p-value, and a boolean `significant`. Confidence defaults to 0.95."""


def _clean_pairs(values_a, values_b) -> tuple[list[float], list[float]]:
    """Drop pairs where either side is None / NaN / non-numeric. Returns (a, b)."""
    a_out: list[float] = []
    b_out: list[float] = []
    for a, b in zip(values_a, values_b):
        if a is None or b is None:
            continue
        try:
            fa, fb = float(a), float(b)
        except (TypeError, ValueError):
            continue
        if fa != fa or fb != fb:  # NaN
            continue
        a_out.append(fa)
        b_out.append(fb)
    return a_out, b_out


class ComparePairedTool(KilnTool):
    def __init__(self) -> None:
        super().__init__(
            tool_id=KilnBuiltInToolId.COMPARE_PAIRED,
            name="compare_paired",
            description=_COMPARE_PAIRED_DESCRIPTION,
            parameters_schema={
                "type": "object",
                "properties": {
                    "values_a": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Per-case baseline values. values_a[i] and values_b[i] must be the same case.",
                    },
                    "values_b": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Per-case treatment values, positionally paired with values_a.",
                    },
                    "confidence": _CONFIDENCE_SCHEMA,
                },
                "required": ["values_a", "values_b"],
            },
        )

    async def run(
        self, context: ToolCallContext | None = None, **kwargs
    ) -> ToolCallResult:
        _ = context
        try:
            values_a = kwargs.get("values_a")
            values_b = kwargs.get("values_b")
            if not isinstance(values_a, list) or not isinstance(values_b, list):
                raise ValueError("'values_a' and 'values_b' must be arrays.")
            if len(values_a) != len(values_b):
                raise ValueError(
                    f"Paired arrays must be equal length (got {len(values_a)} vs {len(values_b)})."
                )
            confidence = float(kwargs.get("confidence", 0.95))
            if not (0.0 < confidence < 1.0):
                raise ValueError(f"confidence must be in (0,1) (got {confidence}).")
        except (ValueError, TypeError) as e:
            return _error(str(e))

        n_pairs = len(values_a)
        a, b = _clean_pairs(values_a, values_b)
        n_used = len(a)
        conf_pct = round(confidence * 100)

        if n_used == 0:
            out = {
                "operation": "compare_paired",
                "n_pairs": n_pairs,
                "n_pairs_used": 0,
                "mean_a": None,
                "mean_b": None,
                "mean_delta": None,
                "significant": None,
                "confidence": confidence,
                "explanation": "No usable paired values after dropping missing/non-numeric rows.",
                "interpretation": "No usable paired values — nothing to compare.",
            }
            return ToolCallResult(output=json.dumps(out, ensure_ascii=False))

        diffs = [bv - av for av, bv in zip(a, b)]
        mean_a = statistics.mean(a)
        mean_b = statistics.mean(b)
        boot = paired_bootstrap_diff_ci(a, b, confidence=confidence)
        assert boot is not None  # n_used > 0, so never None
        mean_delta, ci_low, ci_high = boot
        wilcoxon_p = wilcoxon_signed_rank_p(diffs)

        wilcoxon_note = None
        if wilcoxon_p is not None:
            significant = wilcoxon_p < (1.0 - confidence)
        else:
            wilcoxon_note = (
                "Fewer than 5 non-zero paired differences; the Wilcoxon normal approximation "
                "is unreliable at this size, so its p-value is omitted. Significance below is "
                "based on the bootstrap CI."
            )
            significant = (ci_low > 0) or (ci_high < 0)

        verdict = "a significant" if significant else "no significant"
        interpretation = (
            f"Mean paired difference {round(mean_delta, 4):+} (n={n_used} usable pairs). "
            f"{conf_pct}% paired-bootstrap CI {round(ci_low, 4)} to {round(ci_high, 4)}"
            + (
                f"; Wilcoxon signed-rank p={round(wilcoxon_p, 4)}."
                if wilcoxon_p is not None
                else " (Wilcoxon omitted — <5 non-zero diffs)."
            )
            + f" Shows {verdict} shift."
        )

        out = {
            "operation": "compare_paired",
            "n_pairs": n_pairs,
            "n_pairs_used": n_used,
            "mean_a": round(mean_a, 4),
            "mean_b": round(mean_b, 4),
            "mean_delta": round(mean_delta, 4),
            "method": "paired_bootstrap + wilcoxon_signed_rank",
            "ci_low": round(ci_low, 4),
            "ci_high": round(ci_high, 4),
            "wilcoxon_p": round(wilcoxon_p, 4) if wilcoxon_p is not None else None,
            "wilcoxon_note": wilcoxon_note,
            "significant": significant,
            "confidence": confidence,
            "interpretation": interpretation,
        }
        return ToolCallResult(output=json.dumps(out, ensure_ascii=False))
