import { describe, it, expect } from "vitest"
import { splitSessionRows, type SessionListItem } from "./session_grouping"

function row(
  id: string,
  auto_active = false,
  auto_run_id: string | null = null,
): SessionListItem {
  return { id, title: id, updated_at: null, auto_active, auto_run_id }
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
