"""Built-in statistics tool: confidence intervals and significance tests.

One tool (``statistics``) with an ``operation`` discriminator, so a Kiln agent
computes standard errors, confidence intervals, and significance reliably
instead of doing the arithmetic in its own reasoning. The pure math lives in
``stats_lib.py``; this module dispatches to it per operation.

Each operation takes one natural input form (no alternative encodings):
- "proportion_ci": a proportion + n          -> Wilson CI + standard error
- "compare_proportions": two proportions + their n -> unpaired difference + significance
- "mcnemar_paired": two aligned 0/1 arrays    -> paired McNemar test
- "compare_paired": two paired numeric arrays -> paired bootstrap + Wilcoxon
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

_POOLING_WARNING = (
    "Do not pool the same items across multiple run configs/formats — that double-counts "
    "each item and is anti-conservative. Run one paired test per condition pair, or use an "
    "item-level (cluster-correct) analysis offline."
)


def _error(msg: str) -> ToolCallResult:
    return ToolCallResult(
        output=json.dumps({"error": msg}, ensure_ascii=False),
        is_error=True,
        error_message=msg,
    )


def _successes(proportion, n: int, label: str = "proportion") -> int:
    """Integer success count from a proportion + n (rounded, clamped to [0, n])."""
    if proportion is None:
        raise ValueError(f"'{label}' is required.")
    try:
        p = float(proportion)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a number (got {proportion!r}).")
    if not (0.0 <= p <= 1.0):
        raise ValueError(f"{label} must be in [0,1] (got {p}).")
    return max(0, min(n, round(p * n)))


def _require_n(value, label: str) -> int:
    if value is None:
        raise ValueError(f"'{label}' (sample size) is required.")
    n = int(value)
    if n <= 0:
        raise ValueError(f"{label} must be a positive integer (got {n}).")
    return n


# ---------------------------------------------------------------------------
# operation: proportion_ci
# ---------------------------------------------------------------------------


def _op_proportion_ci(kwargs) -> ToolCallResult:
    try:
        n = _require_n(kwargs.get("n"), "n")
        confidence = float(kwargs.get("confidence", 0.95))
        successes = _successes(kwargs.get("proportion"), n)
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
# operation: compare_proportions (unpaired)
# ---------------------------------------------------------------------------


def _op_compare_proportions(kwargs) -> ToolCallResult:
    try:
        n_a = _require_n(kwargs.get("n_a"), "n_a")
        n_b = _require_n(kwargs.get("n_b"), "n_b")
        confidence = float(kwargs.get("confidence", 0.95))
        s_a = _successes(kwargs.get("proportion_a"), n_a, "proportion_a")
        s_b = _successes(kwargs.get("proportion_b"), n_b, "proportion_b")
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
        "statistically significant" if significant else "not statistically significant"
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
        "note": "Unpaired test (conservative). If both proportions come from the same eval items, use operation='mcnemar_paired' instead.",
        "interpretation": (
            f"Treatment {round(p_b * 100, 1)}% vs baseline {round(p_a * 100, 1)}% "
            f"(delta {round(delta * 100, 1):+}pp). {conf_pct}% Newcombe CI "
            f"{round(low * 100, 1):+}pp to {round(high * 100, 1):+}pp — {verdict} "
            f"(unpaired test)."
        ),
    }
    return ToolCallResult(output=json.dumps(out, ensure_ascii=False))


# ---------------------------------------------------------------------------
# operation: mcnemar_paired
# ---------------------------------------------------------------------------


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


def _table_from_outcomes(kwargs) -> tuple[int, int, int, int]:
    """Build the (n11, n10, n01, n00) 2x2 table from two aligned 0/1 arrays."""
    oa, ob = kwargs.get("outcomes_a"), kwargs.get("outcomes_b")
    if not isinstance(oa, list) or not isinstance(ob, list):
        raise ValueError("'outcomes_a' and 'outcomes_b' must be arrays of 0/1 values.")
    if len(oa) != len(ob):
        raise ValueError(
            f"Paired arrays must be equal length (got {len(oa)} vs {len(ob)})."
        )
    if len(oa) == 0:
        raise ValueError("Paired arrays are empty.")
    a = _coerce_binary(oa, "outcomes_a")
    b = _coerce_binary(ob, "outcomes_b")
    n11 = n10 = n01 = n00 = 0
    for x, y in zip(a, b):
        if x == 1 and y == 1:
            n11 += 1
        elif x == 1 and y == 0:
            n10 += 1
        elif x == 0 and y == 1:
            n01 += 1
        else:
            n00 += 1
    return (n11, n10, n01, n00)


def _op_mcnemar_paired(kwargs) -> ToolCallResult:
    try:
        confidence = float(kwargs.get("confidence", 0.95))
        z = z_for_confidence(confidence)
        n11, n10, n01, n00 = _table_from_outcomes(kwargs)
    except (ValueError, TypeError) as e:
        return _error(str(e))

    b, c = n10, n01  # discordant: a-pass/b-fail (hurt), a-fail/b-pass (helped)
    n_pairs = n11 + n10 + n01 + n00
    p_exact = mcnemar_exact_p(b, c)
    chi2, p_cc = mcnemar_chi2_cc(b, c)
    significant = p_exact < (1.0 - confidence)
    conf_pct = round(confidence * 100)

    p_a = (n11 + n10) / n_pairs
    p_b = (n11 + n01) / n_pairs
    diff_ci = paired_proportion_diff_ci(n11, n10, n01, n00, z)
    delta, ci_low, ci_high = diff_ci if diff_ci is not None else (None, None, None)

    verdict = (
        "statistically significant" if significant else "not statistically significant"
    )
    interpretation = (
        f"Treatment helped c={c} item(s) and hurt b={b} (n={n_pairs} paired). "
        f"McNemar exact two-sided p={round(p_exact, 4)} — {verdict} at {conf_pct}%."
    )
    if delta is not None:
        interpretation += f" Net delta {round(delta * 100, 1):+}pp."

    out = {
        "operation": "mcnemar_paired",
        "n_pairs": n_pairs,
        "table": {"n11": n11, "n10": n10, "n01": n01, "n00": n00},
        "discordant_hurt_b": b,
        "discordant_helped_c": c,
        "p_a": round(p_a, 4),
        "p_b": round(p_b, 4),
        "p_a_pct": round(p_a * 100, 1),
        "p_b_pct": round(p_b * 100, 1),
        "delta": delta,
        "delta_pct": round(delta * 100, 1) if delta is not None else None,
        "p_exact": round(p_exact, 4),
        "chi2_cc": round(chi2, 3),
        "p_chi2_cc": round(p_cc, 4),
        "ci_method": "newcombe_paired" if diff_ci is not None else None,
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
# operation: compare_paired (continuous / count metrics)
# ---------------------------------------------------------------------------


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


def _op_compare_paired(kwargs) -> ToolCallResult:
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


# ---------------------------------------------------------------------------
# The tool
# ---------------------------------------------------------------------------

_OPERATIONS = {
    "proportion_ci": _op_proportion_ci,
    "compare_proportions": _op_compare_proportions,
    "mcnemar_paired": _op_mcnemar_paired,
    "compare_paired": _op_compare_paired,
}

_STATISTICS_DESCRIPTION = """Confidence intervals and significance tests on eval metrics — use this INSTEAD of computing standard errors or significance by hand in your reasoning. Set `operation`:

- "proportion_ci": confidence interval + standard error for ONE proportion (e.g. an "85% pass, n=200" cell). Params: `proportion` (a fraction in [0,1]) and `n`.
- "compare_proportions": difference of two INDEPENDENT proportions with a significance verdict (conservative — for marginals only). Params: `proportion_a`, `n_a`, `proportion_b`, `n_b`.
- "mcnemar_paired": the PAIRED test for two binary pass/fail conditions scored over the SAME items — more powerful than compare_proportions; prefer it when comparing run configs on one eval dataset. Params: `outcomes_a`, `outcomes_b` — two aligned 0/1 arrays (fetch per-item eval results and pair on dataset_id).
- "compare_paired": paired comparison of two numeric arrays for continuous/count metrics (latency, tokens, cost) — NOT binary pass/fail. Params: `values_a`, `values_b`.

Returns JSON with the statistic, a confidence interval, a boolean `significant`, and a one-sentence interpretation. `confidence` defaults to 0.95."""

_PARAMETERS_SCHEMA = {
    "type": "object",
    "properties": {
        "operation": {
            "type": "string",
            "enum": list(_OPERATIONS.keys()),
            "description": "Which test to run (see the tool description for the params each one takes).",
        },
        "confidence": _CONFIDENCE_SCHEMA,
        # proportion_ci
        "proportion": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
            "description": "[proportion_ci] the proportion as a fraction in [0,1] (e.g. 0.85).",
        },
        "n": {
            "type": "integer",
            "minimum": 1,
            "description": "[proportion_ci] sample size (> 0).",
        },
        # compare_proportions
        "proportion_a": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
            "description": "[compare_proportions] baseline proportion in [0,1].",
        },
        "n_a": {
            "type": "integer",
            "minimum": 1,
            "description": "[compare_proportions] baseline sample size (> 0).",
        },
        "proportion_b": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
            "description": "[compare_proportions] treatment proportion in [0,1].",
        },
        "n_b": {
            "type": "integer",
            "minimum": 1,
            "description": "[compare_proportions] treatment sample size (> 0).",
        },
        # mcnemar_paired
        "outcomes_a": {
            "type": "array",
            "items": {"type": "number"},
            "description": "[mcnemar_paired] per-item baseline outcomes (0=fail, 1=pass). outcomes_a[i] and outcomes_b[i] must be the SAME item.",
        },
        "outcomes_b": {
            "type": "array",
            "items": {"type": "number"},
            "description": "[mcnemar_paired] per-item treatment outcomes (0/1), positionally paired with outcomes_a.",
        },
        # compare_paired
        "values_a": {
            "type": "array",
            "items": {"type": ["number", "null"]},
            "description": "[compare_paired] per-case baseline values (null allowed — that pair is skipped). values_a[i] and values_b[i] must be the same case.",
        },
        "values_b": {
            "type": "array",
            "items": {"type": ["number", "null"]},
            "description": "[compare_paired] per-case treatment values (null allowed), positionally paired with values_a.",
        },
    },
    "required": ["operation"],
}


class StatisticsTool(KilnTool):
    """Confidence intervals + significance tests, dispatched by an ``operation`` param."""

    def __init__(self) -> None:
        super().__init__(
            tool_id=KilnBuiltInToolId.STATISTICS,
            name="statistics",
            description=_STATISTICS_DESCRIPTION,
            parameters_schema=_PARAMETERS_SCHEMA,
        )

    async def run(
        self, context: ToolCallContext | None = None, **kwargs
    ) -> ToolCallResult:
        _ = context
        operation = kwargs.get("operation")
        handler = _OPERATIONS.get(operation) if isinstance(operation, str) else None
        if handler is None:
            return _error(
                f"'operation' must be one of {sorted(_OPERATIONS)} (got {operation!r})."
            )
        return handler(kwargs)
