import { describe, it, expect } from "vitest"
import {
  family_bands,
  family_band_arc,
  family_band_label,
  family_band_mid_angle,
  family_label_budgets,
  family_tone,
  family_tone_index,
  truncate_to_width,
  FAMILY_TONES,
} from "./family_bands"

describe("family_bands", () => {
  const member = (family: string) => ({ family, label: family.toUpperCase() })

  it("collapses a run of one family into a single band", () => {
    const bands = family_bands([
      member("cost"),
      member("tokens"),
      member("tokens"),
      member("tokens"),
      member("speed"),
    ])
    expect(bands.map((band) => [band.family, band.count])).toEqual([
      ["cost", 1],
      ["tokens", 3],
      ["speed", 1],
    ])
    expect(bands[1]).toMatchObject({
      startIndex: 1,
      endIndex: 3,
      label: "TOKENS",
    })
  })

  it("covers every axis exactly once, in order", () => {
    const members = ["a", "a", "b", "c", "c", "c"].map(member)
    const bands = family_bands(members)
    expect(bands[0].startIndex).toBe(0)
    expect(bands[bands.length - 1].endIndex).toBe(members.length - 1)
    for (let index = 1; index < bands.length; index++) {
      expect(bands[index].startIndex).toBe(bands[index - 1].endIndex + 1)
    }
    expect(bands.reduce((total, band) => total + band.count, 0)).toBe(
      members.length,
    )
  })

  it("reports a split family as two bands - the picture is what it draws", () => {
    const bands = family_bands([
      member("cost"),
      member("tokens"),
      member("cost"),
    ])
    expect(bands.map((band) => band.family)).toEqual(["cost", "tokens", "cost"])
  })

  it("draws nothing when there is no boundary to draw", () => {
    // One family divides nothing, so a full circle of arc would be decoration
    expect(family_bands([member("cost"), member("cost")])).toEqual([])
    expect(family_bands([member("cost")])).toEqual([])
    expect(family_bands([])).toEqual([])
  })
})

describe("family_band_arc", () => {
  const band = (startIndex: number, endIndex: number) => ({
    startIndex,
    endIndex,
    count: endIndex - startIndex + 1,
  })
  const arc = (b: ReturnType<typeof band>, count: number, gap = 0) =>
    family_band_arc(b, count, { startAngleDegrees: 90, gapRadians: gap })

  // Canvas angles: 0 is due east and they grow CLOCKWISE, because y points down
  const degrees = (radians: number) => Math.round((radians * 180) / Math.PI)

  it("centres a one-axis band on its own axis", () => {
    // Four axes from the top: axis 0 is straight up, which is -90 on a canvas
    const { startAngle, endAngle } = arc(band(0, 0), 4)
    expect(degrees(startAngle)).toBe(-135)
    expect(degrees(endAngle)).toBe(-45)
    expect(degrees((startAngle + endAngle) / 2)).toBe(-90)
  })

  it("sweeps clockwise, following the indicators", () => {
    // Axis 1 of 4 is due east with clockwise indicators, so a band over axes
    // 0 and 1 covers the top-right quadrant and a bit either side
    const { startAngle, endAngle } = arc(band(0, 1), 4)
    expect(endAngle).toBeGreaterThan(startAngle)
    expect(degrees(startAngle)).toBe(-135)
    expect(degrees(endAngle)).toBe(45)
  })

  it("spans half a slot past the axes at each end, so boundaries fall between", () => {
    const first = arc(band(0, 0), 4)
    const second = arc(band(1, 1), 4)
    expect(second.startAngle).toBeCloseTo(first.endAngle, 10)
  })

  it("takes the gap out of the sweep, half at each end", () => {
    const step = (Math.PI * 2) / 8
    const gap = 0.2
    const { startAngle, endAngle } = arc(band(2, 4), 8, gap)
    expect(endAngle - startAngle).toBeCloseTo(3 * step - gap, 10)
    const bare = arc(band(2, 4), 8)
    expect(startAngle - bare.startAngle).toBeCloseTo(gap / 2, 10)
    expect(bare.endAngle - endAngle).toBeCloseTo(gap / 2, 10)
  })

  it("never lets the gap eat the band - a lone axis keeps a visible arc", () => {
    const step = (Math.PI * 2) / 16
    const { startAngle, endAngle } = arc(band(0, 0), 16, 99)
    expect(endAngle - startAngle).toBeCloseTo(step * 0.5, 10)
    expect(endAngle).toBeGreaterThan(startAngle)
  })

  it("survives a degenerate axis count rather than dividing by zero", () => {
    const { startAngle, endAngle } = arc(band(0, 0), 0)
    expect(Number.isFinite(startAngle)).toBe(true)
    expect(Number.isFinite(endAngle)).toBe(true)
  })
})

describe("family_band_mid_angle", () => {
  const band = (startIndex: number, endIndex: number) => ({
    startIndex,
    endIndex,
  })
  const degrees = (radians: number) => Math.round((radians * 180) / Math.PI)

  it("puts a one-axis family on its own axis", () => {
    expect(degrees(family_band_mid_angle(band(0, 0), 4, 90))).toBe(90)
    expect(degrees(family_band_mid_angle(band(1, 1), 4, 90))).toBe(0)
  })

  it("lands between the two middle axes of an even family", () => {
    // Axes 0 and 1 of 4 are at 90 and 0, so the family between them is at 45
    expect(degrees(family_band_mid_angle(band(0, 1), 4, 90))).toBe(45)
  })

  it("agrees with the arc it labels", () => {
    const b = { startIndex: 2, endIndex: 5, count: 4 }
    const { startAngle, endAngle } = family_band_arc(b, 12, {
      startAngleDegrees: 90,
      gapRadians: 0,
    })
    // The arc is in canvas angles, which run the other way
    expect(-(startAngle + endAngle) / 2).toBeCloseTo(
      family_band_mid_angle(b, 12, 90),
      10,
    )
  })
})

describe("family_band_label", () => {
  const place = (
    startIndex: number,
    endIndex: number,
    axisCount: number,
    radius = 100,
  ) =>
    family_band_label(
      { startIndex, endIndex, count: endIndex - startIndex + 1 },
      axisCount,
      { startAngleDegrees: 90, cx: 200, cy: 300, radius },
    )

  // Where the text runs on screen, from the rotation echarts will apply
  const direction = (rotation: number) => ({
    dx: Math.cos(rotation),
    dy: -Math.sin(rotation),
  })

  it("sits on its arc's midpoint, in canvas coordinates", () => {
    // Axis 0 of 4 is straight up, and screen y grows downwards
    const top = place(0, 0, 4)
    expect(top.x).toBeCloseTo(200, 6)
    expect(top.y).toBeCloseTo(200, 6)
    const right = place(1, 1, 4)
    expect(right.x).toBeCloseTo(300, 6)
    expect(right.y).toBeCloseTo(300, 6)
  })

  it("reads left to right at the top of the ring", () => {
    const { dx, dy } = direction(place(0, 0, 4).rotation)
    expect(dx).toBeCloseTo(1, 6)
    expect(dy).toBeCloseTo(0, 6)
  })

  it("reads downwards at both sides, not upwards at one of them", () => {
    // Nine o'clock is the case an exact zero test gets wrong: sin(PI) is 1.2e-16
    for (const index of [1, 3]) {
      const { dx, dy } = direction(place(index, index, 4).rotation)
      expect(dx).toBeCloseTo(0, 6)
      expect(dy).toBeCloseTo(1, 6)
    }
  })

  it("never lets a name come out upside down", () => {
    // The text's up-vector must have a negative screen y at every angle
    for (let index = 0; index < 24; index++) {
      const { dx, dy } = direction(place(index, index, 24).rotation)
      const up_y = -dx
      expect(up_y).toBeLessThanOrEqual(1e-9)
    }
  })

  it("reports the arc it has to fit inside", () => {
    const two = place(0, 1, 8, 100)
    expect(two.sweep).toBeCloseTo((2 * (Math.PI * 2)) / 8 / 1 / (1 / 100), 6)
    expect(place(0, 0, 8, 100).sweep).toBeCloseTo(two.sweep / 2, 6)
  })
})

describe("family_tone_index", () => {
  const cycle = (count: number) =>
    Array.from({ length: count }, (_, index) => family_tone_index(index, count))

  const no_neighbour_matches = (tones: number[]) => {
    for (let index = 0; index < tones.length; index++) {
      // The ring wraps, so the last arc's neighbour is the first
      expect(tones[index]).not.toBe(tones[(index + 1) % tones.length])
    }
  }

  it("alternates two tones when the count is even", () => {
    expect(cycle(2)).toEqual([0, 1])
    expect(cycle(4)).toEqual([0, 1, 0, 1])
    expect(cycle(8)).toEqual([0, 1, 0, 1, 0, 1, 0, 1])
  })

  it("uses a third tone when the count is odd, rather than meeting itself", () => {
    expect(cycle(3)).toEqual([0, 1, 2])
    expect(cycle(5)).toEqual([0, 1, 2, 0, 1])
  })

  it("steps the last arc aside when the cycle would close on itself", () => {
    // 7 % 3 leaves the last arc back on tone 0, next to the first
    expect(cycle(7)).toEqual([0, 1, 2, 0, 1, 2, 1])
  })

  it("never puts a tone next to itself, at any count up to twelve", () => {
    for (let count = 2; count <= 12; count++) {
      no_neighbour_matches(cycle(count))
    }
  })

  it("has a tone for a lone band, which has no neighbour to differ from", () => {
    expect(family_tone_index(0, 1)).toBe(0)
    expect(family_tone(0, 1)).toBe(FAMILY_TONES[0])
  })

  it("is neutral - no hue - so it cannot argue with the series colours", () => {
    for (const tone of FAMILY_TONES) {
      const [r, g, b] = [1, 3, 5].map((at) =>
        parseInt(tone.slice(at, at + 2), 16),
      )
      // Cool greys, so a channel spread of a few percent is expected; what
      // this rules out is a tone with enough chroma to read as a family HUE
      // and compete with the run config series for the eye.
      expect(Math.max(r, g, b) - Math.min(r, g, b)).toBeLessThanOrEqual(24)
    }
  })
})

describe("family_label_budgets", () => {
  it("gives a name its own sweep when nothing is spare", () => {
    expect(family_label_budgets([100, 100], [110, 110], 10)).toEqual([100, 100])
  })

  it("lends a crowded name the room its neighbour is not using", () => {
    // One axis beside a wide family: 40px of arc for a 90px name
    const budgets = family_label_budgets([90, 30, 30], [50, 400, 400], 10)
    expect(budgets[0]).toBeGreaterThanOrEqual(90)
  })

  it("borrows only what the tighter neighbour can spare", () => {
    const budgets = family_label_budgets([200, 10, 10], [50, 100, 400], 0)
    // The 100px neighbour has 90 spare, the 400px one 390: the 90 is the limit
    expect(budgets[0]).toBe(50 + 90)
  })

  it("keeps neighbours apart however much they borrow", () => {
    const needs = [200, 12, 140, 30, 8]
    const sweeps = [40, 260, 60, 300, 90]
    const gap = 12
    const budgets = family_label_budgets(needs, sweeps, gap)
    const drawn = budgets.map((budget, index) => Math.min(budget, needs[index]))
    for (let index = 0; index < drawn.length; index++) {
      const next = (index + 1) % drawn.length
      // Both names are centred in their own sweeps, so this is the whole
      // condition for the pair not to touch - across the twelve o'clock seam too
      expect(drawn[index] + drawn[next]).toBeLessThanOrEqual(
        sweeps[index] + sweeps[next] - 2 * gap + 1e-9,
      )
    }
  })

  it("never returns a negative budget out of a sweep smaller than the gap", () => {
    expect(family_label_budgets([50], [4], 16)).toEqual([0])
  })
})

describe("truncate_to_width", () => {
  const measure = (text: string) => text.length * 10

  it("leaves a name that fits alone", () => {
    expect(truncate_to_width("Format", 100, measure)).toBe("Format")
  })

  it("cuts to the room there is, ellipsis included in the measurement", () => {
    expect(truncate_to_width("Data Integrity", 50, measure)).toBe("Data…")
  })

  it("drops a name that has no room at all rather than showing an ellipsis", () => {
    expect(truncate_to_width("Data Integrity", 5, measure)).toBe("")
  })
})
