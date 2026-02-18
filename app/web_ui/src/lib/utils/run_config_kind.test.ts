import { describe, it, expect } from "vitest"
import type { RunConfigProperties, TaskRunConfig } from "$lib/types"
import {
  is_mcp_run_config,
  is_mcp_run_config_properties,
} from "./run_config_kind"

describe("run_config_kind", () => {
  it("should detect MCP run config properties", () => {
    const props = {
      type: "mcp",
      tool_reference: {
        tool_id: "mcp::local::server::tool",
        tool_name: "Tool",
      },
    } as RunConfigProperties

    expect(is_mcp_run_config_properties(props)).toBe(true)
    expect(is_mcp_run_config_properties(null)).toBe(false)
    expect(is_mcp_run_config_properties(undefined)).toBe(false)
  })

  it("should detect MCP run config", () => {
    const config = {
      run_config_properties: { type: "mcp" },
    } as TaskRunConfig

    expect(is_mcp_run_config(config)).toBe(true)
    expect(is_mcp_run_config(null)).toBe(false)
    expect(is_mcp_run_config(undefined)).toBe(false)
  })
})
