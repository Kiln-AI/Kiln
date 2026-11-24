import { describe, expect, it } from "vitest"
import type { TaskRunConfig } from "$lib/types"
import { pick_entry_run_config } from "./entry_run_config"

function rc(id: string, created_at: string): TaskRunConfig {
  return { id, name: `Config ${id}`, created_at } as TaskRunConfig
}

const OLD = rc("old", "2026-01-01T00:00:00Z")
const NEW = rc("new", "2026-06-01T00:00:00Z")
const MID = rc("mid", "2026-03-01T00:00:00Z")
const ALL = [OLD, NEW, MID]

describe("pick_entry_run_config", () => {
  it("takes the task default first", () => {
    expect(pick_entry_run_config(ALL, "mid")).toBe(MID)
  })

  it("takes the most recently created when there is no default", () => {
    expect(pick_entry_run_config(ALL, null)).toBe(NEW)
  })

  it("skips a default that no longer matches a saved config", () => {
    expect(pick_entry_run_config(ALL, "deleted")).toBe(NEW)
  })

  it("is null when the task has no saved configs", () => {
    expect(pick_entry_run_config([], "old")).toBeNull()
  })
})
