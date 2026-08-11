import { describe, it, expect } from "vitest"
import {
  build_price_latency_points,
  format_cost_tick,
  latency_seconds,
  pareto_frontier,
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
