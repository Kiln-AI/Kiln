import { describe, it, expect } from "vitest"
import type { ProviderModels, TaskRunConfig } from "$lib/types"
import {
  FALLBACK_SERIES_COLOR,
  SERIES_PALETTE,
  series_color,
  series_color_map,
  series_display_map,
  series_label,
  series_model_label,
  series_primary_label,
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

// The model catalog the page has loaded. Names resolve through it; a config on
// a model that is not in it is the "model_info missing" case.
const CATALOG: ProviderModels = {
  models: {
    "gpt-4": { name: "GPT-4", id: "gpt-4", supports_function_calling: true },
    "gpt-5-4-mini": {
      name: "GPT-5.4-mini",
      id: "gpt-5-4-mini",
      supports_function_calling: true,
    },
    luna: { name: "GPT-5.6 Luna", id: "luna", supports_function_calling: true },
  },
} as ProviderModels

function on_model(
  model: string,
  name: string | undefined,
  id: string,
): TaskRunConfig {
  return agent_config({
    id,
    name,
    run_config_properties: {
      ...agent_config().run_config_properties,
      model_name: model,
    },
  } as Partial<TaskRunConfig>)
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

describe("series_model_label", () => {
  it("is the model's display name, without the provider", () => {
    expect(series_model_label(agent_config(), CATALOG)).toBe("GPT-4")
  })

  it("is null for an MCP config, which has no model at all", () => {
    expect(series_model_label(mcp_config(), CATALOG)).toBeNull()
  })

  it("is null when the catalog cannot resolve the model", () => {
    expect(series_model_label(agent_config(), null)).toBeNull()
    expect(series_model_label(on_model("who-dis", "X", "rc-x"), CATALOG)).toBe(
      null,
    )
  })
})

describe("series_primary_label", () => {
  it("is the model, not the config's own name", () => {
    expect(series_primary_label(agent_config(), CATALOG)).toBe("GPT-4")
  })

  it("falls back to the config's name when there is no model to name", () => {
    expect(series_primary_label(agent_config(), null)).toBe("Luna")
    expect(series_primary_label(mcp_config({ name: "My MCP" }), CATALOG)).toBe(
      "My MCP",
    )
  })

  it("falls back to the tool for an unnamed MCP config", () => {
    expect(series_primary_label(mcp_config(), CATALOG)).toBe("Demo Tool")
  })
})

describe("series_subtext", () => {
  it("names the tool for a named MCP config", () => {
    expect(series_subtext(mcp_config({ name: "My MCP" }), null, null)).toEqual([
      "Tool: Demo Tool",
    ])
  })

  it("does not repeat a tool name that is already the top line", () => {
    // Unnamed, so the top line has fallen back to the tool itself
    expect(series_subtext(mcp_config(), null, null)).toEqual([])
  })

  it("leads with the config's own name, under the model", () => {
    const lines = series_subtext(agent_config(), CATALOG, null)
    expect(lines[0]).toBe("Luna")
    expect(lines.some((line) => line.includes("GPT-4"))).toBe(false)
  })

  it("does not repeat a name the top line already fell back to", () => {
    // No catalog, so series_primary_label is the config's name
    const lines = series_subtext(agent_config(), null, null)
    expect(lines.some((line) => line === "Luna")).toBe(false)
  })

  it("puts the provider and the prompt on one detail line", () => {
    const lines = series_subtext(agent_config(), CATALOG, null)
    const detail = lines[lines.length - 1]
    expect(detail).toContain("OpenAI")
    expect(detail).toContain("Prompt:")
    expect(detail).toContain(" · ")
  })

  it("adds the input transform only when there is one", () => {
    const plain = series_subtext(agent_config(), CATALOG, null)
    const transformed = series_subtext(
      agent_config({
        run_config_properties: {
          ...agent_config().run_config_properties,
          input_transform: { type: "jinja", template: "Hi {{ input }}" },
        },
      } as Partial<TaskRunConfig>),
      CATALOG,
      null,
    )
    expect(plain.some((line) => line.includes("Input Transform:"))).toBe(false)
    expect(transformed.some((line) => line.includes("Input Transform:"))).toBe(
      true,
    )
  })
})

describe("series_display_map", () => {
  it("is the model alone when that model is pinned once", () => {
    const map = series_display_map(
      [on_model("luna", "Luna M1", "rc-1"), on_model("gpt-4", "Base", "rc-2")],
      CATALOG,
    )
    expect(map).toEqual({ "rc-1": "GPT-5.6 Luna", "rc-2": "GPT-4" })
  })

  it("appends the config name when a model is shared", () => {
    const map = series_display_map(
      [
        on_model("gpt-5-4-mini", "mini v5", "rc-1"),
        on_model("gpt-5-4-mini", "mini v6", "rc-2"),
        on_model("luna", "Luna M1", "rc-3"),
      ],
      CATALOG,
    )
    expect(map["rc-1"]).toBe("GPT-5.4-mini — mini v5")
    expect(map["rc-2"]).toBe("GPT-5.4-mini — mini v6")
    // Unshared, so it takes no suffix it does not need
    expect(map["rc-3"]).toBe("GPT-5.6 Luna")
  })

  it("keeps the bare model for an unnamed config with nothing to add", () => {
    const map = series_display_map(
      [
        on_model("gpt-5-4-mini", undefined, "rc-1"),
        on_model("gpt-5-4-mini", "mini v6", "rc-2"),
      ],
      CATALOG,
    )
    expect(map["rc-1"]).toBe("GPT-5.4-mini")
    expect(map["rc-2"]).toBe("GPT-5.4-mini — mini v6")
  })

  it("falls back to the config name when the model is unknown", () => {
    const map = series_display_map(
      [agent_config(), mcp_config({ name: "My MCP" })],
      null,
    )
    expect(map["rc-agent"]).toBe("Luna")
    expect(map["rc-mcp"]).toBe("My MCP")
  })

  it("does not depend on the order the configs arrive in", () => {
    const configs = [
      on_model("gpt-5-4-mini", "mini v5", "rc-1"),
      on_model("gpt-5-4-mini", "mini v6", "rc-2"),
      on_model("luna", "Luna M1", "rc-3"),
    ]
    expect(series_display_map([...configs].reverse(), CATALOG)).toEqual(
      series_display_map(configs, CATALOG),
    )
  })

  it("counts a repeated id once, and labels it once", () => {
    const config = on_model("gpt-5-4-mini", "mini v6", "rc-1")
    expect(series_display_map([config, config], CATALOG)).toEqual({
      // Counted twice, it would look shared with itself and take a suffix
      "rc-1": "GPT-5.4-mini",
    })
  })

  it("is empty for an empty pin list", () => {
    expect(series_display_map([], CATALOG)).toEqual({})
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
