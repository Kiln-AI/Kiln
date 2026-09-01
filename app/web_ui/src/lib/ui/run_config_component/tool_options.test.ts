import { describe, it, expect, vi } from "vitest"
import type { ToolSetApiDescription } from "$lib/types"
import {
  AGENT_TOOL_SET_ORDER,
  build_tool_option_groups,
  selectable_tool_sets,
} from "./tool_options"

const ai_models_set: ToolSetApiDescription = {
  type: "sandbox_code",
  set_name: "AI Models",
  tools: [
    {
      id: "kiln_tool::llm",
      name: "LLM",
      description: "Call a model",
      function_name: "llm",
    },
    {
      id: "kiln_tool::llm_judge",
      name: "LLM Judge",
      description: "Judge with the eval schema",
      function_name: "llm_judge",
    },
  ],
}

const mcp_set: ToolSetApiDescription = {
  type: "mcp",
  set_name: "MCP Server: demo",
  tools: [
    {
      id: "mcp::remote::demo::search_docs",
      name: "search_docs",
      description: "  Search the docs  ",
      function_name: "search_docs",
    },
  ],
}

const kiln_task_set: ToolSetApiDescription = {
  type: "kiln_task",
  set_name: "Kiln Tasks as Tools",
  tools: [
    {
      id: "kiln_task::abc",
      name: "Summarize",
      description: null,
      function_name: "summarize",
    },
  ],
}

// Real divergence case: the server sends the display name in `name` and the
// callable name in `function_name` for code (and search) tools.
const code_set: ToolSetApiDescription = {
  type: "code",
  set_name: "Code Tools",
  tools: [
    {
      id: "kiln_tool::code::333",
      name: "Summarizer",
      description: "Summarize the input",
      function_name: "summarize",
    },
  ],
}

const colliding_kiln_task_set: ToolSetApiDescription = {
  type: "kiln_task",
  set_name: "Kiln Tasks as Tools",
  tools: [
    {
      id: "kiln_task::abc",
      name: "Summarize",
      description: "Summarize the input",
      function_name: "summarize",
    },
    {
      id: "kiln_task::def",
      name: "Summarize",
      description: "Summarize the input",
      function_name: "summarize",
    },
  ],
}

const skill_set: ToolSetApiDescription = {
  type: "skill",
  set_name: "Skills",
  tools: [
    {
      id: "kiln_skill::xyz",
      name: "Research",
      description: "Do research",
      function_name: "Research",
    },
  ],
}

const all_options = (groups: ReturnType<typeof build_tool_option_groups>) =>
  groups.flatMap((group) => group.options)

describe("build_tool_option_groups labelling", () => {
  it("labels by tool name and subtitles by the tool's own description", () => {
    const [option] = all_options(build_tool_option_groups([mcp_set]))
    expect(option.label).toBe("search_docs")
    expect(option.description).toBe("Search the docs")
  })

  it("omits the subtitle when a tool has no description", () => {
    const [option] = all_options(build_tool_option_groups([kiln_task_set]))
    expect(option.description).toBeUndefined()
  })

  it("selects tool ids by default", () => {
    const [option] = all_options(build_tool_option_groups([mcp_set]))
    expect(option.value).toBe("mcp::remote::demo::search_docs")
    // Function name matches the label, so repeating it as a badge is noise.
    expect(option.badge).toBeUndefined()
  })

  it("badges the function name in id pickers when it differs from the label", () => {
    const [option] = all_options(build_tool_option_groups([code_set]))
    expect(option.label).toBe("Summarizer")
    expect(option.badge).toBe("summarize")
    // Function names are long: rendered under the label, not beside it.
    expect(option.badge_placement).toBe("below")
  })
})

describe("build_tool_option_groups name disambiguation", () => {
  it("qualifies colliding Kiln task tools by tool server id", () => {
    const labels = all_options(
      build_tool_option_groups([colliding_kiln_task_set]),
    ).map((option) => option.label)
    expect(labels).toEqual(["Summarize (abc)", "Summarize (def)"])
  })

  it("leaves a unique Kiln task tool label untouched", () => {
    const [option] = all_options(build_tool_option_groups([kiln_task_set]))
    expect(option.label).toBe("Summarize")
  })

  it("qualifies a Kiln task tool colliding with a tool in another set", () => {
    const labels = all_options(
      build_tool_option_groups([
        kiln_task_set,
        { ...mcp_set, tools: [{ ...mcp_set.tools[0], name: "Summarize" }] },
      ]),
    ).map((option) => option.label)
    // Only the Kiln task tool is qualified: the MCP tool is already grouped under
    // its server.
    expect(labels).toEqual(["Summarize (abc)", "Summarize"])
  })

  it("ignores a collision the context filter already hid from this picker", () => {
    const labels = all_options(
      build_tool_option_groups([
        kiln_task_set,
        {
          ...ai_models_set,
          tools: [{ ...ai_models_set.tools[0], name: "Summarize" }],
        },
      ]),
    ).map((option) => option.label)
    expect(labels).toEqual(["Summarize"])
  })

  it("ignores a collision with a set this picker does not order", () => {
    // Skills are not in AGENT_TOOL_SET_ORDER -- they have their own picker -- so a
    // skill of the same name is not something the user can confuse this option with.
    const labels = all_options(
      build_tool_option_groups([
        kiln_task_set,
        { ...skill_set, tools: [{ ...skill_set.tools[0], name: "Summarize" }] },
      ]),
    ).map((option) => option.label)
    expect(labels).toEqual(["Summarize"])
  })

  it("qualifies again once the picker orders the colliding set", () => {
    const labels = all_options(
      build_tool_option_groups(
        [
          kiln_task_set,
          {
            ...skill_set,
            tools: [{ ...skill_set.tools[0], name: "Summarize" }],
          },
        ],
        { set_order: [...AGENT_TOOL_SET_ORDER, "skill"] },
      ),
    ).map((option) => option.label)
    expect(labels).toEqual(["Summarize (abc)", "Summarize"])
  })
})

describe("build_tool_option_groups function-name deduplication", () => {
  const function_name_args = { value_field: "function_name" as const }

  it("offers one option per function name, not one per tool", () => {
    // Both tools record the same name in a trace, so a second row would be an
    // option the user cannot pick: FancySelect check-marks every option whose
    // value matches the selection, and labels the closed picker from the first.
    const options = all_options(
      build_tool_option_groups([colliding_kiln_task_set], function_name_args),
    )
    expect(options.map((option) => option.value)).toEqual(["summarize"])
    expect(options.map((option) => option.label)).toEqual(["Summarize"])
  })

  it("dedupes across tool sets, keeping the first offered", () => {
    const groups = build_tool_option_groups(
      [
        kiln_task_set,
        {
          ...mcp_set,
          tools: [{ ...mcp_set.tools[0], function_name: "summarize" }],
        },
      ],
      function_name_args,
    )
    expect(all_options(groups).map((option) => option.value)).toEqual([
      "summarize",
    ])
    // The MCP group had one tool and lost it, so it is gone rather than an empty
    // header.
    expect(groups.map((group) => group.label)).toEqual(["Kiln Tasks as Tools"])
  })

  it("keeps every distinct function name", () => {
    const values = all_options(
      build_tool_option_groups(
        [colliding_kiln_task_set, mcp_set],
        function_name_args,
      ),
    ).map((option) => option.value)
    expect(values).toEqual(["summarize", "search_docs"])
  })

  it("leaves an id-valued picker's options alone", () => {
    const values = all_options(
      build_tool_option_groups([colliding_kiln_task_set]),
    ).map((option) => option.value)
    expect(values).toEqual(["kiln_task::abc", "kiln_task::def"])
  })
})

describe("build_tool_option_groups function-name value field", () => {
  const function_name_args = { value_field: "function_name" as const }

  it("selects the function name a trace records", () => {
    const [option] = all_options(
      build_tool_option_groups([kiln_task_set], function_name_args),
    )
    expect(option.value).toBe("summarize")
  })

  it("badges the function name only when it differs from the display name", () => {
    const [differs] = all_options(
      build_tool_option_groups([kiln_task_set], function_name_args),
    )
    expect(differs.badge).toBe("summarize")

    // Regression: the old bespoke picker put the function name in the subtitle, so
    // every MCP/Kiln-task/RAG/skill tool -- where name and function name match --
    // rendered the same string twice and lost its real description.
    const [same] = all_options(
      build_tool_option_groups([mcp_set], function_name_args),
    )
    expect(same.badge).toBeUndefined()
    expect(same.description).toBe("Search the docs")
  })

  it("falls back to the tool name when the server sends no function name", () => {
    const [option] = all_options(
      build_tool_option_groups(
        [
          {
            ...mcp_set,
            tools: [
              {
                id: "mcp::remote::demo::legacy",
                name: "legacy_tool",
                description: null,
              },
            ],
          },
        ],
        function_name_args,
      ),
    )
    expect(option.value).toBe("legacy_tool")
    expect(option.badge).toBeUndefined()
  })
})

describe("build_tool_option_groups context scoping", () => {
  it("hides both sandbox built-ins outside a sandboxed-code context", () => {
    const values = all_options(
      build_tool_option_groups([ai_models_set, mcp_set]),
    ).map((option) => option.value)
    expect(values).toEqual(["mcp::remote::demo::search_docs"])
  })

  it("offers llm but not llm_judge in a code-tool context", () => {
    const values = all_options(
      build_tool_option_groups([ai_models_set], {
        sandbox_code_context: "code_tool",
      }),
    ).map((option) => option.value)
    expect(values).toEqual(["kiln_tool::llm"])
  })

  it("offers both in a code-eval context", () => {
    const values = all_options(
      build_tool_option_groups([ai_models_set], {
        sandbox_code_context: "code_eval",
      }),
    ).map((option) => option.value)
    expect(values).toEqual(["kiln_tool::llm", "kiln_tool::llm_judge"])
  })

  it("returns no groups when nothing is selectable, so callers show an empty state", () => {
    expect(build_tool_option_groups([ai_models_set])).toEqual([])
    expect(build_tool_option_groups(undefined)).toEqual([])
    expect(build_tool_option_groups([])).toEqual([])
  })
})

describe("build_tool_option_groups ordering and grouping", () => {
  it("orders groups by tool set, not by the order the server returned them", () => {
    const labels = build_tool_option_groups([mcp_set, kiln_task_set]).map(
      (group) => group.label,
    )
    expect(labels).toEqual(["Kiln Tasks as Tools", "MCP Server: demo"])
  })

  it("leaves skills out of the default agent set order", () => {
    expect(AGENT_TOOL_SET_ORDER).not.toContain("skill")
    expect(build_tool_option_groups([skill_set])).toEqual([])
  })

  it("includes a set type the caller asks for", () => {
    const labels = build_tool_option_groups([skill_set, mcp_set], {
      set_order: [...AGENT_TOOL_SET_ORDER, "skill"],
    }).map((group) => group.label)
    expect(labels).toEqual(["MCP Server: demo", "Skills"])
  })
})

describe("build_tool_option_groups caller hooks", () => {
  it("disables the options the caller locks", () => {
    const options = all_options(
      build_tool_option_groups([mcp_set, kiln_task_set], {
        option_disabled: (tool) => tool.id === "kiln_task::abc",
      }),
    )
    expect(options.map((option) => [option.value, option.disabled])).toEqual([
      ["kiln_task::abc", true],
      ["mcp::remote::demo::search_docs", false],
    ])
  })

  it("attaches a group action in the set's own slot", () => {
    const action_handler = vi.fn()
    const groups = build_tool_option_groups([mcp_set, kiln_task_set], {
      group_action: (set_type) =>
        set_type === "kiln_task"
          ? { action_label: "Create New", action_handler }
          : undefined,
    })
    expect(groups.map((group) => group.action_label)).toEqual([
      "Create New",
      undefined,
    ])
  })

  it("keeps an empty group so its action stays discoverable", () => {
    const groups = build_tool_option_groups([mcp_set], {
      group_action: (set_type) =>
        set_type === "kiln_task"
          ? {
              action_label: "Create New",
              action_handler: vi.fn(),
              empty_group_label: "Kiln Tasks as Tools",
            }
          : undefined,
    })
    expect(groups.map((group) => [group.label, group.options.length])).toEqual([
      ["Kiln Tasks as Tools", 0],
      ["MCP Server: demo", 1],
    ])
  })

  it("does not show a lone action when the project has no tools at all", () => {
    // The empty state ("Add Tools") has to win here -- FancySelect keys it off an
    // empty group list, so a placeholder group would suppress it.
    expect(
      build_tool_option_groups([], {
        group_action: () => ({
          action_label: "Create New",
          action_handler: vi.fn(),
          empty_group_label: "Kiln Tasks as Tools",
        }),
      }),
    ).toEqual([])
  })
})

describe("selectable_tool_sets", () => {
  it("drops sets left with no tools by the context filter", () => {
    expect(
      selectable_tool_sets([ai_models_set, mcp_set]).map((set) => set.set_name),
    ).toEqual(["MCP Server: demo"])
  })

  it("judges emptiness across every set type, including ones no picker orders", () => {
    // Skills are not in AGENT_TOOL_SET_ORDER, but a project holding only skills is
    // not a project with no tools.
    expect(selectable_tool_sets([skill_set]).length).toBe(1)
  })

  it("does not mutate the caller's tool sets", () => {
    const sets = [structuredClone(ai_models_set)]
    selectable_tool_sets(sets, "none")
    expect(sets[0].tools.length).toBe(2)
  })
})
