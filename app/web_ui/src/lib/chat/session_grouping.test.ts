import { describe, it, expect } from "vitest"
import {
  nestSessionRows,
  splitSessionNodes,
  splitSessionRows,
  visibleSessionRows,
  type SessionListItem,
} from "./session_grouping"

function row(
  id: string,
  auto_active = false,
  auto_run_id: string | null = null,
): SessionListItem {
  return {
    id,
    title: id,
    updated_at: null,
    auto_active,
    auto_run_id,
    is_subagent: false,
  }
}

function parentRow(
  id: string,
  root_id: string,
  auto_active = false,
): SessionListItem {
  return { ...row(id, auto_active), root_id }
}

function childRow(
  id: string,
  parent_root_id: string | null,
  subagent_status: string | null = "completed",
): SessionListItem {
  return {
    ...row(id),
    is_subagent: true,
    root_id: `root-${id}`,
    parent_root_id,
    subagent_id: `sa_${id}`,
    subagent_status,
  }
}

describe("splitSessionRows", () => {
  it("puts auto_active rows in the active group and the rest in recent", () => {
    const rows = [
      row("a"),
      row("b", true, "ar_b"),
      row("c"),
      row("d", true, "ar_d"),
    ]
    const { active, recent } = splitSessionRows(rows)
    expect(active.map((r) => r.id)).toEqual(["b", "d"])
    expect(recent.map((r) => r.id)).toEqual(["a", "c"])
  })

  it("preserves the server ordering within each group", () => {
    const rows = [row("z", true), row("y"), row("x", true), row("w")]
    const { active, recent } = splitSessionRows(rows)
    expect(active.map((r) => r.id)).toEqual(["z", "x"])
    expect(recent.map((r) => r.id)).toEqual(["y", "w"])
  })

  it("returns an empty active group when nothing is running", () => {
    const { active, recent } = splitSessionRows([row("a"), row("b")])
    expect(active).toEqual([])
    expect(recent.map((r) => r.id)).toEqual(["a", "b"])
  })
})

describe("nestSessionRows", () => {
  it("nests sub-agent rows under their parent by parent_root_id → root_id", () => {
    const nodes = nestSessionRows([
      parentRow("p1", "root-p1"),
      childRow("c1", "root-p1"),
      parentRow("p2", "root-p2"),
      childRow("c2", "root-p2"),
      childRow("c3", "root-p1"),
    ])
    expect(nodes.map((n) => n.row.id)).toEqual(["p1", "p2"])
    expect(nodes[0].children.map((r) => r.id)).toEqual(["c1", "c3"])
    expect(nodes[1].children.map((r) => r.id)).toEqual(["c2"])
  })

  it("renders a child without a visible parent as a normal top-level row", () => {
    const nodes = nestSessionRows([
      parentRow("p1", "root-p1"),
      childRow("orphan", "root-gone"),
      childRow("no-parent-id", null),
    ])
    expect(nodes.map((n) => n.row.id)).toEqual(["p1", "orphan", "no-parent-id"])
    expect(nodes.every((n) => n.children.length === 0)).toBe(true)
  })

  it("does not nest under another sub-agent's root_id", () => {
    // c2's parent_root_id points at c1 (itself a sub-agent): only non-subagent
    // rows are nesting parents, so c2 renders top-level.
    const c1 = childRow("c1", "root-p1")
    const nodes = nestSessionRows([
      parentRow("p1", "root-p1"),
      c1,
      childRow("c2", c1.root_id ?? null),
    ])
    expect(nodes.map((n) => n.row.id)).toEqual(["p1", "c2"])
    expect(nodes[0].children.map((r) => r.id)).toEqual(["c1"])
  })

  it("preserves server ordering for parents and rows without lineage", () => {
    const nodes = nestSessionRows([row("a"), row("b"), row("c")])
    expect(nodes.map((n) => n.row.id)).toEqual(["a", "b", "c"])
  })
})

describe("visibleSessionRows", () => {
  it("returns all rows unchanged when dev tools are enabled", () => {
    const rows = [
      parentRow("p1", "root-p1"),
      childRow("c1", "root-p1"),
      childRow("orphan", "root-gone"),
    ]
    expect(visibleSessionRows(rows, true)).toEqual(rows)
  })

  it("drops every sub-agent row when dev tools are disabled", () => {
    const rows = [
      parentRow("p1", "root-p1"),
      childRow("c1", "root-p1"),
      row("plain"),
      childRow("orphan", "root-gone"),
    ]
    expect(visibleSessionRows(rows, false).map((r) => r.id)).toEqual([
      "p1",
      "plain",
    ])
  })
})

describe("splitSessionNodes", () => {
  it("children follow their parent into the active group", () => {
    const nodes = nestSessionRows([
      parentRow("p1", "root-p1", true),
      childRow("c1", "root-p1"),
      parentRow("p2", "root-p2"),
    ])
    const { active, recent } = splitSessionNodes(nodes)
    expect(active.map((n) => n.row.id)).toEqual(["p1"])
    expect(active[0].children.map((r) => r.id)).toEqual(["c1"])
    expect(recent.map((n) => n.row.id)).toEqual(["p2"])
  })
})
