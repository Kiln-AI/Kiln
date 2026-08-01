import { describe, it, expect } from "vitest"
import { family_bands, family_band_arc } from "./family_bands"

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
