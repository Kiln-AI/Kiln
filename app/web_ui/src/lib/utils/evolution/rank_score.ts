// Putting a performance metric on the quality parallel chart, without lying
// about what it is.
//
// The parallel chart's axes are quality scores drawn as a share of their own
// full range (see parallel_bands): a pass/fail 0.44 is 44% of its axis because
// pass/fail RUNS 0 to 1. A metric has no such range. Nothing says what the top
// of a cost axis is, or the bottom of a latency one, so there is no fraction to
// take and no height a config could sit at that means anything on its own.
//
// The two obvious answers are both wrong here:
//
//   - min-max over the configs shown puts the best config at exactly 1.0 and
//     the worst at exactly 0.0 on EVERY metric axis, whatever the spread. Two
//     configs a hundredth of a cent apart draw the full height of the axis
//     between them, which is the chart claiming a difference that is not there.
//     It is also outlier-driven: one arm 27x the cost of the rest flattens the
//     other five onto the floor and the axis says only "one of these is
//     expensive" - the same failure the price chart's log axis exists to avoid.
//   - the raw value on a shared 0..1 axis is not comparable at all: $0.31 and
//     42,000ms have no common scale, which is why this chart normalizes in the
//     first place.
//
// So a metric axis carries the config's RANK among the configs currently drawn,
// mapped onto 0..1 with UP = BETTER, the same direction every other axis on the
// chart reads. Rank is the one normalization that survives an outlier (a config
// 27x more expensive is one step worse, not the whole axis) and that never
// claims a magnitude it cannot support: the axis says "cheapest of the six",
// and the tooltip carries the actual dollars.
//
// CAPPED, in two senses, and both matter for a chart that mixes these axes with
// pass/fail ones:
//
//   - the scores are bounded strictly INSIDE (0,1) - the midrank percentile
//     never reaches either end. On a pass/fail axis 0.0 and 1.0 are real,
//     earned states (nothing passed; everything passed), and a rank axis must
//     not be able to draw one. Best-of-N sits at 1 - 0.5/N, which is high on
//     the axis without claiming perfection, and a comparison of two configs
//     cannot manufacture a 0-to-1 sweep.
//   - the scale is capped at the comparison: it is a POSITION among the configs
//     on screen, not a score the config owns. Hiding a config in the legend
//     re-ranks the axis, on purpose, and the chart says so.
//
// This module is the arithmetic only. Which configs are in the comparison, and
// which direction a metric points, are the page's to decide (see
// MetricAxis.better in metric_axes).

/** One config's raw value on one metric. Null = not measured. */
export interface RankInput {
  /** Run config id; assumed unique within one call */
  id: string
  value: number | null
}

/** Which end of the RAW scale is the good one - MetricAxis.better */
export type RankDirection = "higher" | "lower"

/**
 * Capped rank scores for one metric over one comparison, keyed by run config id.
 *
 * Midrank percentile. The configs that have a value are ordered best-first
 * (which end is "best" is what `better` decides), given 1-based positions, and
 * every member of a tied run takes the AVERAGE of the positions that run
 * occupies - so tied configs cannot be drawn apart by an arbitrary tiebreak,
 * which is the whole reason midranks rather than dense or competition ranking.
 * The score is then
 *
 *     (n - rank + 0.5) / n
 *
 * where n is how many configs had a value. The half-step is what caps it: the
 * best possible score is 1 - 0.5/n and the worst is 0.5/n, so no rank axis ever
 * touches the 0 or 1 that a pass/fail axis reserves for catastrophe and
 * perfection. Some consequences worth knowing when reading one:
 *
 *   - n = 1 scores 0.5. One config has no rank; drawing it at either end would
 *     be an opinion the data has not got.
 *   - n = 2 scores 0.75 and 0.25, always, however far apart the values are.
 *     That is the point: it says which one won, and nothing about by how much.
 *   - a config with no value scores null, never 0. Zero is the worst rank on
 *     this axis and "we did not measure it" is not the worst rank; the chart
 *     draws a gap.
 *
 * Ids with no value are still present in the returned map (mapped to null), so
 * a caller can tell "in the comparison, unmeasured" from "not in the
 * comparison" - the second is an absent key.
 */
export function capped_rank_scores(
  values: RankInput[],
  better: RankDirection,
): Map<string, number | null> {
  const scores = new Map<string, number | null>()
  const measured: { id: string; value: number }[] = []
  for (const entry of values) {
    if (entry.value === null || !Number.isFinite(entry.value)) {
      scores.set(entry.id, null)
      continue
    }
    measured.push({ id: entry.id, value: entry.value })
  }

  const n = measured.length
  if (n === 0) {
    return scores
  }

  // Best first. Sorting a copy: the caller's array is theirs.
  const ordered = [...measured].sort((a, b) =>
    better === "higher" ? b.value - a.value : a.value - b.value,
  )

  let start = 0
  while (start < ordered.length) {
    // How far the run of equal values extends. Equality on the raw value, not
    // on a rounded one: two costs that differ in the tenth decimal are two
    // different costs, and the chart already refuses to say by how much.
    let end = start
    while (
      end + 1 < ordered.length &&
      ordered[end + 1].value === ordered[start].value
    ) {
      end += 1
    }
    // Positions are 1-based, so the run covers start+1 .. end+1
    const midrank = (start + 1 + (end + 1)) / 2
    const score = (n - midrank + 0.5) / n
    for (let index = start; index <= end; index += 1) {
      scores.set(ordered[index].id, score)
    }
    start = end + 1
  }

  return scores
}

/**
 * A rank score read back as the place it stands for: "2nd of 5".
 *
 * The rank is recoverable exactly - `rank = n + 0.5 - score * n` - which is
 * what makes the axis honest to hover: the reader is told the position, not
 * asked to infer it from a height. Tied configs share a half-step midrank
 * (1.5 for a two-way tie at the top), which reads as the tie it is rather than
 * as a rank nobody holds.
 *
 * Null when there is nothing to describe: no score (the config was not
 * measured), or an n that could not have produced this score - a stale pairing
 * of a score with the wrong comparison size, which is better left unsaid than
 * printed as "4th of 2".
 */
export function describe_rank(score: number | null, n: number): string | null {
  if (score === null || !Number.isFinite(score) || n <= 0) {
    return null
  }
  const rank = n + 0.5 - score * n
  // Midranks land on halves; the arithmetic above is float, so snap before
  // testing whether this is a whole rank or a tie.
  const snapped = Math.round(rank * 2) / 2
  if (snapped < 1 || snapped > n) {
    return null
  }
  if (Number.isInteger(snapped)) {
    return `${ordinal(snapped)} of ${n}`
  }
  return `tied ${ordinal(Math.floor(snapped))}–${ordinal(
    Math.ceil(snapped),
  )} of ${n}`
}

/** 1 -> "1st", 2 -> "2nd", 11 -> "11th" */
function ordinal(value: number): string {
  const teens = value % 100
  if (teens >= 11 && teens <= 13) {
    return `${value}th`
  }
  switch (value % 10) {
    case 1:
      return `${value}st`
    case 2:
      return `${value}nd`
    case 3:
      return `${value}rd`
    default:
      return `${value}th`
  }
}
