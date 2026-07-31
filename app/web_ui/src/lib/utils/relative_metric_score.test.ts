import { describe, it, expect } from "vitest"
import { relative_metric_score } from "./relative_metric_score"

// A spread wide enough that the compression factor k saturates at 1, so the
// scores land on the plain padded range and the assertions read cleanly.
const WIDE = [1, 10]

describe("relative_metric_score", () => {
  it("scores the lowest value highest and the highest value lowest", () => {
    const best = relative_metric_score(1, WIDE)
    const worst = relative_metric_score(10, WIDE)
    expect(best).toBeGreaterThan(worst)
    // Padded endpoints, not a bare 0/100
    expect(best).toBeCloseTo(90, 6)
    expect(worst).toBeCloseTo(10, 6)
  })

  it("is monotonically decreasing in the raw value", () => {
    const values = [1, 3, 5, 7, 10]
    const scores = values.map((value) => relative_metric_score(value, values))
    for (let index = 1; index < scores.length; index++) {
      expect(scores[index]).toBeLessThan(scores[index - 1])
    }
  })

  it("puts a single value at the midpoint - nothing to compare against", () => {
    expect(relative_metric_score(42, [42])).toBe(50)
  })

  it("puts an exact tie at the midpoint", () => {
    expect(relative_metric_score(7, [7, 7, 7])).toBe(50)
  })

  it("returns the midpoint for an empty comparison set", () => {
    expect(relative_metric_score(3, [])).toBe(50)
  })

  it("compresses towards the midpoint when the spread is small", () => {
    // 1% apart: a real difference, but not a 10-vs-90 one
    const tight = [100, 101]
    const best = relative_metric_score(100, tight)
    const worst = relative_metric_score(101, tight)
    expect(best).toBeGreaterThan(50)
    expect(worst).toBeLessThan(50)
    expect(best - worst).toBeLessThan(10)
    // ...where a wide spread uses the full padded range
    expect(
      relative_metric_score(1, WIDE) - relative_metric_score(10, WIDE),
    ).toBeCloseTo(80, 6)
  })

  it("keeps every score inside 0..100", () => {
    const values = [0, 1, 1000, 1e9]
    for (const value of values) {
      const score = relative_metric_score(value, values)
      expect(score).toBeGreaterThanOrEqual(0)
      expect(score).toBeLessThanOrEqual(100)
    }
  })

  it("handles a value outside the comparison set without escaping the range", () => {
    // Not a case the charts produce, but clamping must hold regardless
    expect(relative_metric_score(-100, WIDE)).toBeLessThanOrEqual(100)
    expect(relative_metric_score(1000, WIDE)).toBeGreaterThanOrEqual(0)
  })

  it("handles zeros without dividing by zero", () => {
    expect(relative_metric_score(0, [0, 0])).toBe(50)
    expect(Number.isFinite(relative_metric_score(0, [0, 5]))).toBe(true)
  })
})
