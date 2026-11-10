import { describe, expect, it } from "vitest"
import type { TaskRunConfig } from "$lib/types"
import { build_lineage_graph } from "./lineage_graph"
import { layout_lineage } from "./lineage_layout"
import { next_selection, type NavKey } from "./lineage_navigation"
import { make_dated_config } from "./__tests__/lineage_fixtures"

function navigator(configs: TaskRunConfig[]) {
  const graph = build_lineage_graph(configs)
  const layout = layout_lineage(graph)
  return (current: string | null, key: NavKey) =>
    next_selection(graph, layout, current, key)
}

// Rows: [root], [a, b], [a1], then the grid [alone].
const move = navigator([
  make_dated_config("root", 0),
  make_dated_config("a", 1, ["root"]),
  make_dated_config("b", 2, ["root"]),
  make_dated_config("a1", 3, ["a"]),
  make_dated_config("alone", 4),
])

describe("next_selection", () => {
  it("goes up to the primary parent", () => {
    expect(move("a1", "ArrowUp")).toBe("a")
    expect(move("a", "ArrowUp")).toBe("root")
  })

  it("goes down to the oldest child", () => {
    expect(move("root", "ArrowDown")).toBe("a")
    expect(move("a", "ArrowDown")).toBe("a1")
  })

  it("moves left and right within a row", () => {
    expect(move("a", "ArrowRight")).toBe("b")
    expect(move("b", "ArrowLeft")).toBe("a")
  })

  it("stays put when there is nowhere to go", () => {
    expect(move("root", "ArrowUp")).toBe("root")
    expect(move("a", "ArrowLeft")).toBe("a")
    expect(move("b", "ArrowRight")).toBe("b")
    expect(move("alone", "ArrowRight")).toBe("alone")
    expect(move("alone", "ArrowDown")).toBe("alone")
  })

  it("stays on a node with no children when there is no grid", () => {
    const move_tree = navigator([
      make_dated_config("root", 0),
      make_dated_config("child", 1, ["root"]),
    ])
    expect(move_tree("child", "ArrowDown")).toBe("child")
  })

  describe("between the tree and the grid", () => {
    // Rows: [root], [a, b], [a1], then the grid [g0 g1 g2 g3 g4], [g5].
    const move_with_grid = navigator([
      make_dated_config("root", 0),
      make_dated_config("a", 1, ["root"]),
      make_dated_config("b", 2, ["root"]),
      make_dated_config("a1", 3, ["a"]),
      ...[0, 1, 2, 3, 4, 5].map((i) => make_dated_config(`g${i}`, 10 + i)),
    ])

    it("goes down from a node with no children to the nearest node in the grid's first row", () => {
      expect(move_with_grid("a1", "ArrowDown")).toBe("g0")
      expect(move_with_grid("b", "ArrowDown")).toBe("g1")
    })

    it("goes up from the grid's first row to the nearest node in the tree's bottom row", () => {
      expect(move_with_grid("g0", "ArrowUp")).toBe("a1")
      expect(move_with_grid("g3", "ArrowUp")).toBe("a1")
    })

    it("moves up and down between grid rows", () => {
      expect(move_with_grid("g0", "ArrowDown")).toBe("g5")
      expect(move_with_grid("g3", "ArrowDown")).toBe("g5")
      expect(move_with_grid("g5", "ArrowUp")).toBe("g0")
      expect(move_with_grid("g5", "ArrowDown")).toBe("g5")
    })

    it("picks the node nearest in x between grid rows", () => {
      // No tree, 9 configs: 6 columns, so rows [g0 .. g5], [g6 g7 g8].
      const move_grid_rows = navigator(
        [0, 1, 2, 3, 4, 5, 6, 7, 8].map((i) => make_dated_config(`g${i}`, i)),
      )
      expect(move_grid_rows("g1", "ArrowDown")).toBe("g7")
      expect(move_grid_rows("g5", "ArrowDown")).toBe("g8")
      expect(move_grid_rows("g7", "ArrowUp")).toBe("g1")
    })

    it("picks the leftmost node on a tie", () => {
      // Rows: [root], [a, m, c], [a1, c1], then the grid [g0 g1].
      const move_tie = navigator([
        make_dated_config("root", 0),
        make_dated_config("a", 1, ["root"]),
        make_dated_config("m", 2, ["root"]),
        make_dated_config("c", 3, ["root"]),
        make_dated_config("a1", 4, ["a"]),
        make_dated_config("c1", 5, ["c"]),
        make_dated_config("g0", 10),
        make_dated_config("g1", 11),
      ])
      expect(move_tie("g1", "ArrowUp")).toBe("a1")
      expect(move_tie("m", "ArrowDown")).toBe("g1")
    })
  })

  it("selects the oldest starting point when nothing is selected", () => {
    expect(move(null, "ArrowDown")).toBe("root")
    expect(move("not_in_graph", "ArrowLeft")).toBe("root")
  })

  it("skips a deleted placeholder for the first selection", () => {
    const move_with_placeholder = navigator([
      make_dated_config("orphan", 1, ["gone"]),
      make_dated_config("root", 5),
      make_dated_config("child", 6, ["root"]),
    ])
    expect(move_with_placeholder(null, "ArrowUp")).toBe("root")
  })

  it("selects the first grid node when there is no tree", () => {
    const move_grid = navigator([
      make_dated_config("second", 2),
      make_dated_config("first", 1),
    ])
    expect(move_grid(null, "ArrowRight")).toBe("first")
    expect(move_grid("first", "ArrowUp")).toBe("first")
  })

  it("returns null for an empty graph", () => {
    expect(navigator([])(null, "ArrowDown")).toBeNull()
  })
})
