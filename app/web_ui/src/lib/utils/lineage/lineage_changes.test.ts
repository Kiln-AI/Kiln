import { describe, expect, it } from "vitest"
import type { KilnAgentRunConfigProperties, TaskRunConfig } from "$lib/types"
import {
  CHANGE_KINDS,
  changed_setting_fields,
  detect_changes,
  type ChangeKind,
} from "./lineage_changes"
import {
  make_agent_config,
  make_mcp_config,
} from "./__tests__/lineage_fixtures"

const SKILL_A = "kiln_tool::skill::skill_a"
const SKILL_B = "kiln_tool::skill::skill_b"
const TOOL_A = "kiln_tool::add_numbers"
const TOOL_B = "mcp::remote::server_1::search"

function agent(
  properties: Partial<KilnAgentRunConfigProperties> = {},
): TaskRunConfig {
  return make_agent_config({ properties })
}

function agent_properties(
  properties: Partial<KilnAgentRunConfigProperties> = {},
): KilnAgentRunConfigProperties {
  const config = agent(properties)
  if (config.run_config_properties.type !== "kiln_agent") {
    throw new Error("expected an agent config")
  }
  return config.run_config_properties
}

describe("detect_changes", () => {
  it("returns no changes for identical configs", () => {
    expect(detect_changes(agent(), agent())).toEqual([])
  })

  const single_changes: [ChangeKind, Partial<KilnAgentRunConfigProperties>][] =
    [
      ["prompt", { prompt_id: "other_prompt" }],
      ["tools", { tools_config: { tools: [TOOL_A] } }],
      ["skills", { tools_config: { tools: [SKILL_A] } }],
      ["model", { model_name: "gpt_5_mini" }],
      ["model", { model_provider_name: "openrouter" }],
      ["settings", { temperature: 0.2 }],
      ["settings", { top_p: 0.9 }],
      ["settings", { thinking_level: "high" }],
      ["settings", { structured_output_mode: "json_mode" }],
      [
        "settings",
        { input_transform: { type: "jinja", template: "{{ input }}" } },
      ],
    ]

  it.each(single_changes)("detects a %s change alone", (kind, change) => {
    expect(detect_changes(agent(), agent(change))).toEqual([kind])
  })

  it("returns several kinds in CHANGE_KINDS order", () => {
    const child = agent({
      temperature: 0.1,
      model_name: "gpt_5_mini",
      tools_config: { tools: [TOOL_A, SKILL_A] },
      prompt_id: "other_prompt",
    })
    expect(detect_changes(agent(), child)).toEqual(CHANGE_KINDS)
  })

  it("ignores tool order", () => {
    const parent = agent({ tools_config: { tools: [TOOL_A, TOOL_B, SKILL_A] } })
    const child = agent({ tools_config: { tools: [SKILL_A, TOOL_B, TOOL_A] } })
    expect(detect_changes(parent, child)).toEqual([])
  })

  it("reports a skill-only change as skills, not tools", () => {
    const parent = agent({ tools_config: { tools: [TOOL_A, SKILL_A] } })
    const child = agent({ tools_config: { tools: [TOOL_A, SKILL_B] } })
    expect(detect_changes(parent, child)).toEqual(["skills"])
  })

  it("treats a missing tools config as no tools", () => {
    const parent = agent({ tools_config: null })
    const child = agent({ tools_config: { tools: [] } })
    expect(detect_changes(parent, child)).toEqual([])
  })

  it("compares MCP configs by tool id", () => {
    const parent = make_mcp_config()
    expect(detect_changes(parent, make_mcp_config())).toEqual([])
    expect(
      detect_changes(parent, make_mcp_config({ tool: { tool_name: "Other" } })),
    ).toEqual([])
    expect(
      detect_changes(
        parent,
        make_mcp_config({ tool: { tool_id: "mcp::local::server_2::run" } }),
      ),
    ).toEqual(["model"])
  })

  it("counts a change between agent and MCP as a model change", () => {
    expect(detect_changes(agent(), make_mcp_config())).toEqual(["model"])
    expect(detect_changes(make_mcp_config(), agent())).toEqual(["model"])
  })
})

describe("changed_setting_fields", () => {
  it("treats null and undefined thinking levels as equal", () => {
    expect(
      changed_setting_fields(
        agent_properties({ thinking_level: null }),
        agent_properties({ thinking_level: undefined }),
      ),
    ).toEqual([])
  })

  it("detects a thinking level set from null", () => {
    expect(
      changed_setting_fields(
        agent_properties({ thinking_level: null }),
        agent_properties({ thinking_level: "medium" }),
      ),
    ).toEqual(["thinking_level"])
  })

  it("compares input transforms by content", () => {
    const transform = { type: "jinja" as const, template: "Q: {{ input }}" }
    expect(
      changed_setting_fields(
        agent_properties({ input_transform: transform }),
        agent_properties({ input_transform: { ...transform } }),
      ),
    ).toEqual([])
    expect(
      changed_setting_fields(
        agent_properties({ input_transform: null }),
        agent_properties({ input_transform: transform }),
      ),
    ).toEqual(["input_transform"])
  })

  it("returns every changed field in order", () => {
    expect(
      changed_setting_fields(
        agent_properties(),
        agent_properties({
          input_transform: { type: "jinja", template: "{{ input }}" },
          structured_output_mode: "json_mode",
          thinking_level: "low",
          top_p: 0.5,
          temperature: 0,
        }),
      ),
    ).toEqual([
      "temperature",
      "top_p",
      "thinking_level",
      "structured_output_mode",
      "input_transform",
    ])
  })
})
