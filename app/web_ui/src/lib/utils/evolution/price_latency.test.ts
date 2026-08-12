import { describe, it, expect } from "vitest"
import {
  build_price_latency_points,
  format_cost_tick,
  latency_seconds,
  pareto_frontier,
  quality_gate_cuts,
  split_by_gate,
  type PricePoint,
} from "./price_latency"
import { COST_KEY, LATENCY_KEY } from "./metric_axes"

/** A metric getter over a table of {id: {cost, latency}} */
function metric_getter(
  table: Record<string, { cost?: number | null; latency?: number | null }>,
) {
  return (id: string, key: string): number | null => {
    const row = table[id]
    if (!row) return null
    if (key === COST_KEY) return row.cost ?? null
    if (key === LATENCY_KEY) return row.latency ?? null
    return null
  }
}

function quality_getter(table: Record<string, number | null>) {
  return (id: string): number | null => table[id] ?? null
}

function point(
  id: string,
  latency_ms: number,
  cost: number,
  quality: number | null = 0.8,
): PricePoint {
  return { id, latency_ms, cost, quality }
}

describe("build_price_latency_points", () => {
  it("plots a config with both axes and carries its quality", () => {
    const { plotted, omitted } = build_price_latency_points(
      ["a"],
      metric_getter({ a: { cost: 0.42, latency: 12_000 } }),
      quality_getter({ a: 0.73 }),
    )
    expect(omitted).toEqual([])
    expect(plotted).toEqual([
      { id: "a", latency_ms: 12_000, cost: 0.42, quality: 0.73 },
    ])
  })

  it("omits a config missing either axis, and says which", () => {
    const { plotted, omitted } = build_price_latency_points(
      ["a", "b", "c"],
      metric_getter({
        a: { cost: 0.1, latency: null },
        b: { cost: null, latency: 900 },
        c: { cost: null, latency: null },
      }),
      quality_getter({}),
    )
    expect(plotted).toEqual([])
    expect(omitted).toEqual([
      { id: "a", reason: "missing_latency" },
      { id: "b", reason: "missing_cost" },
      { id: "c", reason: "missing_both" },
    ])
  })

  it("omits a zero or negative cost separately - a log axis has no place for it", () => {
    const { plotted, omitted } = build_price_latency_points(
      ["free", "credit"],
      metric_getter({
        free: { cost: 0, latency: 1_000 },
        credit: { cost: -1, latency: 1_000 },
      }),
      quality_getter({}),
    )
    expect(plotted).toEqual([])
    expect(omitted).toEqual([
      { id: "free", reason: "nonpositive_cost" },
      { id: "credit", reason: "nonpositive_cost" },
    ])
  })

  it("keeps a zero latency, which is a real position", () => {
    const { plotted } = build_price_latency_points(
      ["a"],
      metric_getter({ a: { cost: 0.5, latency: 0 } }),
      quality_getter({ a: 0.5 }),
    )
    expect(plotted).toEqual([
      { id: "a", latency_ms: 0, cost: 0.5, quality: 0.5 },
    ])
  })

  it("treats a non-finite number as no number at all", () => {
    const { plotted, omitted } = build_price_latency_points(
      ["a", "b"],
      metric_getter({
        a: { cost: Number.NaN, latency: 1_000 },
        b: { cost: 1, latency: Number.POSITIVE_INFINITY },
      }),
      quality_getter({}),
    )
    expect(plotted).toEqual([])
    expect(omitted.map((entry) => entry.reason)).toEqual([
      "missing_cost",
      "missing_latency",
    ])
  })

  it("keeps a plotted config with no quality score, as null rather than zero", () => {
    const { plotted } = build_price_latency_points(
      ["a"],
      metric_getter({ a: { cost: 0.2, latency: 5_000 } }),
      quality_getter({}),
    )
    expect(plotted[0].quality).toBeNull()
  })

  it("preserves the caller's order in both lists", () => {
    const { plotted, omitted } = build_price_latency_points(
      ["c", "a", "b"],
      metric_getter({
        a: { cost: 1, latency: 1 },
        b: { cost: null, latency: null },
        c: { cost: 2, latency: 2 },
      }),
      quality_getter({}),
    )
    expect(plotted.map((p) => p.id)).toEqual(["c", "a"])
    expect(omitted.map((entry) => entry.id)).toEqual(["b"])
  })

  it("has nothing to say about an empty selection", () => {
    expect(
      build_price_latency_points([], metric_getter({}), quality_getter({})),
    ).toEqual({ plotted: [], omitted: [] })
  })
})

describe("split_by_gate", () => {
  const points = [
    point("good", 1_000, 1, 0.9),
    point("bad", 500, 0.1, 0.4),
    point("unmeasured", 800, 0.5, null),
  ]

  it("qualifies everything when there is no floor", () => {
    const { qualifying, ghosted } = split_by_gate(points, null)
    expect(qualifying).toEqual(points)
    expect(ghosted).toEqual([])
  })

  it("ghosts what falls below the floor", () => {
    const { qualifying, ghosted } = split_by_gate(points, 0.8)
    expect(qualifying.map((p) => p.id)).toEqual(["good"])
    expect(ghosted.map((p) => [p.id, p.reason])).toEqual([
      ["bad", "below_gate"],
      ["unmeasured", "no_quality"],
    ])
  })

  it("counts a config exactly at the floor as qualifying", () => {
    const { qualifying } = split_by_gate([point("edge", 1, 1, 0.8)], 0.8)
    expect(qualifying.map((p) => p.id)).toEqual(["edge"])
  })

  it("ghosts an unscored config only once a floor is set", () => {
    const unscored = [point("unmeasured", 800, 0.5, null)]
    expect(split_by_gate(unscored, null).ghosted).toEqual([])
    expect(split_by_gate(unscored, 0.5).ghosted[0].reason).toBe("no_quality")
  })

  it("leaves the input alone", () => {
    const original = [...points]
    split_by_gate(points, 0.5)
    expect(points).toEqual(original)
  })
})

describe("quality_gate_cuts", () => {
  /** How many of `values` a gate at `cut` would leave in the comparison. */
  function clearing(values: number[], cut: number): number {
    return values.filter((value) => value >= cut).length
  }

  it("cuts five spread-out configs into quintiles, one dropped per row", () => {
    const values = [0.52, 0.55, 0.58, 0.61, 0.64]
    const cuts = quality_gate_cuts(values)
    expect(cuts).toEqual([0.54, 0.57, 0.59, 0.62])
    expect(cuts.map((cut) => clearing(values, cut))).toEqual([4, 3, 2, 1])
  })

  it("cuts a bunched-up set too - the old fixed ladder's dead case", () => {
    // The complaint that prompted this: every config between 50% and 70%, so
    // 70/80/90 gated out all five and 50% gated out none.
    const values = [0.51, 0.55, 0.6, 0.62, 0.64]
    const cuts = quality_gate_cuts(values)
    expect(cuts.length).toBeGreaterThan(0)
    for (const cut of cuts) {
      const cleared = clearing(values, cut)
      expect(cleared).toBeGreaterThan(0)
      expect(cleared).toBeLessThan(values.length)
    }
  })

  it("returns whole percents, ascending", () => {
    const cuts = quality_gate_cuts([0.5123, 0.6478, 0.7311, 0.8899, 0.9012])
    for (const cut of cuts) {
      expect(cut).toBeCloseTo(Math.round(cut * 100) / 100, 10)
    }
    expect([...cuts].sort((a, b) => a - b)).toEqual(cuts)
  })

  it("drops a cut that clears the same set as the one below it", () => {
    // Two clusters with a gulf between them: the 60th percentile lands inside
    // the upper cluster and gates out exactly what the 40th already did.
    const values = [0.5, 0.51, 0.9, 0.91, 0.92]
    const cuts = quality_gate_cuts(values)
    expect(cuts).toEqual([0.51, 0.74, 0.91])
    expect(cuts.map((cut) => clearing(values, cut))).toEqual([4, 3, 2])
  })

  it("never offers a gate nothing clears, or one everything clears", () => {
    const sets = [
      [0.5, 0.5, 0.5, 0.5, 0.9],
      [0.1, 0.9],
      [0.996, 0.997, 0.998, 0.999, 1],
      [0, 0.001, 0.002, 0.5, 1],
    ]
    for (const values of sets) {
      for (const cut of quality_gate_cuts(values)) {
        expect(clearing(values, cut)).toBeGreaterThan(0)
        expect(clearing(values, cut)).toBeLessThan(values.length)
      }
    }
  })

  it("falls back to no cuts when every config scores the same", () => {
    expect(quality_gate_cuts([0.62, 0.62, 0.62, 0.62])).toEqual([])
    expect(quality_gate_cuts([1, 1])).toEqual([])
    expect(quality_gate_cuts([0, 0, 0])).toEqual([])
  })

  it("falls back to no cuts below two scored configs", () => {
    expect(quality_gate_cuts([])).toEqual([])
    expect(quality_gate_cuts([0.7])).toEqual([])
    expect(quality_gate_cuts([null, 0.7, null])).toEqual([])
  })

  it("ignores nulls and non-finite values", () => {
    const scored = [0.5, 0.9]
    expect(
      quality_gate_cuts([null, 0.5, null, 0.9, NaN, Infinity, -Infinity]),
    ).toEqual(quality_gate_cuts(scored))
  })

  it("does not care what order the qualities arrive in", () => {
    const values = [0.52, 0.55, 0.58, 0.61, 0.64]
    expect(quality_gate_cuts([...values].reverse())).toEqual(
      quality_gate_cuts(values),
    )
    expect(quality_gate_cuts([0.61, 0.52, 0.64, 0.58, 0.55])).toEqual(
      quality_gate_cuts(values),
    )
  })

  it("handles ties without offering a row that changes nothing", () => {
    const values = [0.6, 0.6, 0.6, 0.9, 0.9]
    const cuts = quality_gate_cuts(values)
    // Only one boundary exists in this data, so only one row is offered.
    expect(cuts).toEqual([0.72])
    expect(clearing(values, cuts[0])).toBe(2)
  })

  it("leaves the input alone", () => {
    const values = [0.9, 0.5, 0.7]
    const original = [...values]
    quality_gate_cuts(values)
    expect(values).toEqual(original)
  })
})

describe("pareto_frontier", () => {
  it("drops a point beaten on both axes", () => {
    const cheap_fast = point("cheap_fast", 1_000, 0.1)
    const dear_slow = point("dear_slow", 2_000, 0.2)
    expect(pareto_frontier([dear_slow, cheap_fast])).toEqual([cheap_fast])
  })

  it("keeps a point that wins on one axis and loses on the other", () => {
    const fast = point("fast", 1_000, 0.5)
    const cheap = point("cheap", 4_000, 0.1)
    expect(pareto_frontier([fast, cheap]).map((p) => p.id)).toEqual([
      "fast",
      "cheap",
    ])
  })

  it("sorts by latency, then cost, then id", () => {
    const frontier = pareto_frontier([
      point("c", 3_000, 0.1),
      point("a", 1_000, 0.9),
      point("b", 2_000, 0.5),
    ])
    expect(frontier.map((p) => p.id)).toEqual(["a", "b", "c"])
  })

  it("keeps both of two identical points - a tie is not a domination", () => {
    const twins = [point("a", 1_000, 0.5), point("b", 1_000, 0.5)]
    expect(pareto_frontier(twins).map((p) => p.id)).toEqual(["a", "b"])
  })

  it("drops a point tied on one axis and beaten on the other", () => {
    const frontier = pareto_frontier([
      point("same_cost_slower", 2_000, 0.5),
      point("same_cost_faster", 1_000, 0.5),
    ])
    expect(frontier.map((p) => p.id)).toEqual(["same_cost_faster"])

    const on_cost = pareto_frontier([
      point("same_speed_dearer", 1_000, 0.9),
      point("same_speed_cheaper", 1_000, 0.5),
    ])
    expect(on_cost.map((p) => p.id)).toEqual(["same_speed_cheaper"])
  })

  it("returns a single point as its own frontier", () => {
    const only = point("only", 1_000, 0.5)
    expect(pareto_frontier([only])).toEqual([only])
  })

  it("returns nothing from nothing", () => {
    expect(pareto_frontier([])).toEqual([])
  })

  it("keeps a staircase whole and drops everything above it", () => {
    const frontier = pareto_frontier([
      point("fastest", 1_000, 1.0),
      point("middle", 2_000, 0.5),
      point("cheapest", 3_000, 0.2),
      // Inside the staircase: slower than middle and dearer than cheapest
      point("dominated", 2_500, 0.8),
      // Beaten by fastest on both
      point("worst", 4_000, 1.5),
    ])
    expect(frontier.map((p) => p.id)).toEqual(["fastest", "middle", "cheapest"])
  })

  it("leaves the input order alone", () => {
    const points = [point("b", 2_000, 0.1), point("a", 1_000, 0.2)]
    const ids = points.map((p) => p.id)
    pareto_frontier(points)
    expect(points.map((p) => p.id)).toEqual(ids)
  })
})

describe("format_cost_tick", () => {
  it("follows the magnitude, so a decade of ticks reads as one ladder", () => {
    expect(format_cost_tick(12)).toBe("$12.00")
    expect(format_cost_tick(1)).toBe("$1.00")
    expect(format_cost_tick(0.5)).toBe("$0.500")
    expect(format_cost_tick(0.01)).toBe("$0.010")
    expect(format_cost_tick(0.002)).toBe("$0.0020")
  })

  it("has nothing to draw for a non-number", () => {
    expect(format_cost_tick(Number.NaN)).toBe("")
    expect(format_cost_tick(0)).toBe("$0")
  })
})

describe("latency_seconds", () => {
  it("converts the axis' units", () => {
    expect(latency_seconds(12_345)).toBeCloseTo(12.345)
    expect(latency_seconds(0)).toBe(0)
  })
})
