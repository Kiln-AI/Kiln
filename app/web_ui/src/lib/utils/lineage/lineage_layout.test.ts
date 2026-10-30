import { describe, expect, it } from "vitest"
import type { TaskRunConfig } from "$lib/types"
import { build_lineage_graph } from "./lineage_graph"
import { LAYOUT, layout_lineage, type LineageLayout } from "./lineage_layout"
import {
  make_chain,
  make_dated_config,
  make_random_lineage,
} from "./__tests__/lineage_fixtures"

const STEP = LAYOUT.node + LAYOUT.col_gap

function layout_of(configs: TaskRunConfig[]): LineageLayout {
  return layout_lineage(build_lineage_graph(configs))
}

function position(layout: LineageLayout, id: string): { x: number; y: number } {
  const found = layout.positions.get(id)
  if (!found) {
    throw new Error(`no position for ${id}`)
  }
  return found
}

function tree_y(row: number): number {
  return LAYOUT.padding + row * LAYOUT.row_height
}

function col_x(col: number): number {
  return LAYOUT.padding + col * STEP
}

describe("layout_lineage", () => {
  it("draws a chain as one column", () => {
    const layout = layout_lineage(build_lineage_graph(make_chain(4)))
    for (let i = 0; i < 4; i++) {
      expect(position(layout, `rc_${i}`)).toEqual({
        x: col_x(0),
        y: tree_y(i),
      })
    }
  })

  it("centers a parent over its first and last children", () => {
    const layout = layout_of([
      make_dated_config("root", 0),
      make_dated_config("c1", 1, ["root"]),
      make_dated_config("c2", 2, ["root"]),
      make_dated_config("c3", 3, ["root"]),
    ])
    expect(position(layout, "c1").x).toBe(col_x(0))
    expect(position(layout, "c3").x).toBe(col_x(2))
    expect(position(layout, "root")).toEqual({ x: col_x(1), y: tree_y(0) })
  })

  it("places trees side by side, oldest root first", () => {
    const layout = layout_of([
      make_dated_config("late_root", 1),
      make_dated_config("early_root", 0),
      make_dated_config("a", 2, ["early_root"]),
      make_dated_config("b", 3, ["early_root"]),
      make_dated_config("c", 4, ["late_root"]),
    ])
    expect(position(layout, "a").x).toBe(col_x(0))
    expect(position(layout, "b").x).toBe(col_x(1))
    expect(position(layout, "early_root").x).toBe(col_x(0.5))
    expect(position(layout, "c").x).toBe(col_x(2))
    expect(position(layout, "late_root").x).toBe(col_x(2))
  })

  it("places a merge under its primary parent and below its lowest parent", () => {
    const layout = layout_of([
      make_dated_config("a", 0),
      make_dated_config("b", 1, ["a"]),
      make_dated_config("c", 2, ["a", "b"]),
    ])
    expect(position(layout, "a")).toEqual({ x: col_x(0.5), y: tree_y(0) })
    expect(position(layout, "b")).toEqual({ x: col_x(0), y: tree_y(1) })
    expect(position(layout, "c")).toEqual({ x: col_x(1), y: tree_y(2) })
  })

  it("never overlaps two nodes in a row", () => {
    const graph = build_lineage_graph(make_random_lineage(200, 42))
    const layout = layout_lineage(graph)
    expect(layout.positions.size).toBe(graph.nodes.size)
    for (const row of layout.rows) {
      for (let i = 1; i < row.length; i++) {
        const gap = position(layout, row[i]).x - position(layout, row[i - 1]).x
        expect(gap).toBeGreaterThanOrEqual(STEP)
      }
    }
  })

  it("draws elbow edges from a parent's bottom to a child's top", () => {
    const layout = layout_of([
      make_dated_config("a", 0),
      make_dated_config("b", 1, ["a"]),
      make_dated_config("c", 2, ["a", "b"]),
    ])
    const by_id = new Map(layout.edges.map((e) => [e.id, e]))
    // a at (25, 16), b at (16, 44), c at (34, 72).
    expect(by_id.get("a->b")).toEqual({
      id: "a->b",
      primary: true,
      d: "M32 30V37H23V44",
    })
    expect(by_id.get("b->c")).toEqual({
      id: "b->c",
      primary: false,
      d: "M23 58V65H41V72",
    })
  })

  it("groups rows by y and sorts each by x", () => {
    const layout = layout_of([
      make_dated_config("root", 0),
      make_dated_config("c2", 2, ["root"]),
      make_dated_config("c1", 1, ["root"]),
      make_dated_config("grid", 3),
    ])
    expect(layout.rows).toEqual([["root"], ["c1", "c2"], ["grid"]])
  })

  it("sizes the world to the nodes plus padding", () => {
    const layout = layout_of([
      make_dated_config("root", 0),
      make_dated_config("c1", 1, ["root"]),
      make_dated_config("c2", 2, ["root"]),
    ])
    expect(layout.width).toBe(col_x(1) + LAYOUT.node + LAYOUT.padding)
    expect(layout.height).toBe(tree_y(1) + LAYOUT.node + LAYOUT.padding)
  })

  it("returns an empty layout for an empty graph", () => {
    expect(layout_of([])).toEqual({
      positions: new Map(),
      edges: [],
      grid_label: null,
      rows: [],
      width: 0,
      height: 0,
    })
  })

  it("lays out 1,000 nodes", () => {
    const graph = build_lineage_graph(make_random_lineage(1000, 7))
    const layout = layout_lineage(graph)
    expect(layout.positions.size).toBe(graph.nodes.size)
    expect(layout.edges).toHaveLength(graph.edges.length)
    expect(Number.isFinite(layout.width)).toBe(true)
    expect(Number.isFinite(layout.height)).toBe(true)
  })
})

describe("layout_lineage grid", () => {
  const grid_configs = (n: number, first_minute = 100) =>
    Array.from({ length: n }, (_, i) =>
      make_dated_config(`g${i}`, first_minute + i),
    )

  it("is about four times wider than tall without a tree", () => {
    const layout = layout_of(grid_configs(9))
    const grid_top = LAYOUT.padding + LAYOUT.label_height
    // ceil(sqrt(9 * 4)) = 6 columns.
    expect(position(layout, "g0")).toEqual({ x: col_x(0), y: grid_top })
    expect(position(layout, "g5")).toEqual({ x: col_x(5), y: grid_top })
    expect(position(layout, "g6")).toEqual({ x: col_x(0), y: grid_top + STEP })
    expect(layout.grid_label).toEqual({ x: LAYOUT.padding, y: grid_top - 6 })
  })

  it("is as wide as the tree, below it", () => {
    const tree = [
      make_dated_config("root", 0),
      ...Array.from({ length: 8 }, (_, i) =>
        make_dated_config(`c${i}`, i + 1, ["root"]),
      ),
    ]
    const layout = layout_of([...tree, ...grid_configs(9)])
    const tree_bottom = tree_y(1) + LAYOUT.node
    const grid_top = tree_bottom + LAYOUT.section_gap + LAYOUT.label_height
    // The tree is 8 columns wide, more than ceil(sqrt(9 * 4)) = 6.
    expect(position(layout, "g7")).toEqual({ x: col_x(7), y: grid_top })
    expect(position(layout, "g8")).toEqual({ x: col_x(0), y: grid_top + STEP })
    expect(layout.grid_label).toEqual({ x: LAYOUT.padding, y: grid_top - 6 })
  })

  it("grows wider than a narrow tree", () => {
    const layout = layout_of([
      make_dated_config("root", 0),
      make_dated_config("child", 1, ["root"]),
      ...grid_configs(25),
    ])
    // ceil(sqrt(25 * 4)) = 10 columns.
    expect(position(layout, "g9").x).toBe(col_x(9))
    expect(position(layout, "g10").x).toBe(col_x(0))
  })

  it("has no label without grid nodes", () => {
    expect(layout_of(make_chain(2)).grid_label).toBeNull()
  })
})
