import { describe, expect, it } from "vitest"
import {
  ancestor_edge_ids,
  build_lineage_graph,
  node_matches_filters,
  summarize_lineage,
  type FilterKey,
  type LineageGraph,
  type LineageNode,
  type LineageStatus,
} from "./lineage_graph"
import {
  created_at_for,
  make_agent_config,
  make_chain,
  make_dated_config,
  make_mcp_config,
} from "./__tests__/lineage_fixtures"

function node(graph: LineageGraph, id: string): LineageNode {
  const found = graph.nodes.get(id)
  if (!found) {
    throw new Error(`no node ${id}`)
  }
  return found
}

describe("build_lineage_graph", () => {
  it("makes one edge per parent, and only the first is primary", () => {
    const graph = build_lineage_graph([
      make_dated_config("a", 0),
      make_dated_config("b", 1),
      make_dated_config("c", 2, ["a", "b"]),
    ])
    expect(graph.edges).toEqual([
      { id: "a->c", parent_id: "a", child_id: "c", primary: true },
      { id: "b->c", parent_id: "b", child_id: "c", primary: false },
    ])
    expect(node(graph, "c").parent_ids).toEqual(["a", "b"])
    expect(node(graph, "a").child_ids).toEqual(["c"])
    expect(node(graph, "b").child_ids).toEqual(["c"])
  })

  it("shares one placeholder for a missing parent", () => {
    const graph = build_lineage_graph([
      make_dated_config("x", 1, ["gone"]),
      make_dated_config("y", 2, ["gone"]),
    ])
    const placeholder = node(graph, "gone")
    expect(placeholder.config).toBeNull()
    expect(placeholder.status).toEqual({ type: "deleted" })
    expect(placeholder.child_ids).toEqual(["x", "y"])
    expect(node(graph, "x").status).toEqual({ type: "parent_deleted" })
    expect(node(graph, "y").status).toEqual({ type: "parent_deleted" })
    expect(graph.tree_root_ids).toEqual(["gone"])
    expect(graph.nodes.size).toBe(3)
  })

  it("gives a placeholder its oldest child's sort key", () => {
    const graph = build_lineage_graph([
      make_dated_config("root", 4),
      make_dated_config("root_child", 7, ["root"]),
      make_dated_config("late", 5, ["gone"]),
      make_dated_config("early", 3, ["gone"]),
    ])
    expect(node(graph, "gone").sort_key).toBe(created_at_for(3))
    expect(node(graph, "gone").child_ids).toEqual(["early", "late"])
    expect(graph.tree_root_ids).toEqual(["gone", "root"])
  })

  it("drops self-references, repeats, null and empty ids", () => {
    const graph = build_lineage_graph([
      make_dated_config("a", 0),
      make_dated_config("b", 1, [null, "", "b", "a", "a", null]),
    ])
    expect(node(graph, "b").parent_ids).toEqual(["a"])
    expect(graph.edges).toHaveLength(1)
  })

  it("skips configs without an id, and keeps the first of a duplicate id", () => {
    const graph = build_lineage_graph([
      make_agent_config({ id: null }),
      make_agent_config({ id: "" }),
      make_agent_config({ id: "a", name: "First" }),
      make_agent_config({ id: "a", name: "Second" }),
    ])
    expect([...graph.nodes.keys()]).toEqual(["a"])
    expect(node(graph, "a").config?.name).toBe("First")
  })

  it("drops the newer node's edge in a two-node cycle", () => {
    const graph = build_lineage_graph([
      make_dated_config("older", 0, ["newer"]),
      make_dated_config("newer", 1, ["older"]),
    ])
    expect(node(graph, "newer").parent_ids).toEqual([])
    expect(node(graph, "older").parent_ids).toEqual(["newer"])
    expect(graph.edges.map((e) => e.id)).toEqual(["newer->older"])
    expect(node(graph, "newer").status).toEqual({ type: "starting_point" })
    expect(node(graph, "older").row).toBe(1)
  })

  it("breaks a three-node cycle and still connects every node", () => {
    const graph = build_lineage_graph([
      make_dated_config("a", 0, ["c"]),
      make_dated_config("b", 1, ["a"]),
      make_dated_config("c", 2, ["b"]),
    ])
    expect(graph.edges).toHaveLength(2)
    expect(graph.tree_root_ids).toHaveLength(1)
    const rows = [...graph.nodes.values()].map((n) => n.row).sort()
    expect(rows).toEqual([0, 1, 2])
  })

  it("puts each node on its longest path from a root, through merges", () => {
    const graph = build_lineage_graph([
      make_dated_config("a", 0),
      make_dated_config("b", 1, ["a"]),
      make_dated_config("c", 2, ["b"]),
      make_dated_config("d", 3, ["a", "c"]),
    ])
    expect(node(graph, "a").row).toBe(0)
    expect(node(graph, "c").row).toBe(2)
    expect(node(graph, "d").row).toBe(3)
  })

  it("assigns every status", () => {
    const graph = build_lineage_graph([
      make_dated_config("root", 0),
      make_dated_config("changed", 1, ["root"], {
        prompt_id: "other_prompt",
        model_name: "gpt_5_mini",
      }),
      make_dated_config("copy", 2, ["root"]),
      make_dated_config("orphan", 3, ["gone"]),
      make_dated_config("alone", 4),
    ])
    const statuses: Record<string, LineageStatus> = Object.fromEntries(
      [...graph.nodes.values()].map((n) => [n.id, n.status]),
    )
    expect(statuses).toEqual({
      root: { type: "starting_point" },
      changed: { type: "changed", kinds: ["prompt", "model"] },
      copy: { type: "copy" },
      orphan: { type: "parent_deleted" },
      alone: { type: "no_parent" },
      gone: { type: "deleted" },
    })
  })

  it("orders roots, the grid and child lists by sort key, then id", () => {
    const graph = build_lineage_graph([
      make_dated_config("grid_b", 5),
      make_dated_config("grid_a", 5),
      make_dated_config("grid_c", 1),
      make_dated_config("root_late", 3),
      make_dated_config("root_early", 2),
      make_dated_config("child_2", 9, ["root_late"]),
      make_dated_config("child_1", 8, ["root_late"]),
      make_dated_config("child_0", 8, ["root_early"]),
    ])
    expect(graph.no_parent_ids).toEqual(["grid_c", "grid_a", "grid_b"])
    expect(graph.tree_root_ids).toEqual(["root_early", "root_late"])
    expect(node(graph, "root_late").child_ids).toEqual(["child_1", "child_2"])
  })

  it("treats a config without created_at as the oldest", () => {
    const undated = make_agent_config({ id: "undated", created_at: undefined })
    const graph = build_lineage_graph([make_dated_config("dated", 0), undated])
    expect(node(graph, "undated").sort_key).toBe("")
    expect(graph.no_parent_ids).toEqual(["undated", "dated"])
  })

  it("builds a 1,000-node chain without overflowing the stack", () => {
    const graph = build_lineage_graph(make_chain(1000))
    expect(graph.nodes.size).toBe(1000)
    expect(graph.edges).toHaveLength(999)
    expect(node(graph, "rc_999").row).toBe(999)
  })

  it("returns an empty graph for no configs", () => {
    const graph = build_lineage_graph([])
    expect(graph.nodes.size).toBe(0)
    expect(graph.edges).toEqual([])
    expect(graph.tree_root_ids).toEqual([])
    expect(graph.no_parent_ids).toEqual([])
  })
})

describe("ancestor_edge_ids", () => {
  const graph = build_lineage_graph([
    make_dated_config("a", 0),
    make_dated_config("b", 1),
    make_dated_config("c", 2, ["a"]),
    make_dated_config("d", 3, ["c", "b"]),
    make_dated_config("e", 4, ["a"]),
  ])

  it("collects every edge above the node, extra parents included", () => {
    expect(ancestor_edge_ids(graph, "d")).toEqual(
      new Set(["c->d", "b->d", "a->c"]),
    )
  })

  it("is empty for a root and for an unknown id", () => {
    expect(ancestor_edge_ids(graph, "a").size).toBe(0)
    expect(ancestor_edge_ids(graph, "unknown").size).toBe(0)
  })
})

describe("node_matches_filters", () => {
  const changed: LineageStatus = { type: "changed", kinds: ["prompt", "model"] }
  const filters = (...keys: FilterKey[]) => new Set<FilterKey>(keys)

  it("matches everything when no filter is on", () => {
    expect(node_matches_filters(changed, filters())).toBe(true)
    expect(node_matches_filters({ type: "deleted" }, filters())).toBe(true)
  })

  it("matches a changed node on any of its kinds", () => {
    expect(node_matches_filters(changed, filters("model"))).toBe(true)
    expect(node_matches_filters(changed, filters("tools", "prompt"))).toBe(true)
    expect(node_matches_filters(changed, filters("tools", "copy"))).toBe(false)
  })

  it("matches a copy only on the copy key", () => {
    expect(node_matches_filters({ type: "copy" }, filters("copy"))).toBe(true)
    expect(node_matches_filters({ type: "copy" }, filters("prompt"))).toBe(
      false,
    )
  })

  it("never matches other statuses", () => {
    const all = filters(
      "prompt",
      "tools",
      "skills",
      "model",
      "settings",
      "copy",
    )
    for (const type of [
      "starting_point",
      "parent_deleted",
      "no_parent",
      "deleted",
    ] as const) {
      expect(node_matches_filters({ type }, all)).toBe(false)
    }
  })
})

describe("summarize_lineage", () => {
  it("counts run configs, models and overlapping change kinds", () => {
    const graph = build_lineage_graph([
      make_dated_config("root", 0),
      make_dated_config("prompt_and_model", 1, ["root"], {
        prompt_id: "other_prompt",
        model_name: "gpt_5_mini",
      }),
      make_dated_config("prompt_and_tools", 2, ["root"], {
        prompt_id: "other_prompt",
        tools_config: { tools: ["kiln_tool::add_numbers"] },
      }),
      make_dated_config("copy", 3, ["root"]),
      make_dated_config("other_provider", 4, ["gone"], {
        model_provider_name: "openrouter",
      }),
      make_mcp_config({ id: "mcp", created_at: created_at_for(5) }),
    ])
    expect(summarize_lineage(graph)).toEqual({
      run_config_count: 6,
      model_count: 3,
      filter_counts: {
        prompt: 2,
        tools: 1,
        skills: 0,
        model: 1,
        settings: 0,
        copy: 1,
      },
    })
  })

  it("is all zeros for an empty graph", () => {
    expect(summarize_lineage(build_lineage_graph([]))).toEqual({
      run_config_count: 0,
      model_count: 0,
      filter_counts: {
        prompt: 0,
        tools: 0,
        skills: 0,
        model: 0,
        settings: 0,
        copy: 0,
      },
    })
  })
})
