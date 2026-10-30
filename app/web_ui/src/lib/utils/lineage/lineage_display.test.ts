import { describe, expect, it } from "vitest"
import type {
  KilnAgentRunConfigProperties,
  PromptResponse,
  ProviderModels,
  TaskRunConfig,
  ToolSetApiDescription,
} from "$lib/types"
import {
  build_lineage_graph,
  type LineageNode,
  type LineageStatus,
} from "./lineage_graph"
import {
  change_rows,
  children_text,
  node_model_text,
  node_title,
  status_text,
  type DisplayContext,
} from "./lineage_display"
import {
  make_agent_config,
  make_mcp_config,
} from "./__tests__/lineage_fixtures"

const MODEL_INFO: ProviderModels = {
  models: {
    gpt_5: { id: "gpt_5", name: "GPT 5" },
    gpt_5_mini: { id: "gpt_5_mini", name: "GPT 5 Mini" },
  },
}

const TASK_PROMPTS: PromptResponse = {
  generators: [],
  prompts: [
    { id: "p_old", name: "Old Prompt", prompt: "Be brief.", type: "saved" },
    { id: "p_new", name: "New Prompt", prompt: "Be kind.", type: "saved" },
  ],
}

const PROJECT_TOOLS: ToolSetApiDescription[] = [
  {
    type: "builtin",
    set_name: "Built-in",
    tools: [
      { id: "kiln_tool::add_numbers", name: "add_numbers", description: null },
      { id: "kiln_tool::web_search", name: "web_search", description: null },
    ],
  },
  {
    type: "skill",
    set_name: "Skills",
    tools: [
      { id: "kiln_tool::skill::tone", name: "Tone Guide", description: null },
    ],
  },
]

const LOADED: DisplayContext = {
  model_info: MODEL_INFO,
  task_prompts: TASK_PROMPTS,
  project_tools: PROJECT_TOOLS,
}

const UNLOADED: DisplayContext = {
  model_info: null,
  task_prompts: null,
  project_tools: null,
}

function agent(
  properties: Partial<KilnAgentRunConfigProperties> = {},
): TaskRunConfig {
  return make_agent_config({ name: "Gusty Forest", properties })
}

function graph_node(configs: TaskRunConfig[], id: string): LineageNode {
  const node = build_lineage_graph(configs).nodes.get(id)
  if (!node) {
    throw new Error(`no node ${id}`)
  }
  return node
}

describe("node_title", () => {
  it("is the run config name, or the placeholder text", () => {
    const configs = [
      make_agent_config({
        id: "a",
        name: "Calm River",
        derived_from: ["gone"],
      }),
    ]
    expect(node_title(graph_node(configs, "a"))).toBe("Calm River")
    expect(node_title(graph_node(configs, "gone"))).toBe("Deleted run config")
  })
})

describe("status_text", () => {
  const cases: [LineageStatus, string][] = [
    [{ type: "starting_point" }, "Starting point"],
    [{ type: "changed", kinds: ["prompt", "model"] }, "Prompt, Model"],
    [{ type: "copy" }, "Copy or re-run, no changes"],
    [{ type: "parent_deleted" }, "Parent deleted"],
    [{ type: "no_parent" }, "No recorded parent"],
    [{ type: "deleted" }, "This run config was deleted"],
  ]

  it.each(cases)("describes %j", (status, text) => {
    expect(status_text(status)).toBe(text)
  })
})

describe("node_model_text", () => {
  it("shows the model with its provider", () => {
    const node = graph_node([make_agent_config({ id: "a" })], "a")
    expect(node_model_text(node, MODEL_INFO)).toBe("GPT 5 (OpenAI)")
  })

  it("shows the tool for an MCP run config", () => {
    const node = graph_node([make_mcp_config({ id: "m" })], "m")
    expect(node_model_text(node, MODEL_INFO)).toBe("MCP: Run Task")
  })

  it("is empty for a placeholder", () => {
    const configs = [make_agent_config({ id: "a", derived_from: ["gone"] })]
    expect(node_model_text(graph_node(configs, "gone"), MODEL_INFO)).toBe("")
  })
})

describe("children_text", () => {
  it("counts children", () => {
    expect(children_text(0)).toBe("No children")
    expect(children_text(1)).toBe("1 child")
    expect(children_text(4)).toBe("4 children")
  })
})

describe("change_rows", () => {
  it("shows the new and old prompt names", () => {
    const rows = change_rows(
      agent({ prompt_id: "p_old" }),
      agent({ prompt_id: "p_new" }),
      ["prompt"],
      LOADED,
    )
    expect(rows).toEqual([
      {
        kind: "prompt",
        value: "New Prompt",
        previous: "Old Prompt",
        provider_id: null,
      },
    ])
  })

  it("falls back to prompt ids before prompts load", () => {
    const [row] = change_rows(
      agent({ prompt_id: "p_old" }),
      agent({ prompt_id: "p_new" }),
      ["prompt"],
      UNLOADED,
    )
    expect([row.value, row.previous]).toEqual(["p_new", "p_old"])
  })

  it("lists tools and skills by name", () => {
    const rows = change_rows(
      agent({ tools_config: { tools: ["kiln_tool::add_numbers"] } }),
      agent({
        tools_config: {
          tools: [
            "kiln_tool::add_numbers",
            "kiln_tool::web_search",
            "kiln_tool::skill::tone",
          ],
        },
      }),
      ["tools", "skills"],
      LOADED,
    )
    expect(rows.map((r) => [r.kind, r.value, r.previous])).toEqual([
      ["tools", "add_numbers, web_search", "add_numbers"],
      ["skills", "Tone Guide", "None"],
    ])
  })

  it("falls back to tool ids before tools load", () => {
    const [row] = change_rows(
      agent(),
      agent({ tools_config: { tools: ["kiln_tool::web_search"] } }),
      ["tools"],
      UNLOADED,
    )
    expect([row.value, row.previous]).toEqual(["kiln_tool::web_search", "None"])
  })

  it("shows the model with its provider, and the child's provider id", () => {
    const [row] = change_rows(
      agent(),
      agent({ model_name: "gpt_5_mini" }),
      ["model"],
      LOADED,
    )
    expect(row).toEqual({
      kind: "model",
      value: "GPT 5 Mini (OpenAI)",
      previous: "GPT 5 (OpenAI)",
      provider_id: "openai",
    })
  })

  it("lists only the settings that changed", () => {
    const [row] = change_rows(
      agent({ temperature: 1, thinking_level: null }),
      agent({ temperature: 0.7, thinking_level: "high" }),
      ["settings"],
      LOADED,
    )
    expect(row).toEqual({
      kind: "settings",
      value: "Temperature 0.7 · Thinking High",
      previous: "Temperature 1 · Thinking Default",
      provider_id: null,
    })
  })

  it("names output modes and input transforms", () => {
    const [row] = change_rows(
      agent({ top_p: 1, structured_output_mode: "json_schema" }),
      agent({
        top_p: 0.5,
        structured_output_mode: "json_mode",
        input_transform: { type: "jinja", template: "{{ input }}" },
      }),
      ["settings"],
      LOADED,
    )
    expect(row.value).toBe(
      "Top P 0.5 · Output JSON Mode · Input transform Custom Template",
    )
    expect(row.previous).toBe(
      "Top P 1 · Output JSON Schema · Input transform None",
    )
  })

  it("shows the MCP tool as the model, and a dash for kinds it lacks", () => {
    const rows = change_rows(
      agent({ prompt_id: "p_new" }),
      make_mcp_config(),
      ["prompt", "tools", "model", "settings"],
      LOADED,
    )
    expect(rows).toEqual([
      { kind: "prompt", value: "—", previous: "New Prompt", provider_id: null },
      { kind: "tools", value: "—", previous: "None", provider_id: null },
      {
        kind: "model",
        value: "MCP: Run Task",
        previous: "GPT 5 (OpenAI)",
        provider_id: null,
      },
      { kind: "settings", value: "—", previous: "—", provider_id: null },
    ])
  })
})
