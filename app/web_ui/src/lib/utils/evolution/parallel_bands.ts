// Geometry for the quality parallel-coordinates chart: turn scores and their
// sample sizes into one plotted row per run config.
//
// Axes here can be different score types, so everything is plotted as a
// fraction of each score's own full range - a pass/fail 0.44 and a five-star
// 3.2 both become 0.44 and 0.55 of their axis. Same convention the radar's Full
// Scale mode uses, so a config sits at the same height on both charts. Real
// values go in the tooltip; the axis carries the fraction.

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
 * Plotted rows, one per run config, in the order given. Configs with nothing to
 * plot are still returned (with `hasData` false) so callers can tell "no score
 * for this config" apart from "config not in the comparison".
 */
export function build_parallel_rows(
  axes: ParallelAxisSpec[],
  runConfigIds: string[],
  getValue: (runConfigId: string, key: string) => number | null,
  getSampleSize: (runConfigId: string, key: string) => number | null,
): ParallelRow[] {
  return runConfigIds.map((runConfigId) => {
    const cells = axes.map((axis) =>
      build_cell(
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
