import { describe, it, expect } from "vitest"
import type { TaskRunConfig } from "$lib/types"
import { build_forest } from "./graph_assembly"
import { layout_forest } from "./layout"
import {
  MAP_SIZES,
  MAP_UNLINKED_GAP,
  layout_map,
  map_kinds,
  map_summary,
} from "./map_view"

function config(
  id: string,
  created_at: string,
  derived_from_ids: string[] = [],
  overrides: Partial<{
    model_name: string
    model_provider_name: string
    prompt_id: string
    thinking_level: string | null
  }> = {},
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
      ...overrides,
    },
  } as TaskRunConfig
}

const lineage = [
  config("root", "2026-01-01T00:00:00.000Z"),
  config("prompt", "2026-01-02T00:00:00.000Z", ["root"], { prompt_id: "p2" }),
  config("model", "2026-01-03T00:00:00.000Z", ["root"], {
    model_name: "claude",
    model_provider_name: "anthropic",
  }),
  config("copy", "2026-01-04T00:00:00.000Z", ["prompt"], { prompt_id: "p2" }),
]

describe("layout_map", () => {
  it("lays out the lineage tree on map-sized blocks", () => {
    const forest = build_forest(lineage)
    const map = layout_map(forest)
    const tree = layout_forest(forest, MAP_SIZES)

    expect(map.positions).toEqual(tree.positions)
    expect(map.world).toEqual(tree.world)
    expect(map.unlinkedLabelAt).toBeNull()
    expect(map.positions.get("prompt")!.y).toBe(
      MAP_SIZES.nodeH + MAP_SIZES.vGap,
    )
  })

  it("puts unlinked run configs in a grid below the tree, oldest first", () => {
    const forest = build_forest([
      ...lineage,
      config("lone_b", "2026-02-02T00:00:00.000Z"),
      config("lone_a", "2026-02-01T00:00:00.000Z"),
    ])
    const tree = layout_forest(forest, MAP_SIZES)
    const map = layout_map(forest)
    const top = tree.world.height + MAP_UNLINKED_GAP

    expect(map.unlinkedLabelAt).toEqual({ x: 0, y: top })
    expect(map.positions.get("lone_a")).toEqual({ x: 0, y: top })
    expect(map.positions.get("lone_b")).toEqual({
      x: MAP_SIZES.nodeW + MAP_SIZES.hGap,
      y: top,
    })
    expect(map.world.height).toBe(top + MAP_SIZES.nodeH)
    // Every run config has a block: the tree and the unlinked grid
    expect(map.positions.size).toBe(6)
  })

  it("wraps a long unlinked grid at the tree's width", () => {
    const loner_ids = Array.from({ length: 30 }, (_, i) => `lone_${i}`)
    const loners = loner_ids.map((id, i) =>
      config(id, `2026-02-${String(i + 1).padStart(2, "0")}`),
    )
    const forest = build_forest([...lineage, ...loners])
    const map = layout_map(forest)
    const ys = new Set(loner_ids.map((id) => map.positions.get(id)!.y))

    expect(ys.size).toBeGreaterThan(1)
    for (const id of loner_ids) {
      expect(map.positions.get(id)!.x + MAP_SIZES.nodeW).toBeLessThanOrEqual(
        map.world.width,
      )
    }
  })

  it("gives a task with no lineage a grid only", () => {
    const forest = build_forest([
      config("a", "2026-01-01T00:00:00.000Z"),
      config("b", "2026-01-02T00:00:00.000Z"),
    ])
    const map = layout_map(forest)

    expect(map.unlinkedLabelAt).toEqual({ x: 0, y: 0 })
    expect(map.positions.get("a")).toEqual({ x: 0, y: 0 })
    expect(map.edgePaths.size).toBe(0)
  })
})

describe("map_kinds", () => {
  it("names what each run config changed against its parent", () => {
    const forest = build_forest([
      ...lineage,
      config("lone", "2026-02-01T00:00:00.000Z"),
    ])
    const kinds = map_kinds(forest)

    expect(kinds.get("root")).toBe("start")
    expect(kinds.get("prompt")).toBe("prompt_tools")
    expect(kinds.get("model")).toBe("model_settings")
    expect(kinds.get("copy")).toBe("same")
    expect(kinds.get("lone")).toBe("unlinked")
  })

  it("counts a prompt change with a model change as a prompt change", () => {
    const forest = build_forest([
      config("root", "2026-01-01T00:00:00.000Z"),
      config("both", "2026-01-02T00:00:00.000Z", ["root"], {
        prompt_id: "p2",
        model_name: "claude",
      }),
    ])

    expect(map_kinds(forest).get("both")).toBe("prompt_tools")
  })

  it("marks a deleted parent as deleted", () => {
    const forest = build_forest([
      config("child", "2026-01-02T00:00:00.000Z", ["gone"]),
    ])

    expect(map_kinds(forest).get("gone")).toBe("deleted")
  })
})

describe("map_summary", () => {
  it("counts run configs, models, providers and kinds", () => {
    const forest = build_forest([
      ...lineage,
      config("orphan", "2026-01-05T00:00:00.000Z", ["gone"]),
    ])
    const kinds = map_kinds(forest)
    const summary = map_summary(forest, kinds)

    // The deleted parent is drawn but is not a run config
    expect(summary.runConfigs).toBe(5)
    expect(summary.models).toBe(2)
    expect(summary.providers).toBe(2)
    expect(summary.kindCounts.get("deleted")).toBe(1)
    expect(summary.kindCounts.get("start")).toBe(1)
    expect(summary.kindCounts.get("same")).toBe(2)
  })
})
