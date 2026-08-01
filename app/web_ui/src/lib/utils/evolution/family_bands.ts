// Family bands: the arcs that make a radar's grouping visible.
//
// Both radars on the compare page group their axes into families - the metrics
// ring by what a number measures (cost, tokens, calls, speed), the quality ring
// by what a criterion is about (data integrity, format, workflow). In both cases
// the families are contiguous by construction, and in both cases contiguity is a
// property of the DATA that a reader looking at a ring of same-weight grey
// labels has no way to see. The band is what turns it into a property of the
// picture.
//
// This module is the geometry, shared so the two charts cannot disagree about
// where a family ends. What a family IS differs per chart and lives elsewhere:
// `metric_axes` has a curated catalog, `score_families` reads the task's specs.

/** One unbroken run of same-family axes, in the order they are drawn. */
export interface FamilyBand {
  /** Stable id of the family this run belongs to */
  family: string
  /** The family's heading, as shown in the key and the axis picker */
  label: string
  /** Index of the run's first axis, into the axis list as drawn */
  startIndex: number
  /** Index of the run's last axis */
  endIndex: number
  /** How many axes the run covers */
  count: number
}

/** An axis, as far as banding is concerned */
export interface FamilyMember {
  family: string
  label: string
}

/**
 * The runs of same-family axes in a drawn axis list.
 *
 * Runs, not groups: a family that somehow arrived split would produce two arcs,
 * which is what the picture would actually be showing. Grouping instead would
 * draw one arc spanning the gap and quietly lie about the axes inside it.
 *
 * Fewer than two runs returns nothing. A lone family divides nothing - a full
 * circle of arc is decoration - and this is the case reached whenever the axis
 * set is narrowed to one family, so it has to be silent rather than ringed.
 * That also covers the empty axis set.
 */
export function family_bands(members: FamilyMember[]): FamilyBand[] {
  const bands: FamilyBand[] = []
  members.forEach((member, index) => {
    const open = bands[bands.length - 1]
    if (open && open.family === member.family) {
      open.endIndex = index
      open.count += 1
      return
    }
    bands.push({
      family: member.family,
      label: member.label,
      startIndex: index,
      endIndex: index,
      count: 1,
    })
  })
  return bands.length > 1 ? bands : []
}

/**
 * The arc one family band sweeps, as canvas angles.
 *
 * Two angle conventions meet here and they run opposite ways, which is the only
 * thing in this file worth a test of its own. echarts places indicator `i` at
 * `theta = start - i * step` when the radar is clockwise, and plots it with
 * `y = cy - r * sin(theta)`, so its angles are the mathematical ones,
 * counterclockwise off a y-up axis. A canvas arc measures from the same origin
 * but with y pointing DOWN, so the same direction is `phi = -theta`. Getting
 * that sign wrong draws the band on the far side of the chart from the labels
 * it belongs to.
 *
 * The band runs from half a slot before its first axis to half a slot after its
 * last, so every axis sits under its own family and the boundary falls midway
 * between the two labels it separates - which is where a reader would draw it.
 * A gap is then taken off each end: the gap is what the eye actually reads as a
 * boundary, so it is never allowed to consume more than half the band, and a
 * one-axis family keeps a visible arc rather than vanishing into its own
 * padding.
 */
export function family_band_arc(
  band: Pick<FamilyBand, "startIndex" | "endIndex" | "count">,
  axisCount: number,
  options: { startAngleDegrees: number; gapRadians: number },
): { startAngle: number; endAngle: number } {
  const step = (Math.PI * 2) / Math.max(axisCount, 1)
  const start = (options.startAngleDegrees * Math.PI) / 180
  const gap = Math.min(Math.max(options.gapRadians, 0), band.count * step * 0.5)
  const first = start - band.startIndex * step
  const last = start - band.endIndex * step
  return {
    startAngle: -(first + step / 2) + gap / 2,
    endAngle: -(last - step / 2) - gap / 2,
  }
}
