import { describe, it, expect } from "vitest"
import type { ToolApiDescription, ToolSetApiDescription } from "$lib/types"
import {
  duplicate_tool_names,
  get_tool_names_from_ids,
  is_skill_tool_id,
  kiln_task_tool_server_id,
  split_tool_and_skill_ids,
  tool_display_name,
  tool_qualifier_id,
} from "./tools_store"

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

  describe("kiln task tool disambiguation", () => {
    const summarize_tool: ToolApiDescription = {
      id: "kiln_task::111",
      name: "summarize",
      description: "Summarize text",
    }
    const summarize_tool_clone: ToolApiDescription = {
      id: "kiln_task::222",
      name: "summarize",
      description: "Summarize text",
    }
    const kiln_task_set = (
      tools: ToolApiDescription[],
    ): ToolSetApiDescription => ({
      type: "kiln_task",
      set_name: "Kiln Tasks as Tools",
      tools,
    })
    const mcp_set = (tools: ToolApiDescription[]): ToolSetApiDescription => ({
      type: "mcp",
      set_name: "MCP Server: demo",
      tools,
    })

    describe("kiln_task_tool_server_id", () => {
      it("returns the tool server ID of a Kiln task tool", () => {
        expect(kiln_task_tool_server_id("kiln_task::121377416728")).toBe(
          "121377416728",
        )
      })

      it("returns null for other tool types", () => {
        expect(kiln_task_tool_server_id("mcp::local::456::read")).toBe(null)
        expect(kiln_task_tool_server_id("kiln_tool::add_numbers")).toBe(null)
      })

      it("returns null when the ID carries no server ID", () => {
        expect(kiln_task_tool_server_id("kiln_task::")).toBe(null)
      })
    })

    describe("duplicate_tool_names", () => {
      it("finds names shared by tools in the same set", () => {
        expect(
          duplicate_tool_names([
            kiln_task_set([summarize_tool, summarize_tool_clone]),
          ]),
        ).toEqual(new Set(["summarize"]))
      })

      it("finds names shared across different tool sets", () => {
        expect(
          duplicate_tool_names([
            kiln_task_set([summarize_tool]),
            mcp_set([
              {
                id: "mcp::local::1::summarize",
                name: "summarize",
                description: null,
              },
            ]),
          ]),
        ).toEqual(new Set(["summarize"]))
      })

      it("returns an empty set when every name is unique", () => {
        expect(
          duplicate_tool_names([
            kiln_task_set([summarize_tool]),
            mcp_set([
              { id: "mcp::local::1::read", name: "read", description: null },
            ]),
          ]),
        ).toEqual(new Set())
      })

      it("handles a project with no tool sets", () => {
        expect(duplicate_tool_names([])).toEqual(new Set())
      })
    })

    describe("tool_display_name", () => {
      it("qualifies an ambiguous Kiln task tool with its tool server ID", () => {
        expect(tool_display_name(summarize_tool, new Set(["summarize"]))).toBe(
          "summarize (111)",
        )
      })

      it("leaves a unique name alone", () => {
        expect(tool_display_name(summarize_tool, new Set())).toBe("summarize")
      })

      it("qualifies ambiguous code and search tools with their embedded id", () => {
        expect(
          tool_display_name(
            {
              id: "kiln_tool::code::333",
              name: "Summarize",
              description: null,
              function_name: "summarize",
            },
            new Set(["Summarize"]),
          ),
        ).toBe("Summarize (333)")
        expect(
          tool_display_name(
            {
              id: "kiln_tool::rag::444",
              name: "Docs Search",
              description: null,
              function_name: "docs_search",
            },
            new Set(["Docs Search"]),
          ),
        ).toBe("Docs Search (444)")
      })

      it("leaves MCP tools alone, since their group already names them", () => {
        expect(
          tool_display_name(
            {
              id: "mcp::local::1::summarize",
              name: "summarize",
              description: null,
            },
            new Set(["summarize"]),
          ),
        ).toBe("summarize")
      })
    })

    describe("tool_qualifier_id", () => {
      it("returns the embedded id for kiln task, code, search, and skill tools", () => {
        expect(tool_qualifier_id("kiln_task::111")).toBe("111")
        expect(tool_qualifier_id("kiln_tool::code::333")).toBe("333")
        expect(tool_qualifier_id("kiln_tool::rag::444")).toBe("444")
        expect(tool_qualifier_id("kiln_tool::skill::555")).toBe("555")
      })

      it("returns null for other tool types and empty ids", () => {
        expect(tool_qualifier_id("mcp::local::456::read")).toBe(null)
        expect(tool_qualifier_id("kiln_tool::add_numbers")).toBe(null)
        expect(tool_qualifier_id("kiln_tool::code::")).toBe(null)
      })
    })

    describe("get_tool_names_from_ids", () => {
      it("qualifies only the duplicated names", () => {
        const project_tools = [
          kiln_task_set([summarize_tool, summarize_tool_clone]),
          mcp_set([
            { id: "mcp::local::1::read", name: "read", description: null },
          ]),
        ]
        expect(
          get_tool_names_from_ids(
            ["kiln_task::111", "kiln_task::222", "mcp::local::1::read"],
            project_tools,
          ),
        ).toEqual(["summarize (111)", "summarize (222)", "read"])
      })

      it("falls back to the ID when a tool is not in the project", () => {
        expect(
          get_tool_names_from_ids(
            ["kiln_task::999"],
            [kiln_task_set([summarize_tool])],
          ),
        ).toEqual(["kiln_task::999"])
      })
    })
  })
})
