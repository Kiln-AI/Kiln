// The price/latency plane: what one conversation costs against how long it
// takes, for run configs that clear a quality floor.
//
// Every other chart on this page answers "which config is better", and answers
// it one quantity at a time. This one answers the question that is actually
// asked when a config is chosen to ship: fix the quality, then show the RANGE -
// how much slower, and how much more expensive, the good options are than each
// other. That is a trade-off between two costs, and a trade-off between two
// quantities is a scatter: neither one is the independent variable, and the
// interesting configs are the ones on the lower-left edge of the cloud.
//
// Quality is a GATE rather than a third axis. Encoding it as size or colour
// would invite reading a small improvement in quality against a large one in
// price, which is the comparison nobody can make honestly - the two have no
// exchange rate. A floor is a decision the reader states ("80% is good enough"),
// and everything above it is then comparable on price and speed alone. Configs
// below the floor stay on the chart, ghosted, because "the cheap one is cheap
// because it is bad" is exactly what the reader needs to see, and a chart that
// silently dropped them would look like the cheap arm never existed.
//
// The frontier is the set of configs nothing else beats on BOTH axes. It is
// drawn rather than left to the eye because dominance is a two-dimensional
// judgement that reads as "lower-left-ish" until it is marked; once it is, the
// points off the line are visibly paying for nothing.
//
// Pure functions, no echarts: everything here is decided from numbers, so it is
// tested from numbers. See compare_price_latency_chart.svelte for the drawing.

import { COST_KEY, LATENCY_KEY } from "./metric_axes"

/** One run config's position on the price/latency plane. */
export interface PricePoint {
  id: string
  /** Mean LLM generation time per conversation, in ms */
  latency_ms: number
  /**
   * Mean cost per conversation, in USD. Always finite and > 0 - the cost axis
   * is logarithmic, and a log scale has no position for zero.
   */
  cost: number
  /**
   * Direction-corrected aggregate quality, 0..1, or null when the config has
   * no scores behind it at all. Null is not zero: an unmeasured config is not
   * a bad one, which is why it is ghosted with its own wording rather than
   * plotted at the bottom of the gate.
   */
  quality: number | null
}

/** Why a selected run config could not be put on the plane at all. */
export type OmissionReason =
  | "missing_both"
  | "missing_cost"
  | "missing_latency"
  | "nonpositive_cost"

export interface OmittedPoint {
  id: string
  reason: OmissionReason
}

/**
 * How each omission reads in the footnote under the chart.
 *
 * Named rather than dropped, and named specifically. The server only reports a
 * usage rollup for a config it has the field on at least half its runs, so a
 * missing number here means "not enough runs recorded it", not "it was free" -
 * and a config plotted at zero because its cost never arrived would sit at the
 * cheapest point on the chart, which is the single most misleading place on it.
 */
export const OMISSION_LABELS: Record<OmissionReason, string> = {
  missing_both: "no cost or latency recorded",
  missing_cost: "no cost recorded",
  missing_latency: "no latency recorded",
  nonpositive_cost: "cost of zero, which a log scale cannot place",
}

/** Why a point is on the chart but not part of the comparison. */
export type GhostReason = "below_gate" | "no_quality"

export interface GhostedPoint extends PricePoint {
  reason: GhostReason
}

export const GHOST_LABELS: Record<GhostReason, string> = {
  below_gate: "below the quality gate",
  no_quality: "no quality score to check against the gate",
}

/** A comparison needs two sides; one point is a dot, not a trade-off. */
export const MIN_PRICE_LATENCY_POINTS = 2

function finite_positive(value: number | null): boolean {
  return value !== null && Number.isFinite(value) && value > 0
}

function finite_non_negative(value: number | null): boolean {
  return value !== null && Number.isFinite(value) && value >= 0
}

/**
 * The run configs that can be placed on the plane, and the ones that cannot
 * with the reason why.
 *
 * Both axes are required: a point is a pair, and a config with one of the two
 * has no position rather than a partial one. The order of `ids` is preserved
 * in both lists, so the footnote names configs in the same order the legend
 * above does.
 */
export function build_price_latency_points(
  ids: string[],
  getMetricValue: (runConfigId: string, key: string) => number | null,
  getQuality: (runConfigId: string) => number | null,
): { plotted: PricePoint[]; omitted: OmittedPoint[] } {
  const plotted: PricePoint[] = []
  const omitted: OmittedPoint[] = []

  for (const id of ids) {
    const cost = getMetricValue(id, COST_KEY)
    const latency = getMetricValue(id, LATENCY_KEY)
    const has_cost = cost !== null && Number.isFinite(cost)
    const has_latency = finite_non_negative(latency)

    if (!has_cost && !has_latency) {
      omitted.push({ id, reason: "missing_both" })
      continue
    }
    if (!has_cost) {
      omitted.push({ id, reason: "missing_cost" })
      continue
    }
    if (!has_latency) {
      omitted.push({ id, reason: "missing_latency" })
      continue
    }
    // A recorded cost of zero is a different fact from no recorded cost, and it
    // is still unplottable here: the axis is logarithmic because the spread
    // between the cheap and expensive arms is a couple of orders of magnitude,
    // and log has no zero.
    if (!finite_positive(cost)) {
      omitted.push({ id, reason: "nonpositive_cost" })
      continue
    }

    const quality = getQuality(id)
    plotted.push({
      id,
      latency_ms: latency as number,
      cost: cost as number,
      quality: quality !== null && Number.isFinite(quality) ? quality : null,
    })
  }

  return { plotted, omitted }
}

/**
 * The points that clear the quality floor, and the ones that do not.
 *
 * No floor means no gate: every point is part of the comparison, which is the
 * default the page opens with. A config with no quality score at all counts as
 * BELOW a gate that has been set - the gate is a claim about measured quality,
 * and an unmeasured config has not made it - but it is ghosted under its own
 * wording, since "we did not measure it" and "we measured it and it failed" are
 * different facts about a config and only one of them is its fault.
 */
export function split_by_gate(
  points: PricePoint[],
  floor: number | null,
): { qualifying: PricePoint[]; ghosted: GhostedPoint[] } {
  if (floor === null || !Number.isFinite(floor)) {
    return { qualifying: [...points], ghosted: [] }
  }
  const qualifying: PricePoint[] = []
  const ghosted: GhostedPoint[] = []
  for (const point of points) {
    if (point.quality === null) {
      ghosted.push({ ...point, reason: "no_quality" })
    } else if (point.quality >= floor) {
      qualifying.push(point)
    } else {
      ghosted.push({ ...point, reason: "below_gate" })
    }
  }
  return { qualifying, ghosted }
}

/**
 * Where the gate menu takes its cuts: the quintile boundaries of the plotted
 * configs' quality.
 *
 * Four percentiles rather than four fixed thresholds, because a fixed ladder is
 * a claim about what quality LOOKS like on a task, and no page knows that. A
 * menu of 50/70/80/90 against a task whose configs all sit between 51% and 64%
 * offers one gate that changes nothing and three that gate out everything - a
 * control with four dead positions, which reads as a broken chart rather than
 * as a task whose configs are close together.
 */
export const GATE_PERCENTILES = [0.2, 0.4, 0.6, 0.8] as const

/** Linear-interpolated percentile of an ASCENDING-sorted, non-empty array. */
function percentile(sorted: number[], p: number): number {
  const index = p * (sorted.length - 1)
  const lower = Math.floor(index)
  const upper = Math.ceil(index)
  if (lower === upper) return sorted[lower]
  return sorted[lower] + (index - lower) * (sorted[upper] - sorted[lower])
}

/**
 * A cut, rounded to the percent it is shown as.
 *
 * The menu labels a cut "58%" and the gate applies the raw float, so unless the
 * two are the same number a config sitting exactly on the labelled percent can
 * fail the gate it appears to clear. Rounding the CUT rather than only the
 * label keeps the gate honest at the precision it is stated in - and precision
 * finer than a percent is noise in a decision phrased as "good enough to ship".
 */
function round_to_percent(value: number): number {
  return Math.round(value * 100) / 100
}

/**
 * Up to four quality cuts for the gate menu, ascending, each a 0..1 floor.
 *
 * Takes the numbers rather than the configs, and knows nothing about which
 * quality metric produced them: whatever the page's aggregate happens to be
 * this month, the cuts are the quintiles of what it yielded.
 *
 * DEDUPE RULE - a cut earns a row only when it changes the answer:
 *   - it must gate out at least one config MORE than the row above it (Off is
 *     the row above the first cut, and gates out none), and
 *   - it must leave at least one config standing.
 * Two percentiles that round to the same percent, or that clear the same set
 * because no config's quality falls between them, therefore collapse to one
 * row; a cut that clears everything is dropped as a second Off; and a cut that
 * rounded up past the best config is dropped rather than offered as a gate
 * nothing clears. The menu that results has no dead positions - every row
 * removes at least one config from the comparison, and none empties it.
 *
 * Fewer than two scored configs, or all of them on the same quality, produce no
 * cuts at all: there is nothing to cut BETWEEN, and the menu says so rather
 * than offering an arbitrary number. Nulls and non-finite values are not
 * quality scores and take no part in the percentiles.
 */
export function quality_gate_cuts(qualities: (number | null)[]): number[] {
  const values = qualities
    .filter(
      (value): value is number => value !== null && Number.isFinite(value),
    )
    .sort((a, b) => a - b)
  // One number has no percentiles worth the name, and zero would index off the
  // end of the array.
  if (values.length < 2) return []

  const cuts: number[] = []
  // What the row above clears. Off clears everything, so the first cut has to
  // beat that to be worth a row.
  let clearing = values.length
  for (const p of GATE_PERCENTILES) {
    const cut = round_to_percent(percentile(values, p))
    const count = values.filter((value) => value >= cut).length
    if (count > 0 && count < clearing) {
      cuts.push(cut)
      clearing = count
    }
  }
  // Ascending by construction: percentile is monotonic in p and rounding is
  // monotonic in its argument.
  return cuts
}

/**
 * The Pareto frontier on (latency, cost), both lower-better: the points no
 * other point beats on one axis without losing on the other.
 *
 * Dominance is STRICT - a point is dropped only when another is at least as
 * good on both axes and strictly better on one - so two configs at the same
 * cost and latency both survive. A tie is not a domination: neither of them is
 * the reason to prefer the other, and dropping one arbitrarily would put a
 * config off the frontier for having been listed second.
 *
 * Sorted by latency so the result can be drawn as a line without the caller
 * sorting it again; cost then id break ties, which keeps the frontier's shape
 * a function of the data rather than of the pinning order.
 */
export function pareto_frontier(points: PricePoint[]): PricePoint[] {
  const frontier = points.filter(
    (candidate) =>
      !points.some(
        (other) =>
          other !== candidate &&
          other.latency_ms <= candidate.latency_ms &&
          other.cost <= candidate.cost &&
          (other.latency_ms < candidate.latency_ms ||
            other.cost < candidate.cost),
      ),
  )
  return frontier.sort(
    (a, b) =>
      a.latency_ms - b.latency_ms ||
      a.cost - b.cost ||
      a.id.localeCompare(b.id),
  )
}

/**
 * A cost for the y axis' ticks.
 *
 * Not the four decimals the tooltip and the comparison table use: a log axis
 * puts a tick at every power of ten and at the 2/5 subdivisions between them,
 * so a fixed precision writes either "$0.0100" beside "$10.0000" or "$0.01"
 * beside "$0.00". The number of decimals follows the magnitude instead, which
 * is what makes a decade of ticks read as one ladder.
 */
export function format_cost_tick(value: number): string {
  if (!Number.isFinite(value)) return ""
  const magnitude = Math.abs(value)
  if (magnitude === 0) return "$0"
  if (magnitude >= 1) return `$${value.toFixed(2)}`
  if (magnitude >= 0.01) return `$${value.toFixed(3)}`
  return `$${value.toFixed(4)}`
}

/** Milliseconds as the seconds the x axis is drawn in. */
export function latency_seconds(latency_ms: number): number {
  return latency_ms / 1000
}
