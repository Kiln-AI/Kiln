import { describe, it, expect } from "vitest"
import type { TaskRunConfig } from "$lib/types"
import {
  build_forest,
  diff_axes,
  get_axis_values,
  primary_parent_id,
} from "./graph_assembly"

function agent_config(
  id: string,
  overrides: {
    created_at?: string
    derived_from_ids?: (string | null)[]
    notes?: string | null
    origin?: string | null
    starred?: boolean
    model_name?: string
    prompt_id?: string
    tools?: string[]
    temperature?: number
  } = {},
): TaskRunConfig {
  return {
    v: 1,
    id,
    created_at: overrides.created_at ?? "2026-01-01T00:00:00.000Z",
    created_by: "test",
    name: `Config ${id}`,
    description: null,
    starred: overrides.starred ?? false,
    model_type: "task_run_config",
    prompt: null,
    provenance: {
      notes: overrides.notes ?? null,
      derived_from_ids: overrides.derived_from_ids ?? [],
      origin: overrides.origin ?? null,
    },
    run_config_properties: {
      type: "kiln_agent",
      model_name: overrides.model_name ?? "gpt-4",
      model_provider_name: "openai",
      prompt_id: overrides.prompt_id ?? "p1",
      temperature: overrides.temperature ?? 0.7,
      top_p: 1,
      structured_output_mode: "default",
      input_transform: null,
      thinking_level: null,
      tools_config: overrides.tools ? { tools: overrides.tools } : undefined,
    },
  } as TaskRunConfig
}

function mcp_config(id: string): TaskRunConfig {
  return {
    v: 1,
    id,
    created_at: "2026-01-01T00:00:00.000Z",
    created_by: "test",
    name: `MCP ${id}`,
    description: null,
    starred: false,
    model_type: "task_run_config",
    prompt: null,
    run_config_properties: {
      type: "mcp",
      tool_reference: { tool_id: "t1", tool_name: "Demo" },
    },
  } as TaskRunConfig
}

describe("get_axis_values", () => {
  it("normalizes a kiln_agent config's axes to strings", () => {
    const values = get_axis_values(
      agent_config("a", { tools: ["z_tool", "a_tool"], temperature: 0.5 }),
    )
    expect(values).not.toBeNull()
    expect(values?.model).toBe("gpt-4")
    expect(values?.prompt).toBe("p1")
    expect(values?.temperature).toBe("0.5")
    // Tool order is not meaningful, so it's sorted before joining
    expect(values?.tools).toBe("a_tool, z_tool")
    expect(values?.thinking).toBe("none")
  })

  it("returns null for MCP configs and for ghosts (no config)", () => {
    expect(get_axis_values(mcp_config("m"))).toBeNull()
    expect(get_axis_values(null)).toBeNull()
  })
})

describe("diff_axes", () => {
  it("reports only the axes that differ", () => {
    const changes = diff_axes(
      agent_config("a", { model_name: "gpt-4" }),
      agent_config("b", { model_name: "gpt-5", prompt_id: "p2" }),
    )
    expect(changes.map((c) => c.axis).sort()).toEqual(["model", "prompt"])
    const model = changes.find((c) => c.axis === "model")
    expect(model).toEqual({ axis: "model", from: "gpt-4", to: "gpt-5" })
  })

  it("returns no changes when an MCP config is involved", () => {
    expect(diff_axes(mcp_config("m"), agent_config("a"))).toEqual([])
  })
})

describe("build_forest", () => {
  it("links parents and children, and marks the first parent primary", () => {
    const forest = build_forest([
      agent_config("root"),
      agent_config("child", { derived_from_ids: ["root", "other"] }),
      agent_config("other"),
    ])

    const child = forest.nodes.get("child")!
    expect(child.parents).toEqual([
      { parentId: "root", primary: true },
      { parentId: "other", primary: false },
    ])
    expect(forest.nodes.get("root")!.children).toEqual(["child"])
    expect(child.depth).toBe(1)
    expect(forest.edges.map((e) => e.id).sort()).toEqual([
      "other->child",
      "root->child",
    ])
  })

  it("records changed axes and the note summary on an edge", () => {
    const forest = build_forest([
      agent_config("root", { model_name: "gpt-4" }),
      agent_config("child", {
        derived_from_ids: ["root"],
        model_name: "gpt-5",
        notes: "Swapped the model\nsecond line ignored in the summary",
      }),
    ])
    const edge = forest.edges.find((e) => e.id === "root->child")!
    expect(edge.changedAxes).toEqual([
      { axis: "model", from: "gpt-4", to: "gpt-5" },
    ])
    expect(edge.noteSummary).toBe("Swapped the model")
    expect(forest.nodes.get("child")!.noteFull).toContain("second line")
  })

  it("materializes a dangling parent id as a ghost node with no diff", () => {
    const forest = build_forest([
      agent_config("child", { derived_from_ids: ["deleted"] }),
    ])
    const ghost = forest.nodes.get("deleted")!
    expect(ghost.ghost).toBe(true)
    expect(ghost.config).toBeNull()
    expect(ghost.name).toBe("Deleted config")
    expect(ghost.children).toEqual(["child"])
    // A ghost has no properties to diff against
    expect(forest.edges[0].changedAxes).toEqual([])
  })

  it("breaks cycles, marking the closing edge and keeping depth finite", () => {
    const forest = build_forest([
      agent_config("a", { derived_from_ids: ["b"] }),
      agent_config("b", { derived_from_ids: ["a"] }),
    ])
    const broken = forest.edges.filter((e) => e.cycleBroken)
    expect(broken).toHaveLength(1)
    // The dropped edge is gone from the node links, not just flagged
    const parent_count =
      forest.nodes.get("a")!.parents.length +
      forest.nodes.get("b")!.parents.length
    expect(parent_count).toBe(1)
    for (const node of forest.nodes.values()) {
      expect(Number.isFinite(node.depth)).toBe(true)
      expect(node.depth).toBeLessThanOrEqual(1)
    }
  })

  it("ignores self-parents and duplicate parent ids", () => {
    const forest = build_forest([
      agent_config("root"),
      agent_config("child", {
        derived_from_ids: ["child", "root", "root", null],
      }),
    ])
    expect(forest.nodes.get("child")!.parents).toEqual([
      { parentId: "root", primary: true },
    ])
    expect(forest.edges).toHaveLength(1)
  })

  it("takes depth from the longest path when parents disagree", () => {
    const forest = build_forest([
      agent_config("a"),
      agent_config("b", { derived_from_ids: ["a"] }),
      // c has a depth-0 and a depth-1 parent; the longest path wins
      agent_config("c", { derived_from_ids: ["a", "b"] }),
    ])
    expect(forest.nodes.get("c")!.depth).toBe(2)
  })

  it("lists unlinked configs newest first and keeps them out of components", () => {
    const forest = build_forest([
      agent_config("old", { created_at: "2026-01-01T00:00:00.000Z" }),
      agent_config("new", { created_at: "2026-03-01T00:00:00.000Z" }),
      agent_config("root", { created_at: "2026-02-01T00:00:00.000Z" }),
      agent_config("child", {
        created_at: "2026-02-02T00:00:00.000Z",
        derived_from_ids: ["root"],
      }),
    ])
    expect(forest.unlinkedIds).toEqual(["new", "old"])
    expect(forest.components).toHaveLength(1)
    expect(forest.components[0].rootIds).toEqual(["root"])
    expect(forest.components[0].nodeIds.sort()).toEqual(["child", "root"])
  })

  it("assigns every linked node a component id and sorts components by age", () => {
    const forest = build_forest([
      agent_config("late_root", { created_at: "2026-05-01T00:00:00.000Z" }),
      agent_config("late_child", {
        created_at: "2026-05-02T00:00:00.000Z",
        derived_from_ids: ["late_root"],
      }),
      agent_config("early_root", { created_at: "2026-01-01T00:00:00.000Z" }),
      agent_config("early_child", {
        created_at: "2026-01-02T00:00:00.000Z",
        derived_from_ids: ["early_root"],
      }),
    ])
    expect(forest.components).toHaveLength(2)
    expect(forest.components[0].nodeIds).toContain("early_root")
    expect(forest.nodes.get("early_root")!.componentId).toBe("c0")
    expect(forest.nodes.get("late_root")!.componentId).toBe("c1")
  })

  it("skips configs with no id and parses only known origins", () => {
    const no_id = agent_config("x", { origin: "agent" })
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(no_id as any).id = null
    const forest = build_forest([
      no_id,
      agent_config("human_made", { origin: "human" }),
      agent_config("unknown_origin", { origin: "robot" }),
    ])
    expect(forest.nodes.size).toBe(2)
    expect(forest.nodes.get("human_made")!.origin).toBe("human")
    expect(forest.nodes.get("unknown_origin")!.origin).toBeNull()
  })
})

describe("primary_parent_id", () => {
  it("returns null with no parents, and prefers the primary edge", () => {
    const forest = build_forest([
      agent_config("root"),
      agent_config("second"),
      agent_config("child", { derived_from_ids: ["root", "second"] }),
    ])
    expect(primary_parent_id(forest.nodes.get("root")!)).toBeNull()
    expect(primary_parent_id(forest.nodes.get("child")!)).toBe("root")
  })

  it("falls back to the first parent when the primary edge was cycle-broken", () => {
    const node = {
      parents: [
        { parentId: "kept_a", primary: false },
        { parentId: "kept_b", primary: false },
      ],
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any
    expect(primary_parent_id(node)).toBe("kept_a")
  })
})
