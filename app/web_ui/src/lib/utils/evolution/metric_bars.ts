// Row geometry for the performance-metrics bar chart.
//
// The metrics chart is a horizontal grouped bar chart: one row per metric, one
// bar per run config, all on the shared 0-100 relative scale that
// `relative_metric_score` produces. echarts places the bars itself. What it
// will not place is anything OUTSIDE the plot that has to line up with a row -
// the family band down the gutter, and the invisible hover targets over the row
// names - so those are drawn as `graphic` elements, and this is the band
// arithmetic they are placed against. Shared with nothing else on purpose: it
// has to be the same arithmetic echarts uses, or a band drifts off the rows it
// claims to cover.

import type { FamilyBand } from "./family_bands"

/** The plot area a category axis is laid out down, in canvas px */
export interface BarPlot {
  /** Top edge of the plot area */
  top: number
  /** Its height */
  height: number
}

/** Where one metric's row sits, in canvas px */
export interface CategoryBand {
  top: number
  height: number
  /** Middle of the row - where echarts centres the row's name */
  center: number
}

/**
 * The row a metric occupies.
 *
 * echarts divides a category axis into `count` equal bands and centres each
 * category in its own, which is the whole of the arithmetic. Index 0 is at the
 * TOP because the chart inverts its category axis: the metrics then read down
 * the card in the order they were chosen - cost first, the way the families are
 * ordered - rather than bottom-up.
 *
 * The index is clamped rather than trusted, since a caller that has just
 * dropped an axis and not yet redrawn would otherwise place a band off the end
 * of the plot instead of at the last row.
 */
export function category_band(
  index: number,
  count: number,
  plot: BarPlot,
): CategoryBand {
  const rows = Math.max(count, 1)
  const height = plot.height / rows
  const row = Math.min(Math.max(index, 0), rows - 1)
  const top = plot.top + row * height
  return { top, height, center: top + height / 2 }
}

/**
 * The run of rows a family covers, as a bar down the gutter.
 *
 * Inset by half of `gap` at each end, so the space between two neighbouring
 * families is `gap` whole and every band is inset the same amount - a band that
 * paid the full gap at one end only would sit off-centre against its own rows.
 * The first and last bands lose the same half at the outer edge, which keeps
 * the tier reading as one column of marks rather than one that bleeds to the
 * top and bottom of the plot.
 */
export function family_band_span(
  band: Pick<FamilyBand, "startIndex" | "endIndex">,
  count: number,
  plot: BarPlot,
  gap: number = 0,
): { top: number; height: number } {
  const first = category_band(band.startIndex, count, plot)
  const last = category_band(band.endIndex, count, plot)
  const top = first.top + gap / 2
  const height = last.top + last.height - gap / 2 - top
  // A single-row family in a short plot can be thinner than the gap it is
  // inset by. It keeps a hairline: nothing is more honest than a mark that is
  // there, and an inside-out rect would be drawn by zrender as a filled block
  // reaching back over its neighbour.
  return { top, height: Math.max(height, 1) }
}
