import { describe, it, expect } from "vitest"
import type { TaskRunConfig } from "$lib/types"
import {
  FALLBACK_SERIES_COLOR,
  SERIES_PALETTE,
  series_color,
  series_color_map,
  series_label,
  series_subtext,
} from "./series_identity"

function agent_config(overrides: Partial<TaskRunConfig> = {}): TaskRunConfig {
  return {
    v: 1,
    id: "rc-agent",
    created_at: "2026-02-01T00:00:00.000Z",
    created_by: "test",
    name: "Luna",
    description: null,
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
    prompt: null,
    model_type: "task_run_config",
    starred: false,
    ...overrides,
  } as TaskRunConfig
}

function mcp_config(overrides: Partial<TaskRunConfig> = {}): TaskRunConfig {
  return {
    v: 1,
    id: "rc-mcp",
    created_at: "2026-02-01T00:00:00.000Z",
    created_by: "test",
    // Unnamed, so the tool name is what it has to fall back to
    name: undefined,
    description: null,
    run_config_properties: {
      type: "mcp",
      tool_reference: {
        tool_id: "mcp::local::server::tool",
        tool_name: "Demo Tool",
        input_schema: { type: "object", properties: {} },
        output_schema: null,
      },
    },
    prompt: null,
    model_type: "task_run_config",
    starred: false,
    ...overrides,
  } as TaskRunConfig
}

describe("series_label", () => {
  it("prefers the config's own name", () => {
    expect(series_label(agent_config(), null)).toBe("Luna")
  })

  it("falls back to the MCP tool name for an unnamed MCP config", () => {
    expect(series_label(mcp_config(), null)).toBe("Demo Tool")
  })

  it("falls back to the model for an unnamed agent config", () => {
    const label = series_label(agent_config({ name: undefined }), null)
    expect(label).toContain("gpt-4")
    expect(label).not.toBe("Unknown")
  })

  it("names an unnamed MCP config with no tool name at all", () => {
    const config = mcp_config()
    // A tool reference that lost its name is the one case with nothing to
    // fall back to
    ;(
      config.run_config_properties as unknown as {
        tool_reference: { tool_name: string | null }
      }
    ).tool_reference.tool_name = null
    expect(series_label(config, null)).toBe("MCP Tool")
  })
})

describe("series_subtext", () => {
  it("names the tool for an MCP config, and nothing else", () => {
    expect(series_subtext(mcp_config(), null, null)).toEqual([
      "Tool: Demo Tool",
    ])
  })

  it("leads with the model for an agent config", () => {
    const lines = series_subtext(agent_config(), null, null)
    expect(lines[0]).toContain("Model:")
    expect(lines[0]).toContain("gpt-4")
  })

  it("adds the input transform only when there is one", () => {
    const plain = series_subtext(agent_config(), null, null)
    const transformed = series_subtext(
      agent_config({
        run_config_properties: {
          ...agent_config().run_config_properties,
          input_transform: { type: "jinja", template: "Hi {{ input }}" },
        },
      } as Partial<TaskRunConfig>),
      null,
      null,
    )
    expect(plain.some((line) => line.startsWith("Input Transform:"))).toBe(
      false,
    )
    expect(
      transformed.some((line) => line.startsWith("Input Transform:")),
    ).toBe(true)
  })
})

describe("series_color", () => {
  it("walks the palette in order", () => {
    expect(series_color(0)).toBe(SERIES_PALETTE[0])
    expect(series_color(2)).toBe(SERIES_PALETTE[2])
  })

  it("cycles past the end, as echarts does", () => {
    expect(series_color(SERIES_PALETTE.length)).toBe(SERIES_PALETTE[0])
    expect(series_color(SERIES_PALETTE.length + 3)).toBe(SERIES_PALETTE[3])
  })

  it("survives a negative or non-finite index", () => {
    expect(series_color(-1)).toBe(SERIES_PALETTE[SERIES_PALETTE.length - 1])
    expect(series_color(Number.NaN)).toBe(FALLBACK_SERIES_COLOR)
  })
})

describe("series_color_map", () => {
  it("assigns by position in the pinned list", () => {
    expect(series_color_map(["a", "b", "c"])).toEqual({
      a: SERIES_PALETTE[0],
      b: SERIES_PALETTE[1],
      c: SERIES_PALETTE[2],
    })
  })

  it("keeps a config's colour when another is pinned after it", () => {
    const before = series_color_map(["a", "b"])
    const after = series_color_map(["a", "b", "c"])
    expect(after.a).toBe(before.a)
    expect(after.b).toBe(before.b)
  })

  it("restains the tail when a config is unpinned from the middle", () => {
    // Honest about the one case that does move: pinned position IS the key, so
    // removing a config shifts everything below it - the same thing the pin
    // list itself does, and visible to the reader in the legend.
    const before = series_color_map(["a", "b", "c"])
    const after = series_color_map(["a", "c"])
    expect(after.a).toBe(before.a)
    expect(after.c).not.toBe(before.c)
  })

  it("gives a repeated id one colour, its first", () => {
    expect(series_color_map(["a", "b", "a"])).toEqual({
      a: SERIES_PALETTE[0],
      b: SERIES_PALETTE[1],
    })
  })

  it("is empty for an empty pin list", () => {
    expect(series_color_map([])).toEqual({})
  })
})
