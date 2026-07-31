// Scoring for open-ended quantities - cost, latency, token counts, tool call
// counts - which have no absolute range to plot against. Almost all of them are
// better the smaller they get; a few (cache reuse) are the other way round, and
// `higherIsBetter` is the only thing that differs.
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
  /**
   * Set for the rare metric whose good end is the top of the scale - cached
   * tokens, where a bigger number is more of the prompt read from cache instead
   * of paid for again. Only the direction flips: the spread-based compression
   * below still measures the same spread, so two axes over the same numbers
   * stay mirror images rather than differently compressed.
   */
  higherIsBetter?: boolean
}

/**
 * Position of `value` within `values`, as a 0-100 score where higher is always
 * better. Lower raw values score highest unless `higherIsBetter` is set. Ties,
 * an empty set, or a single value all land at 50.
 */
export function relative_metric_score(
  value: number,
  values: number[],
  {
    padding = 10,
    relFull = 0.7,
    higherIsBetter = false,
  }: RelativeMetricScoreOptions = {},
): number {
  if (values.length === 0) {
    return 50
  }
  const lo = Math.min(...values)
  const hi = Math.max(...values)

  const range = hi - lo
  if (range <= 0) return 50

  // 1) range-based normalized position, pointed at the good end
  const t = (value - lo) / range
  const position = higherIsBetter ? t : 1 - t

  // 2) raw padded linear score (best value = highest score)
  const raw = padding + position * (100 - 2 * padding)

  // 3) compress based on range relative to magnitude ("scale from zero")
  const scale = Math.max(Math.abs(hi), 1e-12)
  const relRange = range / scale // e.g. 0.02..0.03 => 0.01/0.03 ≈ 0.33
  const k = Math.max(0, Math.min(1, relRange / relFull)) // small relRange -> k<1 -> compress

  // 4) mix toward midpoint
  const score = 50 + k * (raw - 50)

  return Math.max(0, Math.min(100, score))
}
