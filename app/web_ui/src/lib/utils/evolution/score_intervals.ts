// Confidence intervals for eval scores.
//
// A mean over 25 runs is not a number, it is an estimate, and at the sample
// sizes evals actually run at the interval around it is wide - a pass rate of
// 0.5 over 25 runs carries a 95% interval roughly 36 points wide, better than a
// third of the axis. A chart that draws the mean as a point asserts a precision
// the data does not have, which is how two configs that differ by nothing come
// to look different.
//
// Only `pass_fail` gets an interval here, and the restriction is deliberate:
// its scores are Bernoulli (each run is 0 or 1), so the mean IS a proportion
// and Wilson applies exactly. The other score types are means over a range -
// `five_star` over 1..5, `pass_fail_critical` over {-1, 0, 1} - where a
// proportion interval would be wrong, and the spread needed for the right one
// (a standard deviation) is not in the summary payload. Those axes plot their
// point estimate with no band rather than a band that lies.

import type { components } from "$lib/api_schema"

type ScoreType = components["schemas"]["TaskOutputRatingType"]

/** 95% two-sided normal quantile. */
export const Z_95 = 1.959963984540054

export interface Interval {
  /** Point estimate (the mean itself). */
  value: number
  /** Lower bound, clamped to the score's range. */
  lower: number
  /** Upper bound, clamped to the score's range. */
  upper: number
  /** Runs behind the estimate. */
  n: number
}

/**
 * Whether an interval can be computed for this score type at all. See the file
 * header: Bernoulli scores only.
 */
export function supports_interval(type: ScoreType | null): boolean {
  return type === "pass_fail"
}

/**
 * Wilson score interval for a binomial proportion.
 *
 * Wilson rather than the textbook normal approximation because eval results sit
 * exactly where the normal approximation fails: small n, and rates that pin to
 * the boundary. A config that passes 25 of 25 has a real upper bound of 1 and a
 * lower bound near 0.87 - the normal approximation returns the degenerate
 * [1, 1], which reads as certainty earned by a sample of 25.
 *
 * Returns null when there is nothing to interval: no runs, or a proportion
 * outside [0, 1] (which would mean the caller handed us a non-Bernoulli score).
 */
export function wilson_interval(p: number, n: number): Interval | null {
  if (!Number.isFinite(p) || !Number.isFinite(n) || n <= 0) return null
  if (p < 0 || p > 1) return null

  const z2 = Z_95 * Z_95
  const denominator = 1 + z2 / n
  const center = (p + z2 / (2 * n)) / denominator
  const spread =
    (Z_95 / denominator) * Math.sqrt((p * (1 - p)) / n + z2 / (4 * n * n))

  return {
    value: p,
    // The bounds are exact at the boundaries - an all-pass sample cannot rule
    // out a true rate of 1 - but the closed form lands a float's breadth short
    // (0.9999999999999999), which would leave a hairline gap between a perfect
    // score's band and the top of its axis. Pin those two cases.
    lower: p === 0 ? 0 : Math.max(0, center - spread),
    upper: p === 1 ? 1 : Math.min(1, center + spread),
    n,
  }
}

/**
 * Interval for a score mean, expressed in the score's own units.
 *
 * `mean` arrives in score units (a pass_fail mean is already 0..1, which is
 * both its unit range and its proportion), so no rescaling is needed today.
 * Kept as its own function so the score-type gate lives in one place and the
 * caller never has to know which types are intervalable.
 */
export function score_interval(
  mean: number | null | undefined,
  n: number | null | undefined,
  type: ScoreType | null,
): Interval | null {
  if (!supports_interval(type)) return null
  if (typeof mean !== "number" || typeof n !== "number") return null
  return wilson_interval(mean, n)
}

/**
 * Half-width of an interval in percentage points, for prose like "±18pp".
 * Wilson intervals are asymmetric around the mean near the boundaries, so this
 * is the average half-width - use the bounds themselves when precision matters.
 */
export function interval_half_width_pp(interval: Interval): number {
  return ((interval.upper - interval.lower) / 2) * 100
}
