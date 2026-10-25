// Geometry for the quality parallel-coordinates chart: turn scores and their
// sample sizes into one plotted row per run config.
//
// Axes here can be different score types, so everything is plotted as a
// fraction of each score's own full range - a pass/fail 0.44 and a five-star
// 3.2 both become 0.44 and 0.55 of their axis. Same convention the radar's Full
// Scale mode uses, so a config sits at the same height on both charts. Real
// values go in the tooltip; the axis carries the fraction.
//
// A RANK axis is the one exception, and it is why `ParallelAxisSpec.rank`
// exists: a performance metric the reader added has no full range to be a
// fraction of, so it arrives already normalized as a capped rank score over the
// configs on screen (see rank_score). Everything below leaves those values
// alone - the score IS the height - and gives them no confidence band, because
// a Wilson interval on a pass rate says nothing about a position in an
// ordering.

import type { components } from "$lib/api_schema"
import { score_type_range } from "$lib/utils/formatters"
import { score_interval } from "./score_intervals"

type ScoreType = components["schemas"]["TaskOutputRatingType"]

export interface ParallelAxisSpec {
  /** score_key_id - eval id and score key */
  key: string
  /** Score name, the axis label */
  label: string
  /** Owning eval, shown under the label and in tooltips */
  evalName: string
  type: ScoreType | null
  /**
   * A performance metric plotted as a capped rank score rather than as a share
   * of a score's own scale. Absent on the quality axes this chart began as.
   */
  rank?: boolean
  /**
   * How this axis's RAW value is written out in the tooltip - dollars, seconds,
   * tokens. Rank axes only: the height is a position, so the tooltip is the
   * only place the actual quantity appears, and the axis's own unit is the only
   * thing that can format it.
   */
  format?: (value: number | null) => string
}

export interface ParallelCell {
  /** Position on the axis, 0..1 of the score's full range. Null when unscored. */
  fraction: number | null
  /** Band bottom in the same units; equals `fraction` when there is no band. */
  lower: number | null
  /** Band top in the same units; equals `fraction` when there is no band. */
  upper: number | null
  /** The score in its own units, for display. */
  value: number | null
  /** Runs behind the score, null when the payload did not carry it. */
  n: number | null
  /** Whether an interval was computable - see score_intervals for the rule. */
  banded: boolean
}

export interface ParallelRow {
  runConfigId: string
  cells: ParallelCell[]
  /** True when at least one axis has a score; rows without one are not drawn. */
  hasData: boolean
}

const EMPTY_CELL: ParallelCell = {
  fraction: null,
  lower: null,
  upper: null,
  value: null,
  n: null,
  banded: false,
}

/**
 * Where a value sits on its axis, as 0..1 of the score's full range. Unknown
 * ranges (custom scores) have no full scale to be a fraction of - those belong
 * to the metrics chart, and are refused here rather than min-max scaled into
 * something that looks comparable.
 */
export function axis_fraction(
  value: number | null,
  type: ScoreType | null,
): number | null {
  if (value === null || !Number.isFinite(value)) return null
  const range = score_type_range(type)
  if (!range || range.max === range.min) return null
  const fraction = (value - range.min) / (range.max - range.min)
  return Math.min(1, Math.max(0, fraction))
}

/** One config's cell on one axis, interval included when the score type allows. */
export function build_cell(
  value: number | null,
  n: number | null,
  type: ScoreType | null,
): ParallelCell {
  const fraction = axis_fraction(value, type)
  if (fraction === null) return { ...EMPTY_CELL }

  const interval = score_interval(value, n, type)
  if (!interval) {
    // No band: the point still plots, and the tooltip says why it is alone.
    return {
      fraction,
      lower: fraction,
      upper: fraction,
      value,
      n,
      banded: false,
    }
  }
  return {
    fraction,
    lower: axis_fraction(interval.lower, type) ?? fraction,
    upper: axis_fraction(interval.upper, type) ?? fraction,
    value,
    n: interval.n,
    banded: true,
  }
}

/**
 * One config's cell on a RANK axis.
 *
 * The rank score is already the height - it is a 0..1 position among the
 * configs on screen, computed by the page over exactly the set being drawn - so
 * there is nothing to normalize and no range to normalize against. The raw
 * value rides along untouched for the tooltip, which is the only place a metric
 * axis reports an actual quantity.
 *
 * Never banded, and `n` is deliberately left null. A confidence interval is a
 * statement about a proportion; a rank is a statement about an ordering, and
 * putting a band round one would be drawing uncertainty in units the number
 * does not have. A config with no rank (nothing measured) yields the empty
 * cell, which the chart draws as a gap rather than as a zero - last place and
 * "not measured" are different facts.
 */
export function build_rank_cell(
  score: number | null,
  value: number | null,
): ParallelCell {
  if (score === null || !Number.isFinite(score)) {
    return { ...EMPTY_CELL }
  }
  return {
    fraction: score,
    lower: score,
    upper: score,
    value,
    n: null,
    banded: false,
  }
}

/**
 * Plotted rows, one per run config, in the order given. Configs with nothing to
 * plot are still returned (with `hasData` false) so callers can tell "no score
 * for this config" apart from "config not in the comparison".
 *
 * `getRankScore` is consulted for rank axes only, and is optional: a caller
 * with no metric axes never needs one.
 */
export function build_parallel_rows(
  axes: ParallelAxisSpec[],
  runConfigIds: string[],
  getValue: (runConfigId: string, key: string) => number | null,
  getSampleSize: (runConfigId: string, key: string) => number | null,
  getRankScore?: (runConfigId: string, key: string) => number | null,
): ParallelRow[] {
  return runConfigIds.map((runConfigId) => {
    const cells = axes.map((axis) =>
      axis.rank
        ? build_rank_cell(
            getRankScore?.(runConfigId, axis.key) ?? null,
            getValue(runConfigId, axis.key),
          )
        : build_cell(
            getValue(runConfigId, axis.key),
            getSampleSize(runConfigId, axis.key),
            axis.type,
          ),
    )
    return {
      runConfigId,
      cells,
      hasData: cells.some((cell) => cell.fraction !== null),
    }
  })
}

/**
 * Move one axis to a new position, the operation a drag performs.
 *
 * Axis ORDER is the reader's to choose on a parallel-coordinates chart: which
 * axes sit next to each other decides which crossings are visible, and the
 * order that tells the story is not the order the evals happen to be stored in.
 * Out-of-range indices return the list untouched rather than throwing - a drag
 * that ends outside the chart is a cancelled drag, not an error.
 */
export function reorder(list: string[], from: number, to: number): string[] {
  if (from === to) return [...list]
  if (from < 0 || from >= list.length) return [...list]
  if (to < 0 || to >= list.length) return [...list]
  const next = [...list]
  const [moved] = next.splice(from, 1)
  next.splice(to, 0, moved)
  return next
}

/**
 * Fold a new set of axis keys into an order the reader has already arranged:
 * keep what they arranged, in their order, drop what is gone, and put anything
 * new on the end. Pinning another config must not throw away a layout the
 * reader built to make a point.
 */
export function reconcile_order(
  previous: string[],
  current: string[],
): string[] {
  const available = new Set(current)
  const seen = new Set(previous)
  return [
    ...previous.filter((key) => available.has(key)),
    ...current.filter((key) => !seen.has(key)),
  ]
}

/**
 * Widest interval on the chart, in percentage points, or null when nothing is
 * banded. The header uses it to say up front how much of each axis the
 * uncertainty covers, which is the whole point of the chart.
 */
export function widest_band_pp(rows: ParallelRow[]): number | null {
  let widest: number | null = null
  for (const row of rows) {
    for (const cell of row.cells) {
      if (!cell.banded || cell.lower === null || cell.upper === null) continue
      const width = (cell.upper - cell.lower) * 100
      if (widest === null || width > widest) widest = width
    }
  }
  return widest
}
