// Scoring for "less is better" quantities - cost, latency, token counts, tool
// call counts - which have no absolute range to plot against.
//
// A radar axis needs a bounded scale where further from the centre is better.
// A pass rate already has one (0-1). Cost does not: there is no "maximum cost"
// to normalize against, and the useful question is never "how close to zero is
// this config" but "how does it compare to the others on the chart". So these
// quantities are scored by their position within the selected run configs, on a
// shared 0-100 axis, with the lowest raw value scoring highest.
//
// That makes the score a comparison, with two consequences worth stating:
//   - it only carries information when there are at least two configs to
//     compare. A single config (or an exact tie) lands at 50 - no better, no
//     worse - and callers are expected to refuse to draw that rather than
//     present a flat shape as a result.
//   - it is relative in every axis mode. There is no "full scale" version of
//     "cheaper than the alternatives".
//
// Extracted from compare_radar_chart.svelte so the metrics radar scores its
// axes exactly the way the usage axes on the eval-score radar are scored,
// rather than growing a second, subtly different definition of "better".

export interface RelativeMetricScoreOptions {
  /** Keeps the best and worst endpoints away from a bare 0 / 100 */
  padding?: number
  /**
   * When the spread (hi-lo)/|hi| reaches this, the full padded range is used.
   * Below it the scores are compressed towards the midpoint, so configs that
   * are within a percent of each other don't get drawn as opposites.
   */
  relFull?: number
}

/**
 * Position of a lower-is-better `value` within `values`, as a 0-100 score where
 * higher is better. Ties, an empty set, or a single value all land at 50.
 */
export function relative_metric_score(
  value: number,
  values: number[],
  { padding = 10, relFull = 0.7 }: RelativeMetricScoreOptions = {},
): number {
  if (values.length === 0) {
    return 50
  }
  const lo = Math.min(...values)
  const hi = Math.max(...values)

  const range = hi - lo
  if (range <= 0) return 50

  // 1) range-based normalized position
  const t = (value - lo) / range

  // 2) raw padded linear score (lower value = higher score)
  const raw = padding + (1 - t) * (100 - 2 * padding)

  // 3) compress based on range relative to magnitude ("scale from zero")
  const scale = Math.max(Math.abs(hi), 1e-12)
  const relRange = range / scale // e.g. 0.02..0.03 => 0.01/0.03 ≈ 0.33
  const k = Math.max(0, Math.min(1, relRange / relFull)) // small relRange -> k<1 -> compress

  // 4) mix toward midpoint
  const score = 50 + k * (raw - 50)

  return Math.max(0, Math.min(100, score))
}
