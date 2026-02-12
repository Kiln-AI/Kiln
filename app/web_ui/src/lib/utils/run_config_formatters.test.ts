import { describe, it, expect } from "vitest"
import type { TaskRunConfig } from "$lib/types"
import {
  getDetailedModelName,
  getRunConfigUiProperties,
} from "./run_config_formatters"

describe("run_config_formatters (MCP)", () => {
  const mcp_config: TaskRunConfig = {
    v: 1,
    id: "rc1",
    created_at: "2026-02-01T00:00:00.000Z",
    created_by: "test",
    name: "MCP Config",
    description: null,
    run_config_properties: {
      kind: "mcp",
      mcp_tool: {
        tool_id: "mcp::local::server::tool",
        tool_name: "Demo Tool",
        input_schema: { type: "object", properties: {} },
        output_schema: null,
      },
      model_name: "mcp_tool",
      model_provider_name: "mcp_provider",
      prompt_id: "simple_prompt_builder",
      top_p: 1,
      temperature: 1,
      structured_output_mode: "default",
      tools_config: null,
    },
    prompt: null,
    model_type: "task_run_config",
  }

  it("getDetailedModelName should return MCP tool name", () => {
    expect(getDetailedModelName(mcp_config, null)).toBe("Demo Tool")
  })

  it("getRunConfigUiProperties should return MCP-specific fields", () => {
    const props = getRunConfigUiProperties(
      "project1",
      "task1",
      mcp_config,
      null,
      null,
      null,
    )
    const propNames = props.map((p) => p.name)
    expect(propNames).toContain("Type")
    expect(propNames).toContain("Tool Name")
    expect(propNames).toContain("Tool ID")
    expect(propNames).not.toContain("Model")
    expect(propNames).not.toContain("Prompt")
    const typeProp = props.find((p) => p.name === "Type")
    expect(typeProp?.value).toBe("MCP Tool (No Agent)")
  })
})
