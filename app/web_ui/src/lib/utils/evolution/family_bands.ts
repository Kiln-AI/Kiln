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
// This module is the geometry and the styling of that band - where the arc
// sweeps, where its name is written, and what tone it is filled with - shared
// so the two charts cannot disagree about where a family ends or look like two
// different conventions. What a family IS differs per chart and lives
// elsewhere: `metric_axes` has a curated catalog, `score_families` reads the
// task's specs.

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
 * The angle a band's arc is centred on, in echarts' convention: radians, y up,
 * counterclockwise, 0 due east - the same numbers the radar's own indicator
 * axes carry. Callers wanting canvas angles negate it, as `family_band_arc`
 * does below.
 *
 * The midpoint of the INDEX range, not of the sweep: the two are the same
 * number, because the sweep is symmetric about the axes it covers, and the
 * index form is the one that stays exact for a one-axis family (its own axis).
 */
export function family_band_mid_angle(
  band: Pick<FamilyBand, "startIndex" | "endIndex">,
  axisCount: number,
  startAngleDegrees: number,
): number {
  const step = (Math.PI * 2) / Math.max(axisCount, 1)
  const start = (startAngleDegrees * Math.PI) / 180
  return start - ((band.startIndex + band.endIndex) / 2) * step
}

/** Where a family's name is drawn, and how much room it has */
export interface FamilyLabelPlacement {
  /** Centre of the text, in canvas px */
  x: number
  y: number
  /** echarts `graphic` rotation: radians, counterclockwise on screen */
  rotation: number
  /** The arc this family sweeps at that radius, in px - see family_label_budgets */
  sweep: number
}

/**
 * Where a family's name goes: centred on its arc, laid along it.
 *
 * TANGENTIAL, and that is a decision the card's width forces rather than a
 * stylistic one. The obvious placement is a third ring of horizontal text
 * outside the axis names, and it does not fit: these cards are ~539px wide, an
 * axis name pointing due east already reaches ~95px past the ring, and a
 * horizontal family name beyond it would take another ~90 - which prices the
 * ring itself down by about 30%, on both charts. Laid along the arc the name
 * costs its LINE HEIGHT rather than its width, ~15px, because at the two places
 * where horizontal room is scarce - due east and due west - the text is running
 * vertically. So the tier is affordable at every card size the page produces.
 *
 * Rotation follows the ring clockwise, the direction it is read, and flips on
 * the bottom half so a name is never upside down. The flip is decided by which
 * way the text's own "up" would point, which is what makes it continuous: the
 * two exactly-sideways cases (due east, due west) have no up at all, so due
 * west is flipped by hand to match due east and both read downwards.
 *
 * How wide the name may be is not decided here - see family_label_budgets,
 * which needs the whole ring to answer it.
 */
export function family_band_label(
  band: Pick<FamilyBand, "startIndex" | "endIndex" | "count">,
  axisCount: number,
  options: {
    startAngleDegrees: number
    cx: number
    cy: number
    radius: number
  },
): FamilyLabelPlacement {
  const angle = family_band_mid_angle(
    band,
    axisCount,
    options.startAngleDegrees,
  )
  const sin = Math.sin(angle)
  const cos = Math.cos(angle)
  // Clockwise tangent, in screen coordinates (y down)
  let dx = sin
  let dy = cos
  // The text's up-vector is (dy, -dx), so it points at the sky exactly when
  // dx > 0. At dx = 0 - due east and due west - the text is running straight up
  // or down and has no up at all, so due west is flipped to read the way due
  // east does. The tolerance is not decoration: sin(PI) comes back as 1.2e-16,
  // so an exact test would leave the label at nine o'clock reading upwards.
  const sideways = Math.abs(dx) < 1e-9
  if (sideways ? cos < 0 : dx < 0) {
    dx = -dx
    dy = -dy
  }
  const step = (Math.PI * 2) / Math.max(axisCount, 1)
  return {
    x: options.cx + options.radius * cos,
    y: options.cy - options.radius * sin,
    rotation: Math.atan2(-dy, dx),
    sweep: band.count * step * options.radius,
  }
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

/**
 * The ink every family arc is drawn in - one cool grey, #8b93a1, as channels.
 *
 * No hue, because the run configs already own colour on these charts. Five
 * family hues muted enough to sit behind the series stop being tellable apart
 * (a worst pair of ~5 in OKLab dE, where ~15 is the floor), and five saturated
 * enough to be tellable apart fight the series for the eye. Either way the
 * colour would be decoration that looks like meaning.
 *
 * One ink rather than a set of tones, because what separates the arcs is their
 * OPACITY - see family_tone_alpha. Kept as channels rather than a hex string so
 * the arcs composite against the card instead of against a white this module
 * assumed: baking the blend in would fix the lightest rung to one background.
 */
export const FAMILY_TONE_INK = [139, 147, 161] as const

/**
 * The two ends of the ladder, as opacities of that ink.
 *
 * The floor is where a 4px arc stops reading, and it was read off the rendered
 * page rather than picked as a number that looks reasonable in code: 0.22, 0.3,
 * 0.34 and 0.38 all drawn on the compare page and compared at the size the card
 * actually shows them. The worst case is the one that decides it - a ONE-AXIS
 * family at twelve o'clock, which is both the shortest arc on the ring and the
 * lightest rung, and which both charts have. At 0.22 it is a smudge and at 0.3
 * it is faint; 0.34 is the first that is unmistakably a drawn thing, #d8dadf,
 * L* 87.0. Losing that arc is the worst loss available, because twelve o'clock
 * is where the eye starts.
 *
 * The ceiling is the ink at full strength, L* 60.7. That is the tone the
 * darkest arc has always been, so the ladder is built downwards from a top the
 * page has already been seen to carry rather than upwards into a new one.
 */
export const FAMILY_TONE_LIGHTEST = 0.34
export const FAMILY_TONE_DARKEST = 1

/**
 * How opaque one arc is: a LADDER. Lightest at twelve o'clock, one step darker
 * for every family clockwise, through to the last.
 *
 * A ramp of one colour encodes magnitude, and over nominal categories that is
 * normally a lie - it asserts an order the categories do not have. Here they
 * do. The families are laid out clockwise from the top in a fixed order the
 * reader can see on the page, so the darkening tracks POSITION IN THE RING,
 * which is true of them, rather than rank, which would not be. What that buys
 * over tones that merely differ is that a reader who has found one arc knows
 * which way round the ring they are looking without reading a single name.
 *
 * The rungs are spaced over the arcs actually DRAWN, so the ladder always spans
 * the whole range end to end. Hiding rows until a family empties re-spaces the
 * families that are left rather than leaving a hole where that family's rung
 * used to be, which is the only behaviour that stays legible while someone is
 * pruning the ring a row at a time.
 *
 * The wrap is left alone. Darkest meets lightest at twelve o'clock, so the
 * largest tone difference on the ring falls exactly where two families meet,
 * and reads as the ladder starting over. That discontinuity is the point;
 * smoothing it would spend the range on the one boundary that needs no help.
 *
 * At high family counts the step COMPRESSES rather than clamping to a minimum:
 * the range is fixed, so N families step by 1/(N-1) of it, and by twelve that
 * is ~2.3 L* between neighbours, near the floor of what tells apart. That is
 * deliberate, because the two things the band is read for fail at different
 * rates. "Is this a different family from the one beside it" is answered by the
 * gap between the arcs, which is a fixed 16px and does not shrink with N. "How
 * far round the ring is this" is answered by comparing arcs that are NOT
 * neighbours, and half a ring apart is half the range however many rungs it has
 * been cut into. Holding a minimum step instead costs one of the two things the
 * range is pinned to: lift the floor and the first arc disappears, darken the
 * ink and two cards side by side with different family counts end up with
 * different darkest tones, which is two conventions rather than one.
 *
 * A lone band is not a ladder - nothing to climb, nothing to read it against -
 * so it takes the ink at full strength. `family_bands` has returned nothing by
 * then anyway, so this is the definition being total rather than a case the
 * charts reach.
 */
export function family_tone_alpha(index: number, count: number): number {
  if (count <= 1) return FAMILY_TONE_DARKEST
  const rung = Math.min(Math.max(index, 0), count - 1) / (count - 1)
  return (
    FAMILY_TONE_LIGHTEST + rung * (FAMILY_TONE_DARKEST - FAMILY_TONE_LIGHTEST)
  )
}

/** The fill an arc is drawn with: the ink at its rung. See `family_tone_alpha`. */
export function family_tone(index: number, count: number): string {
  const [r, g, b] = FAMILY_TONE_INK
  return `rgba(${r}, ${g}, ${b}, ${family_tone_alpha(index, count).toFixed(3)})`
}

/**
 * How wide each family's name may be drawn, in px along the ring.
 *
 * The obvious budget - a name gets its own family's sweep and no more - is what
 * a one-axis family cannot live with: at seventeen axes its sweep is about 50px
 * and "Data Integrity" needs 90, so the heading of a whole family comes out as
 * "Data I…" while the twelve-axis family next to it leaves 600px of arc empty.
 *
 * So a name may borrow from its neighbours, and the amount it may borrow is the
 * one that cannot go wrong. Two names never touch when
 * `w[i] + w[i+1] <= s[i] + s[i+1] - 2*gap`, since both are centred in their own
 * sweeps and the centres are `(s[i] + s[i+1]) / 2` apart. Give a name its own
 * sweep plus the SMALLER of its two neighbours' unused room, and cap it at the
 * width it actually wanted, and that inequality holds in every case: whichever
 * of the pair is borrowing, the other one has slack to spare by definition,
 * because slack is only positive when that neighbour's name fits inside its own
 * sweep with room over. Symmetric, so a name stays centred on its own group.
 *
 * The ring wraps, so the first band's neighbour is the last one - the seam at
 * twelve o'clock is a boundary like any other and is not special-cased.
 */
export function family_label_budgets(
  needs: number[],
  sweeps: number[],
  gap: number,
): number[] {
  const count = needs.length
  const own = sweeps.map((sweep) => Math.max(sweep - gap, 0))
  if (count < 2) return own
  const slack = own.map((room, index) => Math.max(room - needs[index], 0))
  return own.map(
    (room, index) =>
      room +
      Math.min(slack[(index - 1 + count) % count], slack[(index + 1) % count]),
  )
}

/**
 * A label cut down to the room it has, or "" when even an ellipsis would not
 * fit. Shared so the two rings ellipsize a family name the same way; each
 * passes its own text measurement, since one chart measures against the canvas
 * and the other estimates.
 */
export function truncate_to_width(
  text: string,
  maxWidth: number,
  measure: (value: string) => number,
): string {
  if (measure(text) <= maxWidth) return text
  let kept = text
  while (kept.length > 0 && measure(`${kept}…`) > maxWidth) {
    kept = kept.slice(0, -1)
  }
  return kept.length > 0 ? `${kept}…` : ""
}
