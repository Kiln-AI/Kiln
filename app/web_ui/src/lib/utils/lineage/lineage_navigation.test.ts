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
    expect(move("a1", "ArrowDown")).toBe("a1")
    expect(move("a", "ArrowLeft")).toBe("a")
    expect(move("b", "ArrowRight")).toBe("b")
    expect(move("alone", "ArrowRight")).toBe("alone")
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
  })

  it("returns null for an empty graph", () => {
    expect(navigator([])(null, "ArrowDown")).toBeNull()
  })
})
