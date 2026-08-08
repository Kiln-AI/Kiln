import { describe, it, expect } from "vitest"
import {
  wilson_interval,
  score_interval,
  supports_interval,
  interval_half_width_pp,
  Z_95,
} from "./score_intervals"

describe("wilson_interval", () => {
  it("inverts the score test, which is what a Wilson interval is", () => {
    // The interval is the set of p0 the data would not reject at 95%:
    // |p - p0| / sqrt(p0(1-p0)/n) <= z. Solving that by search agrees with the
    // closed form to six decimals, which pins the algebra rather than a
    // constant someone typed from memory.
    const p = 0.5
    const n = 25
    const interval = wilson_interval(p, n)!
    const admits = (p0: number) =>
      Math.abs(p - p0) / Math.sqrt((p0 * (1 - p0)) / n) <= Z_95

    expect(interval.lower).toBeCloseTo(0.317522, 5)
    expect(interval.upper).toBeCloseTo(0.682478, 5)
    // Just inside the bounds is admitted, just outside is rejected.
    expect(admits(interval.lower + 1e-6)).toBe(true)
    expect(admits(interval.upper - 1e-6)).toBe(true)
    expect(admits(interval.lower - 1e-4)).toBe(false)
    expect(admits(interval.upper + 1e-4)).toBe(false)
  })

  it("stays inside [0, 1] at the boundaries where the normal approximation degenerates", () => {
    // 25/25. The normal approximation gives [1, 1] - certainty from 25 runs.
    const perfect = wilson_interval(1, 25)
    expect(perfect!.lower).toBeCloseTo(0.866808, 5)
    expect(perfect!.upper).toBe(1)

    // 0/25. Likewise [0, 0] under the normal approximation.
    const zero = wilson_interval(0, 25)
    expect(zero!.lower).toBe(0)
    expect(zero!.upper).toBeCloseTo(0.133192, 5)
  })

  it("is symmetric under relabelling success as failure", () => {
    const a = wilson_interval(0.28, 25)!
    const b = wilson_interval(0.72, 25)!
    expect(a.lower).toBeCloseTo(1 - b.upper, 12)
    expect(a.upper).toBeCloseTo(1 - b.lower, 12)
  })

  it("narrows as n grows, and never to zero width", () => {
    const widths = [10, 25, 100, 1000].map((n) => {
      const i = wilson_interval(0.5, n)!
      return i.upper - i.lower
    })
    for (let i = 1; i < widths.length; i++) {
      expect(widths[i]).toBeLessThan(widths[i - 1])
    }
    expect(widths[widths.length - 1]).toBeGreaterThan(0)
  })

  it("brackets the point estimate", () => {
    for (const p of [0, 0.09, 0.5, 0.91, 1]) {
      for (const n of [1, 11, 25, 140]) {
        const i = wilson_interval(p, n)!
        expect(i.lower).toBeLessThanOrEqual(p + 1e-12)
        expect(i.upper).toBeGreaterThanOrEqual(p - 1e-12)
      }
    }
  })

  it("reports the sample size it used", () => {
    expect(wilson_interval(0.5, 11)!.n).toBe(11)
  })

  it("returns null rather than a fabricated interval for unusable input", () => {
    expect(wilson_interval(0.5, 0)).toBeNull()
    expect(wilson_interval(0.5, -1)).toBeNull()
    expect(wilson_interval(NaN, 25)).toBeNull()
    expect(wilson_interval(0.5, NaN)).toBeNull()
    // Outside [0,1] means the caller passed something that is not a proportion.
    expect(wilson_interval(2.5, 25)).toBeNull()
    expect(wilson_interval(-1, 25)).toBeNull()
  })

  it("uses the 95% quantile", () => {
    expect(Z_95).toBeCloseTo(1.96, 3)
  })
})

describe("supports_interval", () => {
  it("admits pass_fail only", () => {
    expect(supports_interval("pass_fail")).toBe(true)
    // Means over a range, not proportions - see the module header.
    expect(supports_interval("five_star")).toBe(false)
    expect(supports_interval("pass_fail_critical")).toBe(false)
    expect(supports_interval("custom")).toBe(false)
    expect(supports_interval(null)).toBe(false)
  })
})

describe("score_interval", () => {
  it("computes an interval for a pass_fail mean", () => {
    const i = score_interval(0.44, 25, "pass_fail")
    expect(i).not.toBeNull()
    expect(i!.value).toBe(0.44)
    expect(i!.upper - i!.lower).toBeGreaterThan(0.3)
  })

  it("declines the score types it cannot do honestly", () => {
    expect(score_interval(4.2, 25, "five_star")).toBeNull()
    expect(score_interval(0.4, 25, "pass_fail_critical")).toBeNull()
    expect(score_interval(120, 25, "custom")).toBeNull()
  })

  it("declines when the sample size is missing", () => {
    expect(score_interval(0.44, null, "pass_fail")).toBeNull()
    expect(score_interval(0.44, undefined, "pass_fail")).toBeNull()
    expect(score_interval(null, 25, "pass_fail")).toBeNull()
  })
})

describe("interval_half_width_pp", () => {
  it("reports half the span in percentage points", () => {
    const i = wilson_interval(0.5, 25)!
    expect(interval_half_width_pp(i)).toBeCloseTo(18.25, 2)
  })
})
