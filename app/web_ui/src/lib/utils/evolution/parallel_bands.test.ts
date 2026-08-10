import { describe, it, expect } from "vitest"
import {
  axis_fraction,
  build_cell,
  build_parallel_rows,
  reconcile_order,
  reorder,
  widest_band_pp,
  type ParallelAxisSpec,
} from "./parallel_bands"

describe("reorder", () => {
  const list = ["a", "b", "c", "d"]

  it("moves an axis later, closing the gap behind it", () => {
    expect(reorder(list, 0, 2)).toEqual(["b", "c", "a", "d"])
  })

  it("moves an axis earlier", () => {
    expect(reorder(list, 3, 1)).toEqual(["a", "d", "b", "c"])
  })

  it("handles the ends", () => {
    expect(reorder(list, 0, 3)).toEqual(["b", "c", "d", "a"])
    expect(reorder(list, 3, 0)).toEqual(["d", "a", "b", "c"])
  })

  it("is a no-op when nothing moves, and never mutates the input", () => {
    expect(reorder(list, 2, 2)).toEqual(list)
    const copy = [...list]
    reorder(list, 0, 3)
    expect(list).toEqual(copy)
  })

  it("treats an out-of-range drop as a cancelled drag", () => {
    expect(reorder(list, 0, 9)).toEqual(list)
    expect(reorder(list, -1, 2)).toEqual(list)
    expect(reorder(list, 9, 0)).toEqual(list)
  })

  it("keeps every axis exactly once, wherever it lands", () => {
    for (let from = 0; from < list.length; from++) {
      for (let to = 0; to < list.length; to++) {
        expect([...reorder(list, from, to)].sort()).toEqual([...list].sort())
      }
    }
  })
})

describe("reconcile_order", () => {
  it("keeps the reader's arrangement when the axes are unchanged", () => {
    expect(reconcile_order(["c", "a", "b"], ["a", "b", "c"])).toEqual([
      "c",
      "a",
      "b",
    ])
  })

  it("appends axes that appeared, without disturbing the arrangement", () => {
    expect(reconcile_order(["c", "a"], ["a", "c", "d"])).toEqual([
      "c",
      "a",
      "d",
    ])
  })

  it("drops axes that are gone", () => {
    expect(reconcile_order(["c", "a", "b"], ["a", "b"])).toEqual(["a", "b"])
  })

  it("starts from the given order when there is nothing arranged yet", () => {
    expect(reconcile_order([], ["a", "b"])).toEqual(["a", "b"])
  })

  it("survives a full swap of the axis set", () => {
    expect(reconcile_order(["a", "b"], ["x", "y"])).toEqual(["x", "y"])
  })
})

describe("axis_fraction", () => {
  it("maps each score type onto its own full range", () => {
    expect(axis_fraction(0.44, "pass_fail")).toBeCloseTo(0.44, 10)
    // five_star runs 1..5, so the midpoint is 3
    expect(axis_fraction(3, "five_star")).toBeCloseTo(0.5, 10)
    expect(axis_fraction(1, "five_star")).toBe(0)
    expect(axis_fraction(5, "five_star")).toBe(1)
    // pass_fail_critical runs -1..1
    expect(axis_fraction(0, "pass_fail_critical")).toBeCloseTo(0.5, 10)
    expect(axis_fraction(-1, "pass_fail_critical")).toBe(0)
  })

  it("clamps out-of-range values instead of plotting off the axis", () => {
    expect(axis_fraction(7, "five_star")).toBe(1)
    expect(axis_fraction(-3, "pass_fail")).toBe(0)
  })

  it("refuses score types with no full scale", () => {
    // custom scores are unbounded - they belong to the metrics chart
    expect(axis_fraction(120, "custom")).toBeNull()
    expect(axis_fraction(120, null)).toBeNull()
  })

  it("passes through null and non-finite values", () => {
    expect(axis_fraction(null, "pass_fail")).toBeNull()
    expect(axis_fraction(NaN, "pass_fail")).toBeNull()
  })
})

describe("build_cell", () => {
  it("bands a pass_fail score with its Wilson interval", () => {
    const cell = build_cell(0.44, 25, "pass_fail")
    expect(cell.banded).toBe(true)
    expect(cell.fraction).toBeCloseTo(0.44, 10)
    expect(cell.lower!).toBeLessThan(0.44)
    expect(cell.upper!).toBeGreaterThan(0.44)
    expect(cell.n).toBe(25)
  })

  it("keeps a banded interval inside the axis", () => {
    const perfect = build_cell(1, 25, "pass_fail")
    expect(perfect.upper).toBe(1)
    expect(perfect.lower!).toBeGreaterThan(0)
    expect(perfect.lower!).toBeLessThan(1)

    const zero = build_cell(0, 25, "pass_fail")
    expect(zero.lower).toBe(0)
    expect(zero.upper!).toBeGreaterThan(0)
  })

  it("plots the point but no band when the score type has no honest interval", () => {
    const cell = build_cell(4.2, 25, "five_star")
    expect(cell.banded).toBe(false)
    expect(cell.fraction).toBeCloseTo(0.8, 10)
    // A zero-height band, so a caller stacking lower + (upper - lower) draws nothing
    expect(cell.lower).toBe(cell.fraction)
    expect(cell.upper).toBe(cell.fraction)
  })

  it("plots the point but no band when the sample size is missing", () => {
    const cell = build_cell(0.44, null, "pass_fail")
    expect(cell.banded).toBe(false)
    expect(cell.lower).toBe(cell.upper)
    expect(cell.value).toBe(0.44)
  })

  it("is empty for an unscored cell", () => {
    const cell = build_cell(null, 25, "pass_fail")
    expect(cell).toEqual({
      fraction: null,
      lower: null,
      upper: null,
      value: null,
      n: null,
      banded: false,
    })
  })
})

describe("build_parallel_rows", () => {
  const axes: ParallelAxisSpec[] = [
    {
      key: "e1::grounded",
      label: "Grounded",
      evalName: "E1",
      type: "pass_fail",
    },
    { key: "e1::tone", label: "Tone", evalName: "E1", type: "five_star" },
  ]
  const values: Record<string, Record<string, number | null>> = {
    a: { "e1::grounded": 0.48, "e1::tone": 4 },
    b: { "e1::grounded": 0.72, "e1::tone": null },
    empty: { "e1::grounded": null, "e1::tone": null },
  }
  const sizes: Record<string, Record<string, number | null>> = {
    a: { "e1::grounded": 25, "e1::tone": 25 },
    b: { "e1::grounded": 25, "e1::tone": null },
    empty: { "e1::grounded": null, "e1::tone": null },
  }
  const getValue = (rc: string, key: string) => values[rc]?.[key] ?? null
  const getN = (rc: string, key: string) => sizes[rc]?.[key] ?? null

  it("builds one row per config, in the order given", () => {
    const rows = build_parallel_rows(axes, ["a", "b"], getValue, getN)
    expect(rows.map((row) => row.runConfigId)).toEqual(["a", "b"])
    expect(rows[0].cells).toHaveLength(2)
  })

  it("bands only the axis whose score type allows it", () => {
    const [row] = build_parallel_rows(axes, ["a"], getValue, getN)
    expect(row.cells[0].banded).toBe(true) // pass_fail
    expect(row.cells[1].banded).toBe(false) // five_star
  })

  it("marks a config with no scores at all rather than dropping it", () => {
    const rows = build_parallel_rows(axes, ["a", "empty"], getValue, getN)
    expect(rows[0].hasData).toBe(true)
    expect(rows[1].hasData).toBe(false)
    expect(rows[1].cells.every((cell) => cell.fraction === null)).toBe(true)
  })

  it("leaves a hole for one missing axis without losing the row", () => {
    const [row] = build_parallel_rows(axes, ["b"], getValue, getN)
    expect(row.hasData).toBe(true)
    expect(row.cells[0].fraction).toBeCloseTo(0.72, 10)
    expect(row.cells[1].fraction).toBeNull()
  })
})

describe("widest_band_pp", () => {
  const axes: ParallelAxisSpec[] = [
    { key: "k", label: "K", evalName: "E", type: "pass_fail" },
  ]

  it("reports the widest interval across every plotted cell", () => {
    // n=11 is wider than n=25 at the same rate
    const rows = build_parallel_rows(
      axes,
      ["small", "big"],
      (rc) => (rc === "small" ? 0.5 : 0.5),
      (rc) => (rc === "small" ? 11 : 25),
    )
    const widest = widest_band_pp(rows)
    expect(widest).not.toBeNull()
    expect(widest!).toBeGreaterThan(36)
    expect(widest!).toBeLessThan(60)
  })

  it("is null when nothing on the chart is banded", () => {
    const starAxes: ParallelAxisSpec[] = [
      { key: "k", label: "K", evalName: "E", type: "five_star" },
    ]
    const rows = build_parallel_rows(
      starAxes,
      ["a"],
      () => 4,
      () => 25,
    )
    expect(widest_band_pp(rows)).toBeNull()
  })
})
