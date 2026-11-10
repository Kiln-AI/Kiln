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
  added_removed_text,
  change_rows,
  children_text,
  lineage_relatives,
  lineage_summary_text,
  node_model_text,
  node_title,
  origin_text,
  status_text,
  type DisplayContext,
} from "./lineage_display"
import {
  make_agent_config,
  make_dated_config,
  make_mcp_config,
} from "./__tests__/lineage_fixtures"

const MODEL_INFO: ProviderModels = {
  models: {
    gpt_5: { id: "gpt_5", name: "GPT 5" },
    gpt_5_mini: { id: "gpt_5_mini", name: "GPT 5 Mini" },
  },
}

const TASK_PROMPTS: PromptResponse = {
  generators: [
    {
      id: "simple_prompt_builder",
      name: "Basic (Zero Shot)",
      short_description: "",
      description: "",
      chain_of_thought: false,
    },
  ],
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
  project_id: "p1",
  task_id: "t1",
  model_info: MODEL_INFO,
  task_prompts: TASK_PROMPTS,
  project_tools: PROJECT_TOOLS,
}

const UNLOADED: DisplayContext = {
  project_id: "p1",
  task_id: "t1",
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
    expect(children_text(1)).toBe("1 child")
    expect(children_text(4)).toBe("4 children")
  })
})

describe("added_removed_text", () => {
  it("counts what was added and removed, leaving off a zero part", () => {
    expect(added_removed_text(2, 1)).toBe("2 added, 1 removed")
    expect(added_removed_text(2, 0)).toBe("2 added")
    expect(added_removed_text(0, 3)).toBe("3 removed")
  })
})

describe("change_rows", () => {
  it("shows the new and old prompt names, each linked to its page", () => {
    const rows = change_rows(
      agent({ prompt_id: "p_old" }),
      agent({ prompt_id: "p_new" }),
      ["prompt"],
      LOADED,
    )
    expect(rows).toEqual([
      {
        type: "value",
        kind: "prompt",
        value: { text: "New Prompt", link: "/prompts/p1/t1/saved/p_new" },
        previous: { text: "Old Prompt", link: "/prompts/p1/t1/saved/p_old" },
      },
    ])
  })

  it("doesn't link a generator prompt, which has no page", () => {
    const [row] = change_rows(
      agent({ prompt_id: "simple_prompt_builder" }),
      agent({ prompt_id: "p_new" }),
      ["prompt"],
      LOADED,
    )
    expect(row.type === "value" && row.previous).toEqual({
      text: "Basic (Zero Shot)",
      link: null,
    })
  })

  it("falls back to prompt ids before prompts load", () => {
    const [row] = change_rows(
      agent({ prompt_id: "p_old" }),
      agent({ prompt_id: "p_new" }),
      ["prompt"],
      UNLOADED,
    )
    expect(row.type === "value" && [row.value.text, row.previous.text]).toEqual(
      ["p_new", "p_old"],
    )
  })

  it("lists the tools and skills added and removed, by name with links", () => {
    const rows = change_rows(
      agent({
        tools_config: {
          tools: ["kiln_tool::add_numbers", "kiln_tool::skill::tone"],
        },
      }),
      agent({
        tools_config: {
          tools: ["kiln_tool::web_search", "kiln_tool::sql_query"],
        },
      }),
      ["tools", "skills"],
      LOADED,
    )
    expect(rows).toEqual([
      {
        type: "list",
        kind: "tools",
        added: [
          { text: "web_search", link: "/tools/p1" },
          { text: "kiln_tool::sql_query", link: "/tools/p1" },
        ],
        removed: [{ text: "add_numbers", link: "/tools/p1" }],
      },
      {
        type: "list",
        kind: "skills",
        added: [],
        removed: [{ text: "Tone Guide", link: "/skills/p1/tone" }],
      },
    ])
  })

  it("falls back to tool ids before tools load", () => {
    const [row] = change_rows(
      agent(),
      agent({ tools_config: { tools: ["kiln_tool::web_search"] } }),
      ["tools"],
      UNLOADED,
    )
    expect(row.type === "list" && row.added.map((tool) => tool.text)).toEqual([
      "kiln_tool::web_search",
    ])
  })

  it("shows the model with its provider, without a link", () => {
    const [row] = change_rows(
      agent(),
      agent({ model_name: "gpt_5_mini" }),
      ["model"],
      LOADED,
    )
    expect(row).toEqual({
      type: "value",
      kind: "model",
      value: { text: "GPT 5 Mini (OpenAI)", link: null },
      previous: { text: "GPT 5 (OpenAI)", link: null },
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
      type: "value",
      kind: "settings",
      value: { text: "Temperature 0.7 · Thinking High", link: null },
      previous: { text: "Temperature 1 · Thinking Default", link: null },
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
    expect(row.type === "value" && [row.value.text, row.previous.text]).toEqual(
      [
        "Top P 0.5 · Output JSON Mode · Input transform Custom Template",
        "Top P 1 · Output JSON Schema · Input transform None",
      ],
    )
  })

  it("shows the MCP tool as the model, and a dash or nothing for kinds it lacks", () => {
    const rows = change_rows(
      agent({ prompt_id: "p_new", tools_config: { tools: [] } }),
      make_mcp_config(),
      ["prompt", "tools", "model", "settings"],
      LOADED,
    )
    const none = { text: "—", link: null }
    expect(rows).toEqual([
      {
        type: "value",
        kind: "prompt",
        value: none,
        previous: { text: "New Prompt", link: "/prompts/p1/t1/saved/p_new" },
      },
      { type: "list", kind: "tools", added: [], removed: [] },
      {
        type: "value",
        kind: "model",
        value: { text: "MCP: Run Task", link: null },
        previous: { text: "GPT 5 (OpenAI)", link: null },
      },
      { type: "value", kind: "settings", value: none, previous: none },
    ])
  })
})

describe("lineage_summary_text and lineage_relatives", () => {
  const configs = [
    make_dated_config("root", 0),
    make_dated_config("b", 1, ["root"]),
    make_dated_config("c", 2, ["root"]),
    make_dated_config("merge", 3, ["b", "gone", "c"]),
    make_dated_config("orphan", 4, ["gone"]),
    make_dated_config("alone", 5),
  ]
  const graph = build_lineage_graph(configs)

  function node_of(id: string): LineageNode {
    const node = graph.nodes.get(id)
    if (!node) {
      throw new Error(`no node ${id}`)
    }
    return node
  }

  it("counts a starting point's children", () => {
    expect(lineage_summary_text(node_of("root"))).toBe(
      "Starting point · 2 children",
    )
  })

  it("counts the parents and children of a derived node", () => {
    expect(lineage_summary_text(node_of("b"))).toBe(
      "Derived from 1 parent · 1 child",
    )
  })

  it("leaves the children off when there are none", () => {
    expect(lineage_summary_text(node_of("merge"))).toBe(
      "Derived from 3 parents",
    )
    expect(lineage_summary_text(node_of("orphan"))).toBe(
      "Derived from 1 parent",
    )
    expect(lineage_summary_text(node_of("alone"))).toBe("No recorded parent")
  })

  it("describes the deleted placeholder with its children", () => {
    expect(lineage_summary_text(node_of("gone"))).toBe(
      "This run config was deleted · 2 children",
    )
  })

  it("lists the parents in recorded order and marks a deleted one", () => {
    expect(lineage_relatives(node_of("merge"), graph)).toEqual({
      parents: [
        { id: "b", text: "Name b", deleted: false },
        { id: "gone", text: "Deleted run config", deleted: true },
        { id: "c", text: "Name c", deleted: false },
      ],
      children: [],
    })
  })

  it("lists the children oldest first", () => {
    expect(lineage_relatives(node_of("root"), graph)).toEqual({
      parents: [],
      children: [
        { id: "b", text: "Name b", deleted: false },
        { id: "c", text: "Name c", deleted: false },
      ],
    })
  })
})

describe("origin_text", () => {
  it("names who created the run config", () => {
    expect(origin_text("agent")).toBe("Agent Created")
    expect(origin_text("human")).toBe("Human Created")
  })

  it("is null when the origin is unknown", () => {
    expect(origin_text(null)).toBeNull()
    expect(origin_text(undefined)).toBeNull()
    expect(origin_text("robot")).toBeNull()
  })
})
