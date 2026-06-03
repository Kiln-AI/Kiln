"""Pure statistical helpers — no I/O, no globals, stdlib only (math/random/statistics).

Confidence intervals (Wilson, Newcombe), bootstrap difference CIs, the McNemar test
for paired binary outcomes, the Wilcoxon signed-rank test, and small helpers
(inverse-normal z, percentiles). Dependency-free (no numpy/scipy) so it ships in
kiln-core with no new requirements. These functions back the built-in statistics
tools (stats_tools.py) that Kiln agents call instead of hand-computing standard
errors and significance.
"""

from __future__ import annotations

import math
import random
import statistics
from typing import Iterable, Sequence


def wilson_ci(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion.

    Returns (low, high) clamped to [0, 1] and rounded to 3 decimals. Returns
    (0.0, 0.0) when total==0 — a deliberate choice to keep the function pure;
    the caller decides whether to surface the empty interval as `None`.
    """
    if total == 0:
        return (0.0, 0.0)
    p = successes / total
    denom = 1 + z**2 / total
    center = (p + z**2 / (2 * total)) / denom
    margin = (z / denom) * math.sqrt(p * (1 - p) / total + z**2 / (4 * total**2))
    return (round(max(0, center - margin), 3), round(min(1, center + margin), 3))


def _wilson_ci_unrounded(
    successes: int, total: int, z: float = 1.96
) -> tuple[float, float]:
    """Same as wilson_ci but without the rounding step — needed by
    wilson_difference_ci so the difference interval composes cleanly
    instead of inheriting rounding error from each side."""
    if total == 0:
        return (0.0, 0.0)
    p = successes / total
    denom = 1 + z**2 / total
    center = (p + z**2 / (2 * total)) / denom
    margin = (z / denom) * math.sqrt(p * (1 - p) / total + z**2 / (4 * total**2))
    return (max(0.0, center - margin), min(1.0, center + margin))


def wilson_difference_ci(
    successes_a: int,
    total_a: int,
    successes_b: int,
    total_b: int,
    z: float = 1.96,
) -> tuple[float, float, float] | None:
    """Newcombe hybrid score interval for the difference of two proportions.

    Returns ``(delta, low, high)`` where ``delta = p_b - p_a`` and ``[low,
    high]`` is the (1 - 2 * (1 - Φ(z)))-confidence interval on that delta.
    With ``z=1.96`` (default) that's the standard 95% CI. Returns ``None``
    when either side has ``total == 0`` — the caller decides whether to
    render an empty cell or skip the row.

    Reference: Newcombe (1998), "Interval Estimation for the Difference
    Between Independent Proportions: Comparison of Eleven Methods",
    Method 10. Composes two Wilson intervals into one for the difference
    — robust at extreme proportions (near 0 or 1) where the simple
    normal-approximation Wald interval misbehaves.

    Sign convention: ``p_b - p_a`` matches the rendering convention where
    ``b`` is the newer / right-hand run in a compare table — positive
    delta = b improved over a.
    """
    if total_a == 0 or total_b == 0:
        return None
    p_a = successes_a / total_a
    p_b = successes_b / total_b
    l_a, u_a = _wilson_ci_unrounded(successes_a, total_a, z)
    l_b, u_b = _wilson_ci_unrounded(successes_b, total_b, z)
    delta = p_b - p_a
    low = delta - math.sqrt((p_b - l_b) ** 2 + (u_a - p_a) ** 2)
    high = delta + math.sqrt((u_b - p_b) ** 2 + (p_a - l_a) ** 2)
    return (round(delta, 4), round(max(-1.0, low), 4), round(min(1.0, high), 4))


def _deterministic_seed(*ints: int) -> int:
    """Pack integers into a stable 64-bit seed.

    ``hash(tuple)`` is randomized per-process under PYTHONHASHSEED, which
    would defeat the goal of "same inputs → same CI across runs." Bit-
    pack the inputs ourselves (each clamped to 16 bits — sample
    counts never approach 65k) so the seed is a pure deterministic
    function of the inputs.
    """
    seed = 0
    for i, v in enumerate(ints):
        seed |= (int(v) & 0xFFFF) << (16 * i)
    return seed


def bootstrap_difference_ci(
    successes_a: int,
    total_a: int,
    successes_b: int,
    total_b: int,
    *,
    n_resamples: int = 10000,
    confidence: float = 0.95,
    seed: int | None = None,
) -> tuple[float, float, float] | None:
    """Percentile-bootstrap CI for the difference of two binomial proportions.

    Returns ``(delta, low, high)`` with ``delta = p_b - p_a`` and ``[low,
    high]`` the percentile interval at the requested confidence. Returns
    ``None`` when either side has ``total == 0`` (matches
    ``wilson_difference_ci``'s contract so callers can swap them).

    Resamples each side independently with replacement (unpaired). For
    mid-range proportions with n≥30 this agrees closely with Newcombe;
    the win is generality — the same resampling routine extends to
    medians, ratios, and cluster-bootstrap variants where Newcombe has
    no analog.

    Caveat: percentile bootstrap is poorly calibrated at extreme
    proportions (s == 0 or s == n) — the resampled distribution
    collapses toward a point and the CI under-states small-sample
    uncertainty. ``wilson_difference_ci`` is the better choice in that
    regime; both functions live here so callers can pick per metric.

    Determinism: when ``seed`` is None, the seed is derived from the
    input tuple so identical ``(s_a, n_a, s_b, n_b)`` calls return
    bit-identical CIs across processes. Pass ``seed`` explicitly to
    override (e.g., to deliberately vary the resample draw).
    """
    if total_a == 0 or total_b == 0:
        return None
    if not (0.0 < confidence < 1.0):
        raise ValueError(f"confidence must be in (0, 1), got {confidence}")
    if n_resamples < 1:
        raise ValueError(f"n_resamples must be >= 1, got {n_resamples}")
    if seed is None:
        seed = _deterministic_seed(successes_a, total_a, successes_b, total_b)
    rng = random.Random(seed)
    p_a = successes_a / total_a
    p_b = successes_b / total_b
    # ``random.binomialvariate`` is 3.12+, but the codebase still has to
    # run under older interpreters in CI. Sum bernoulli draws ourselves —
    # at our N (≲200) and n_resamples=10k that's ~4M random() calls,
    # ~150ms in CPython. Fine for a once-per-row CI computation.
    rand = rng.random
    deltas: list[float] = [0.0] * n_resamples
    for i in range(n_resamples):
        sr_a = sum(1 for _ in range(total_a) if rand() < p_a)
        sr_b = sum(1 for _ in range(total_b) if rand() < p_b)
        deltas[i] = sr_b / total_b - sr_a / total_a
    deltas.sort()
    alpha = (1.0 - confidence) / 2.0
    low_idx = math.floor(alpha * n_resamples)
    high_idx = min(math.ceil((1.0 - alpha) * n_resamples) - 1, n_resamples - 1)
    delta = p_b - p_a
    return (
        round(delta, 4),
        round(max(-1.0, deltas[low_idx]), 4),
        round(min(1.0, deltas[high_idx]), 4),
    )


def paired_bootstrap_diff_ci(
    a_values: Sequence[float],
    b_values: Sequence[float],
    *,
    n_resamples: int = 10000,
    confidence: float = 0.95,
    seed: int | None = None,
) -> tuple[float, float, float] | None:
    """Percentile-bootstrap CI on the mean of paired differences (b_i - a_i).

    Returns ``(mean_delta, low, high)`` where ``mean_delta = mean(b_i - a_i)``
    and ``[low, high]`` is the percentile interval at the requested
    confidence on that mean. Returns ``None`` when the paired arrays are
    empty after dropping rows where either side is None / NaN.

    Pairing is positional: ``a_values[i]`` and ``b_values[i]`` MUST come
    from the same matched case. Unpaired comparison would resample each
    side independently and inflate the variance estimate by the
    between-case variance — exactly the noise paired analysis is meant
    to remove.

    Determinism: when ``seed`` is None, the seed is derived from the
    input lengths and a checksum of the difference vector so identical
    inputs return bit-identical CIs across processes. Pass ``seed``
    explicitly to override.

    Use this for any per-case scalar metric (wall-clock, tokens, cost,
    tool-call counts, mean-of-per-case proportions like knowledge
    coverage). For binomial pass-rates the paired version of the
    proportion difference is McNemar territory; use ``mcnemar_exact_p``
    / ``paired_proportion_diff_ci`` for those.
    """
    if len(a_values) != len(b_values):
        raise ValueError(
            f"paired_bootstrap_diff_ci: paired sequences must be same length; "
            f"got len(a)={len(a_values)}, len(b)={len(b_values)}"
        )
    if not (0.0 < confidence < 1.0):
        raise ValueError(f"confidence must be in (0, 1), got {confidence}")
    if n_resamples < 1:
        raise ValueError(f"n_resamples must be >= 1, got {n_resamples}")

    diffs: list[float] = []
    for a, b in zip(a_values, b_values):
        if a is None or b is None:
            continue
        try:
            d = float(b) - float(a)
        except (TypeError, ValueError):
            continue
        if d != d:  # NaN
            continue
        diffs.append(d)

    n = len(diffs)
    if n == 0:
        return None
    mean_delta = sum(diffs) / n

    if seed is None:
        # Hash the diff vector deterministically — len + a checksum of the
        # quantized values. We round to keep tiny FP variation from
        # changing the seed across machines.
        seed_int = _deterministic_seed(
            n,
            sum(round(d * 1e6) & 0xFFFF for d in diffs) & 0xFFFF,
        )
    else:
        seed_int = seed
    rng = random.Random(seed_int)

    means: list[float] = [0.0] * n_resamples
    rand_int = rng.randrange
    for i in range(n_resamples):
        s = 0.0
        for _ in range(n):
            s += diffs[rand_int(n)]
        means[i] = s / n
    means.sort()
    alpha = (1.0 - confidence) / 2.0
    low_idx = math.floor(alpha * n_resamples)
    high_idx = min(math.ceil((1.0 - alpha) * n_resamples) - 1, n_resamples - 1)
    return (mean_delta, means[low_idx], means[high_idx])


def wilcoxon_signed_rank_p(diffs: Sequence[float]) -> float | None:
    """Two-sided p-value from the Wilcoxon signed-rank test on paired diffs.

    Drops zero-differences before ranking (the standard Wilcoxon
    pre-treatment) and uses the large-n normal approximation with a
    continuity correction. Returns ``None`` when fewer than 5 non-zero
    diffs remain — at that size the normal approximation breaks down
    and an exact-permutation table is needed; surface ``None`` rather
    than render a misleading p.

    The variance term omits the tie-correction factor, so the test is
    slightly conservative (p-values marginally inflated) when tied absolute
    differences are present — results can differ slightly from
    ``scipy.stats.wilcoxon``, which applies that correction.

    Non-parametric, robust to outliers, and the natural companion to
    ``paired_bootstrap_diff_ci`` for "did treatment systematically
    shift this metric?" — sign matters but distribution shape doesn't.
    """
    nz = [float(d) for d in diffs if d is not None and d != 0]
    n = len(nz)
    if n < 5:
        return None

    # Rank by absolute magnitude; resolve ties with average rank.
    indexed = sorted(enumerate(nz), key=lambda x: abs(x[1]))
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and abs(indexed[j + 1][1]) == abs(indexed[i][1]):
            j += 1
        avg_rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg_rank
        i = j + 1

    w_plus = sum(r for r, d in zip(ranks, nz) if d > 0)
    mu = n * (n + 1) / 4.0
    sigma = math.sqrt(n * (n + 1) * (2 * n + 1) / 24.0)
    if sigma == 0:
        return None
    # Continuity correction: shrink |W - mu| toward 0 by 0.5, clamped at 0 so
    # a perfectly symmetric sample (w_plus == mu) gives z = 0 / p = 1.0 instead
    # of overshooting via copysign(0.5, 0.0) == 0.5 (and never flips sign when
    # |W - mu| < 0.5).
    num = w_plus - mu
    z = math.copysign(max(0.0, abs(num) - 0.5), num) / sigma
    # Two-sided p-value from standard normal.
    p = 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(z) / math.sqrt(2.0))))
    return min(1.0, max(0.0, p))


def min_med_max(
    values: Sequence[float],
) -> tuple[float | None, float | None, float | None]:
    """Return (min, median, max) or (None, None, None) for an empty sequence.

    Median uses statistics.median (not mean of middle two for odd-length).
    """
    if not values:
        return (None, None, None)
    return (min(values), statistics.median(values), max(values))


def percentile(values: Sequence[float], p: float) -> float | None:
    """p ∈ [0, 100]. Linear interpolation between order statistics.

    Returns `None` for empty input. Mirrors numpy.percentile's default
    interpolation but without the numpy dependency.
    """
    if not values:
        return None
    if not (0 <= p <= 100):
        raise ValueError(f"percentile p must be in [0, 100], got {p}")
    s = sorted(values)
    n = len(s)
    if n == 1:
        return s[0]
    k = (n - 1) * (p / 100.0)
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return float(s[lo])
    return float(s[lo] + (s[hi] - s[lo]) * (k - lo))


def mean_or_none(values: Iterable[float]) -> float | None:
    """statistics.mean but returns None on empty input rather than raising."""
    vs = list(values)
    if not vs:
        return None
    return statistics.mean(vs)


# ---------------------------------------------------------------------------
# Inverse-normal z, McNemar test, and paired-proportion difference CI.
# ---------------------------------------------------------------------------


def _inv_norm_cdf(p: float) -> float:
    """Inverse standard-normal CDF (probit) via Acklam's rational approximation.

    |absolute error| < 1.15e-9 over p ∈ (0, 1). Pure stdlib, used to turn an
    arbitrary confidence level into the z multiplier the Wilson functions take.
    """
    if not (0.0 < p < 1.0):
        raise ValueError(f"_inv_norm_cdf: p must be in (0, 1), got {p}")
    a = [
        -3.969683028665376e01,
        2.209460984245205e02,
        -2.759285104469687e02,
        1.383577518672690e02,
        -3.066479806614716e01,
        2.506628277459239e00,
    ]
    b = [
        -5.447609879822406e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    ]
    c = [
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e00,
        -2.549732539343734e00,
        4.374664141464968e00,
        2.938163982698783e00,
    ]
    d = [
        7.784695709041462e-03,
        3.224671290700398e-01,
        2.445134137142996e00,
        3.754408661907416e00,
    ]
    p_low = 0.02425
    p_high = 1.0 - p_low
    if p < p_low:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )
    if p <= p_high:
        q = p - 0.5
        r = q * q
        return (
            (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5])
            * q
            / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)
        )
    q = math.sqrt(-2.0 * math.log(1.0 - p))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
        (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
    )


def z_for_confidence(confidence: float) -> float:
    """Two-sided z multiplier for a confidence level. ``0.95 -> 1.95996``."""
    if not (0.0 < confidence < 1.0):
        raise ValueError(f"confidence must be in (0, 1), got {confidence}")
    return _inv_norm_cdf((1.0 + confidence) / 2.0)


def mcnemar_exact_p(b: int, c: int) -> float:
    """Exact two-sided McNemar p-value for paired binary outcomes.

    ``b`` and ``c`` are the discordant counts (one condition passed, the other
    failed, in each direction). The test is the exact binomial test on
    ``min(b, c)`` "successes" out of ``n = b + c`` trials with p=0.5, doubled
    for two-sidedness. This is the right call at small discordant counts — the
    regime paired comparisons over the same ~100-200 items fall into, where the
    normal/chi-square approximation is unreliable.

    Returns 1.0 when b+c == 0 (no discordant pairs — nothing to test).
    """
    n = b + c
    if n == 0:
        return 1.0
    k0 = min(b, c)
    tail = 0.0
    for k in range(0, k0 + 1):
        tail += math.comb(n, k) * (0.5**n)
    return min(1.0, 2.0 * tail)


def mcnemar_chi2_cc(b: int, c: int) -> tuple[float, float]:
    """McNemar chi-square with continuity correction (1 dof). Returns ``(chi2, p)``.

    Secondary to ``mcnemar_exact_p`` — reported alongside it as a sanity check,
    but the exact binomial is the significance driver at these sample sizes.
    """
    n = b + c
    if n == 0:
        return (0.0, 1.0)
    chi2 = (abs(b - c) - 1) ** 2 / n
    p = math.erfc(math.sqrt(chi2 / 2.0))
    return (chi2, p)


def paired_proportion_diff_ci(
    n11: int,
    n10: int,
    n01: int,
    n00: int,
    z: float = 1.96,
) -> tuple[float, float, float] | None:
    """Newcombe paired (MOVER) CI for the difference of two paired proportions.

    The 2x2 table classifies each paired item by (condition-A outcome,
    condition-B outcome):

    - ``n11`` both pass, ``n00`` both fail (concordant),
    - ``n10`` A pass / B fail, ``n01`` A fail / B pass (discordant).

    Returns ``(delta, low, high)`` where ``delta = p_b - p_a = (n01 - n10)/n``
    (positive = B better), composing the two marginal Wilson intervals with
    Newcombe's correlation estimate. Robust at small discordant counts where a
    Wald interval misbehaves — the companion CI to ``mcnemar_exact_p``. Returns
    ``None`` when the table is empty.

    Reference: Newcombe (1998), "Improved confidence intervals for the
    difference between binomial proportions based on paired data",
    Statistics in Medicine 17, Method 10.
    """
    n = n11 + n10 + n01 + n00
    if n == 0:
        return None
    succ_a = n11 + n10  # A passed
    succ_b = n11 + n01  # B passed
    p_a = succ_a / n
    p_b = succ_b / n
    delta = p_b - p_a
    l_a, u_a = _wilson_ci_unrounded(succ_a, n, z)
    l_b, u_b = _wilson_ci_unrounded(succ_b, n, z)
    # Newcombe's correlation estimate from the 2x2 table.
    a_term = n11 * n00 - n10 * n01
    denom = math.sqrt(
        max(0.0, float(succ_a) * (n01 + n00) * float(succ_b) * (n10 + n00))
    )
    if denom == 0:
        phi = 0.0
    elif a_term - n / 2.0 > 0:
        phi = (a_term - n / 2.0) / denom
    elif a_term >= 0:
        phi = 0.0
    else:
        phi = a_term / denom
    phi = max(-1.0, min(1.0, phi))
    lower_var = (
        (p_a - l_a) ** 2 - 2 * phi * (p_a - l_a) * (u_b - p_b) + (u_b - p_b) ** 2
    )
    upper_var = (
        (u_a - p_a) ** 2 - 2 * phi * (u_a - p_a) * (p_b - l_b) + (p_b - l_b) ** 2
    )
    low = delta - math.sqrt(max(0.0, lower_var))
    high = delta + math.sqrt(max(0.0, upper_var))
    return (round(delta, 4), round(max(-1.0, low), 4), round(min(1.0, high), 4))
