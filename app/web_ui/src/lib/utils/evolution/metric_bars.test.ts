import { describe, it, expect } from "vitest"
import { category_band, family_band_span, type BarPlot } from "./metric_bars"

const PLOT: BarPlot = { top: 20, height: 400 }

describe("category_band", () => {
  it("splits the plot into equal rows, first at the top", () => {
    const first = category_band(0, 4, PLOT)
    const last = category_band(3, 4, PLOT)
    expect(first.top).toBe(20)
    expect(first.height).toBe(100)
    expect(first.center).toBe(70)
    expect(last.top).toBe(320)
    expect(last.top + last.height).toBe(420)
  })

  it("tiles the plot with no gaps and no overhang", () => {
    const rows = [0, 1, 2, 3, 4, 5, 6, 7].map((index) =>
      category_band(index, 8, PLOT),
    )
    rows.forEach((row, index) => {
      if (index === 0) return
      expect(row.top).toBeCloseTo(rows[index - 1].top + rows[index - 1].height)
    })
    const lastRow = rows[rows.length - 1]
    expect(lastRow.top + lastRow.height).toBeCloseTo(PLOT.top + PLOT.height)
  })

  it("clamps an index outside the axis to the row nearest it", () => {
    expect(category_band(-2, 4, PLOT)).toEqual(category_band(0, 4, PLOT))
    expect(category_band(9, 4, PLOT)).toEqual(category_band(3, 4, PLOT))
  })

  it("gives an empty axis one full-height row rather than dividing by zero", () => {
    const only = category_band(0, 0, PLOT)
    expect(only.height).toBe(400)
    expect(only.center).toBe(220)
  })
})

describe("family_band_span", () => {
  it("covers every row of a run", () => {
    const span = family_band_span({ startIndex: 1, endIndex: 2 }, 4, PLOT)
    expect(span.top).toBe(120)
    expect(span.height).toBe(200)
  })

  it("leaves one whole gap between neighbouring families", () => {
    const above = family_band_span({ startIndex: 0, endIndex: 1 }, 4, PLOT, 10)
    const below = family_band_span({ startIndex: 2, endIndex: 3 }, 4, PLOT, 10)
    expect(below.top - (above.top + above.height)).toBeCloseTo(10)
    // ...and each is inset by the same half at both ends, so a band stays
    // centred on its own rows
    expect(above.top).toBeCloseTo(25)
    expect(above.top + above.height).toBeCloseTo(215)
  })

  it("keeps a hairline for a run shorter than its gap", () => {
    const span = family_band_span(
      { startIndex: 0, endIndex: 0 },
      40,
      { top: 0, height: 100 },
      20,
    )
    expect(span.height).toBeGreaterThan(0)
  })
})
