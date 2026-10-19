// Source assertions: the builder page is too large to mount (see
// generate_step_surface.test.ts), so these read its save calls directly.
import { describe, expect, it } from "vitest"
import * as fs from "fs"
import * as path from "path"

const page_source = fs.readFileSync(
  path.resolve(__dirname, "./+page.svelte"),
  "utf-8",
)

const SAVE_PATH =
  '"/api/projects/{project_id}/tasks/{task_id}/spec_with_copilot"'

function save_call_bodies(): string[] {
  return page_source
    .split(SAVE_PATH)
    .slice(1)
    .map((after) => {
      const end = after.indexOf("signal: new_copilot_abort_signal()")
      if (end < 0) {
        throw new Error("spec_with_copilot call has no abort signal anchor")
      }
      return after.slice(0, end).replace(/\s+/g, " ")
    })
}

describe("spec builder save provenance", () => {
  it("has a single-turn and a multi-turn save call", () => {
    expect(save_call_bodies()).toHaveLength(2)
  })

  it("stamps human origin with no parent on every save call", () => {
    for (const body of save_call_bodies()) {
      expect(body).toContain('provenance: { origin: "human" }')
      expect(body).not.toContain("derived_from_ids")
    }
  })
})
