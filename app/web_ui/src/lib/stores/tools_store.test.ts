import { describe, it, expect } from "vitest"
import { is_skill_tool_id, split_tool_and_skill_ids } from "./tools_store"

describe("tools_store", () => {
  describe("is_skill_tool_id", () => {
    it("returns true for skill tool IDs", () => {
      expect(is_skill_tool_id("kiln_tool::skill::123")).toBe(true)
    })

    it("returns false for non-skill tool IDs", () => {
      expect(is_skill_tool_id("mcp::local::456::read")).toBe(false)
    })
  })

  describe("split_tool_and_skill_ids", () => {
    it("separates skill IDs from tool IDs", () => {
      const result = split_tool_and_skill_ids([
        "mcp::local::1::read",
        "kiln_tool::skill::100",
        "mcp::local::2::write",
        "kiln_tool::skill::200",
      ])
      expect(result.tool_ids).toEqual([
        "mcp::local::1::read",
        "mcp::local::2::write",
      ])
      expect(result.skill_ids).toEqual([
        "kiln_tool::skill::100",
        "kiln_tool::skill::200",
      ])
    })

    it("returns empty arrays when given empty input", () => {
      const result = split_tool_and_skill_ids([])
      expect(result.tool_ids).toEqual([])
      expect(result.skill_ids).toEqual([])
    })
  })
})
