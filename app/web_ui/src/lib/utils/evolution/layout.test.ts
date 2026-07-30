import { describe, it, expect } from "vitest"
import type { TaskRunConfig } from "$lib/types"
import { build_forest } from "./graph_assembly"
import {
  COMPONENT_GAP,
  H_GAP_SIB,
  NODE_H,
  NODE_W,
  V_GAP_GEN,
  layout_forest,
} from "./layout"

function config(
  id: string,
  created_at: string,
  derived_from_ids: string[] = [],
): TaskRunConfig {
  return {
    v: 1,
    id,
    created_at,
    created_by: "test",
    name: `Config ${id}`,
    description: null,
    starred: false,
    model_type: "task_run_config",
    prompt: null,
    provenance: { notes: null, derived_from_ids, origin: null },
    run_config_properties: {
      type: "kiln_agent",
      model_name: "gpt-4",
      model_provider_name: "openai",
      prompt_id: "p1",
      temperature: 0.7,
      top_p: 1,
      structured_output_mode: "default",
      input_transform: null,
      thinking_level: null,
    },
  } as TaskRunConfig
}

const ROW_PITCH = NODE_H + V_GAP_GEN

describe("layout_forest", () => {
  it("puts a generation on one horizontal row, keyed by depth", () => {
    const forest = build_forest([
      config("root", "2026-01-01T00:00:00.000Z"),
      config("a", "2026-01-02T00:00:00.000Z", ["root"]),
      config("b", "2026-01-03T00:00:00.000Z", ["root"]),
      config("leaf", "2026-01-04T00:00:00.000Z", ["a"]),
    ])
    const { positions } = layout_forest(forest)

    expect(positions.get("root")!.y).toBe(0)
    expect(positions.get("a")!.y).toBe(ROW_PITCH)
    expect(positions.get("b")!.y).toBe(ROW_PITCH)
    expect(positions.get("leaf")!.y).toBe(2 * ROW_PITCH)
  })

  it("separates siblings in a row by at least a card width plus the gap", () => {
    const forest = build_forest([
      config("root", "2026-01-01T00:00:00.000Z"),
      config("a", "2026-01-02T00:00:00.000Z", ["root"]),
      config("b", "2026-01-03T00:00:00.000Z", ["root"]),
      config("c", "2026-01-04T00:00:00.000Z", ["root"]),
    ])
    const { positions } = layout_forest(forest)

    const row = ["a", "b", "c"]
      .map((id) => positions.get(id)!.x)
      .sort((x, y) => x - y)
    for (let i = 1; i < row.length; i++) {
      expect(row[i] - row[i - 1]).toBeGreaterThanOrEqual(NODE_W + H_GAP_SIB)
    }
  })

  it("never overlaps two cards in a generation row, even with merge nodes", () => {
    // A tangled component: two roots, a shared merge child, a deep chain and a
    // node whose depth (from its deepest parent) is far below its placement
    // parent. That mismatch is exactly what the per-row collision pass exists
    // to absorb, so assert its guarantee rather than one hand-picked push.
    const forest = build_forest([
      config("r1", "2026-01-01T00:00:00.000Z"),
      config("r2", "2026-01-02T00:00:00.000Z"),
      config("merge", "2026-01-03T00:00:00.000Z", ["r1", "r2"]),
      config("chain1", "2026-01-04T00:00:00.000Z", ["merge"]),
      config("chain2", "2026-01-05T00:00:00.000Z", ["chain1"]),
      config("chain3", "2026-01-06T00:00:00.000Z", ["chain2"]),
      // Placed under r1 (its primary parent) but drawn as deep as chain3+1
      config("shortcut", "2026-01-07T00:00:00.000Z", ["r1", "chain3"]),
      config("sib", "2026-01-08T00:00:00.000Z", ["r1"]),
    ])
    const { positions } = layout_forest(forest)

    const rows = new Map<number, number[]>()
    for (const [id, pos] of positions) {
      expect(forest.nodes.get(id)).toBeTruthy()
      rows.set(pos.y, [...(rows.get(pos.y) ?? []), pos.x])
    }
    expect(rows.size).toBeGreaterThan(1)
    for (const xs of rows.values()) {
      const sorted = [...xs].sort((a, b) => a - b)
      for (let i = 1; i < sorted.length; i++) {
        // Each card clears the previous card's right edge by the sibling gap
        expect(sorted[i]).toBeGreaterThanOrEqual(
          sorted[i - 1] + NODE_W + H_GAP_SIB,
        )
      }
    }
  })

  it("centers a parent over its placement children", () => {
    const forest = build_forest([
      config("root", "2026-01-01T00:00:00.000Z"),
      config("a", "2026-01-02T00:00:00.000Z", ["root"]),
      config("b", "2026-01-03T00:00:00.000Z", ["root"]),
    ])
    const { positions } = layout_forest(forest)
    const midpoint = (positions.get("a")!.x + positions.get("b")!.x) / 2
    expect(positions.get("root")!.x).toBeCloseTo(midpoint, 5)
  })

  it("stacks components vertically with COMPONENT_GAP between them", () => {
    const forest = build_forest([
      config("early_root", "2026-01-01T00:00:00.000Z"),
      config("early_child", "2026-01-02T00:00:00.000Z", ["early_root"]),
      config("late_root", "2026-05-01T00:00:00.000Z"),
      config("late_child", "2026-05-02T00:00:00.000Z", ["late_root"]),
    ])
    const { positions } = layout_forest(forest)

    // First component starts at y = 0 and is two rows tall
    expect(positions.get("early_root")!.y).toBe(0)
    const first_bottom = positions.get("early_child")!.y + NODE_H
    expect(positions.get("late_root")!.y).toBe(first_bottom + COMPONENT_GAP)
    // Every component is left-aligned at x = 0
    expect(Math.min(...[...positions.values()].map((p) => p.x))).toBe(0)
  })

  it("draws each edge as a vertical S-curve with the midpoint as chip anchor", () => {
    const forest = build_forest([
      config("root", "2026-01-01T00:00:00.000Z"),
      config("child", "2026-01-02T00:00:00.000Z", ["root"]),
    ])
    const { positions, edgePaths } = layout_forest(forest)

    const parent = positions.get("root")!
    const child = positions.get("child")!
    const x1 = parent.x + NODE_W / 2
    const y1 = parent.y + NODE_H
    const x2 = child.x + NODE_W / 2
    const y2 = child.y
    const mid_y = (y1 + y2) / 2

    const path = edgePaths.get("root->child")!
    expect(path.d).toBe(
      `M ${x1} ${y1} C ${x1} ${mid_y}, ${x2} ${mid_y}, ${x2} ${y2}`,
    )
    // Leaves the parent's bottom edge, arrives at the child's top edge
    expect(y1).toBeLessThan(y2)
    expect(path.chipAt).toEqual({ x: (x1 + x2) / 2, y: mid_y })
  })

  it("sizes the world to the furthest card's far corner", () => {
    const forest = build_forest([
      config("root", "2026-01-01T00:00:00.000Z"),
      config("a", "2026-01-02T00:00:00.000Z", ["root"]),
      config("b", "2026-01-03T00:00:00.000Z", ["root"]),
    ])
    const { positions, world } = layout_forest(forest)
    const max_x = Math.max(...[...positions.values()].map((p) => p.x))
    const max_y = Math.max(...[...positions.values()].map((p) => p.y))
    expect(world.width).toBe(max_x + NODE_W)
    expect(world.height).toBe(max_y + NODE_H)
  })

  it("returns an empty layout for a forest with no linked nodes", () => {
    const forest = build_forest([config("lonely", "2026-01-01T00:00:00.000Z")])
    const layout = layout_forest(forest)
    expect(layout.positions.size).toBe(0)
    expect(layout.edgePaths.size).toBe(0)
    expect(layout.world).toEqual({ width: 0, height: 0 })
  })

  it("places a multi-parent node under its primary parent only", () => {
    const forest = build_forest([
      config("primary", "2026-01-01T00:00:00.000Z"),
      config("secondary", "2026-01-02T00:00:00.000Z"),
      config("merged", "2026-01-03T00:00:00.000Z", ["primary", "secondary"]),
    ])
    const { positions } = layout_forest(forest)
    // The primary parent is centered over its one placement child
    expect(positions.get("primary")!.x).toBe(positions.get("merged")!.x)
    expect(positions.get("secondary")!.x).not.toBe(positions.get("merged")!.x)
  })
})
