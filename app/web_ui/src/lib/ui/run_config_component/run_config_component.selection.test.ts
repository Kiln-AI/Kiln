// @vitest-environment jsdom
// A saved run config stays selected until the user changes one of its options.
// The component holds tools and skills in two pickers and joins them as tools
// first, then skills, while a saved config may list them in any order. These
// tests pin that the order of the saved list is not read as a user's change,
// and that a config the user's edit deselected is selected again when the edit
// is undone.
import {
  describe,
  it,
  expect,
  vi,
  beforeAll,
  beforeEach,
  afterEach,
} from "vitest"
import {
  render,
  cleanup,
  screen,
  waitFor,
  fireEvent,
} from "@testing-library/svelte"
import { tick } from "svelte"
import {
  available_models,
  available_tools,
  get_task_composite_id,
} from "$lib/stores"
import { tools_store } from "$lib/stores/tools_store"
import { skills_store } from "$lib/stores/skills_store"
import { run_configs_by_task_composite_id } from "$lib/stores/run_configs_store"
import {
  get_last_used_run_config,
  last_used_run_config_store,
} from "$lib/stores/last_used_run_config_store"
import type {
  AvailableModels,
  Task,
  TaskRunConfig,
  ToolSetApiDescription,
} from "$lib/types"

vi.mock("$app/navigation", () => ({ goto: vi.fn() }))

const { GET } = vi.hoisted(() => ({ GET: vi.fn() }))
vi.mock("$lib/api_client", () => ({
  client: { GET },
  base_url: "http://localhost:0",
}))

// The input-transform picker is not what these tests are about, and its modal
// pulls a large dialog subtree into jsdom.
vi.mock("./input_transform_selector.svelte", async () => {
  const { default: Stub } = await import("./__tests__/empty_stub.svelte")
  return { default: Stub }
})

const Harness = (await import("./__tests__/selected_run_config_harness.svelte"))
  .default

beforeAll(() => {
  if (typeof globalThis.ResizeObserver === "undefined") {
    // eslint-disable-next-line @typescript-eslint/no-extraneous-class
    class ResizeObserverStub {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
    ;(
      globalThis as unknown as { ResizeObserver: typeof ResizeObserverStub }
    ).ResizeObserver = ResizeObserverStub
  }
})

const project_id = "project_1"
const task = { id: "task_1", name: "Task" } as unknown as Task

const composite_id = get_task_composite_id(project_id, "task_1")

const FINE_TUNE_CONFIG_ID = "finetune_run_config::project_1::task_1::ft_1"

const MODELS = [
  {
    provider_name: "OpenAI",
    provider_id: "openai",
    models: [
      { id: "gpt_5_4_mini", name: "GPT 5.4 Mini" },
      { id: "gpt_5_4", name: "GPT 5.4" },
      {
        id: "fine_tune_model",
        name: "Fine Tune",
        model_specific_run_config: FINE_TUNE_CONFIG_ID,
      },
    ],
  },
] as unknown as AvailableModels[]

const TOOL_A = "mcp::server::tool_a"
const TOOL_B = "mcp::server::tool_b"
const TOOL_C = "mcp::server::tool_c"
const SKILL_A = "kiln_tool::skill::skill_a"
const SKILL_B = "kiln_tool::skill::skill_b"

function tool_set(
  type: ToolSetApiDescription["type"],
  set_name: string,
  ids: string[],
): ToolSetApiDescription {
  return {
    type,
    set_name,
    tools: ids.map((id) => ({ id, name: id, description: null })),
  }
}

const TOOL_SETS: ToolSetApiDescription[] = [
  tool_set("mcp", "Server", [TOOL_A, TOOL_B, TOOL_C]),
  tool_set("skill", "Skills", [SKILL_A, SKILL_B]),
]

function saved_config(
  id: string,
  tool_ids: string[],
  model_name: string = "gpt_5_4_mini",
): TaskRunConfig {
  return {
    v: 1,
    id,
    name: id,
    run_config_properties: {
      type: "kiln_agent",
      model_name,
      model_provider_name: "openai",
      prompt_id: "simple_prompt_builder",
      temperature: 1.0,
      top_p: 1.0,
      structured_output_mode: "default",
      thinking_level: null,
      input_transform: null,
      tools_config: { tools: tool_ids },
    },
  } as unknown as TaskRunConfig
}

const TOOLS_FIRST = saved_config("tools_first", [TOOL_A, TOOL_B, SKILL_A])
// A config made outside this component (the API, the SDK) can list tools and
// skills in any order.
const MIXED_ORDER = saved_config("mixed_order", [
  TOOL_A,
  SKILL_A,
  TOOL_B,
  SKILL_B,
])
// Same options as TOOLS_FIRST, and after it in the task's list.
const TWIN = saved_config("twin", [TOOL_A, TOOL_B, SKILL_A])
const ZERO_TEMPERATURE = saved_config("zero_temperature", [TOOL_A])
ZERO_TEMPERATURE.run_config_properties = {
  ...ZERO_TEMPERATURE.run_config_properties,
  temperature: 0,
} as TaskRunConfig["run_config_properties"]
const FINE_TUNE_CONFIG = saved_config(
  FINE_TUNE_CONFIG_ID,
  [],
  "fine_tune_model",
)
const MCP_CONFIG = {
  v: 1,
  id: "mcp_config",
  name: "mcp_config",
  run_config_properties: {
    type: "mcp",
    tool_reference: { tool_id: TOOL_A, tool_name: "tool_a" },
  },
} as unknown as TaskRunConfig

beforeEach(() => {
  GET.mockImplementation(async (path: string) => {
    if (path === "/api/available_models") {
      return { data: MODELS }
    }
    return { data: undefined }
  })
  available_models.set(MODELS)
  available_tools.set({ [project_id]: TOOL_SETS })
  tools_store.set({ selected_tool_ids_by_task_id: {} })
  skills_store.set({ selected_skill_ids_by_task_id: {} })
  run_configs_by_task_composite_id.set({
    [composite_id]: [
      TOOLS_FIRST,
      MIXED_ORDER,
      TWIN,
      ZERO_TEMPERATURE,
      FINE_TUNE_CONFIG,
      MCP_CONFIG,
    ],
  })
  last_used_run_config_store.set({})
})

afterEach(cleanup)

// Long enough for the component's chained reactive passes (load the config,
// apply it to the pickers, compare) to finish.
async function settle() {
  for (let i = 0; i < 5; i++) {
    await new Promise((resolve) => setTimeout(resolve, 0))
    await tick()
  }
}

function shown(test_id: string): string {
  return screen.getByTestId(test_id).textContent ?? ""
}

// What the user does in one of the advanced panel's text fields.
async function type_in(field_id: string, text: string) {
  const input = document.getElementById(field_id) as HTMLInputElement
  await fireEvent.input(input, { target: { value: text } })
  await settle()
}

async function render_with_selection(run_config_id: string) {
  const { component } = render(Harness, {
    props: {
      project_id,
      current_task: task,
      selected_run_config_id: run_config_id,
    },
  })
  // Wait for the config's tools to reach the pickers, so a pass below means the
  // comparison ran against the applied options and not against an empty form.
  await waitFor(() => expect(shown("tools")).toContain(TOOL_A))
  await settle()
  return component
}

describe("RunConfigComponent saved run config selection", () => {
  it("keeps a config selected when its saved list has tools first, then skills", async () => {
    await render_with_selection("tools_first")
    expect(shown("selected_run_config_id")).toBe("tools_first")
  })

  it("keeps a config selected when its saved list mixes tools and skills", async () => {
    await render_with_selection("mixed_order")
    expect(JSON.parse(shown("tools"))).toEqual([TOOL_A, TOOL_B])
    expect(JSON.parse(shown("skills"))).toEqual([SKILL_A, SKILL_B])
    expect(shown("selected_run_config_id")).toBe("mixed_order")
  })

  it("changes to custom when the user adds a tool", async () => {
    const component = await render_with_selection("mixed_order")
    await component.$set({ tools: [TOOL_A, TOOL_B, TOOL_C] })
    await settle()
    expect(shown("selected_run_config_id")).toBe("custom")
  })

  it("changes to custom when the user removes a skill", async () => {
    const component = await render_with_selection("mixed_order")
    await component.$set({ skills: [SKILL_A] })
    await settle()
    expect(shown("selected_run_config_id")).toBe("custom")
  })

  it("changes to custom when the user swaps one tool for another", async () => {
    // Same count as the saved list, so only the members can tell them apart.
    const component = await render_with_selection("mixed_order")
    await component.$set({ tools: [TOOL_A, TOOL_C] })
    await settle()
    expect(shown("selected_run_config_id")).toBe("custom")
  })
})

describe("RunConfigComponent returning to a saved run config", () => {
  it("selects the config again when the user changes an option and changes it back", async () => {
    const component = await render_with_selection("tools_first")
    await component.$set({ tools: [TOOL_A, TOOL_B, TOOL_C] })
    await settle()
    expect(shown("selected_run_config_id")).toBe("custom")

    await component.$set({ tools: [TOOL_A, TOOL_B] })
    await settle()
    expect(shown("selected_run_config_id")).toBe("tools_first")
  })

  it.each(["temperature", "top_p"])(
    "selects the config again when the user types a new %s and types the old one back",
    async (field_id) => {
      await render_with_selection("tools_first")
      await type_in(field_id, "0.5")
      expect(shown("selected_run_config_id")).toBe("custom")

      await type_in(field_id, "1")
      expect(shown("selected_run_config_id")).toBe("tools_first")
    },
  )

  it("keeps the config selected when the user types the same temperature again", async () => {
    await render_with_selection("tools_first")
    await type_in("temperature", "1.0")
    expect(shown("selected_run_config_id")).toBe("tools_first")
  })

  it("leaves the typed text alone when it selects the config again", async () => {
    // The user is on the way from 1.5 to 1.7: "1." equals the saved 1.
    await render_with_selection("tools_first")
    await type_in("temperature", "1.5")
    await type_in("temperature", "1.")
    expect(shown("selected_run_config_id")).toBe("tools_first")
    const input = document.getElementById("temperature") as HTMLInputElement
    expect(input.value).toBe("1.")

    await type_in("temperature", "1.7")
    expect(shown("selected_run_config_id")).toBe("custom")
  })

  it("changes to custom when the user empties the temperature of a config that saved 0", async () => {
    await render_with_selection("zero_temperature")
    await type_in("temperature", "")
    expect(shown("selected_run_config_id")).toBe("custom")
  })

  it("selects the config again when the user picks another model and picks the old one back", async () => {
    const component = await render_with_selection("tools_first")
    await component.$set({ model: "openai/gpt_5_4" })
    await settle()
    expect(shown("selected_run_config_id")).toBe("custom")

    await component.$set({ model: "openai/gpt_5_4_mini" })
    await settle()
    expect(shown("selected_run_config_id")).toBe("tools_first")
  })

  it("returns to the config it left, not to another config with the same options", async () => {
    const component = await render_with_selection("twin")
    await component.$set({ tools: [TOOL_A, TOOL_B, TOOL_C] })
    await settle()
    await component.$set({ tools: [TOOL_A, TOOL_B] })
    await settle()
    expect(shown("selected_run_config_id")).toBe("twin")
  })

  it("stays on custom while the options still differ from the config it left", async () => {
    const component = await render_with_selection("tools_first")
    await component.$set({ tools: [TOOL_A, TOOL_B, TOOL_C] })
    await settle()
    await component.$set({ tools: [TOOL_A, TOOL_C] })
    await settle()
    expect(shown("selected_run_config_id")).toBe("custom")
  })

  it("stays on custom when the user picks Custom by hand", async () => {
    const component = await render_with_selection("tools_first")
    await component.$set({ selected_run_config_id: "custom" })
    await settle()
    expect(shown("selected_run_config_id")).toBe("custom")

    await component.$set({ tools: [TOOL_A, TOOL_B, TOOL_C] })
    await settle()
    await component.$set({ tools: [TOOL_A, TOOL_B] })
    await settle()
    expect(shown("selected_run_config_id")).toBe("custom")
  })

  it("forgets the config it left when the user picks another selection", async () => {
    const component = await render_with_selection("tools_first")
    await component.$set({ tools: [TOOL_A, TOOL_B, TOOL_C] })
    await settle()
    expect(shown("selected_run_config_id")).toBe("custom")

    await component.$set({ selected_run_config_id: "mixed_order" })
    await settle()
    expect(JSON.parse(shown("skills"))).toEqual([SKILL_A, SKILL_B])
    await component.$set({ selected_run_config_id: "custom" })
    await settle()

    // The options now agree with tools_first again.
    await component.$set({ skills: [SKILL_A] })
    await settle()
    expect(JSON.parse(shown("tools"))).toEqual([TOOL_A, TOOL_B])
    expect(shown("selected_run_config_id")).toBe("custom")
  })

  it("stays on custom when the config it left is gone from the task", async () => {
    const component = await render_with_selection("tools_first")
    await component.$set({ tools: [TOOL_A, TOOL_B, TOOL_C] })
    await settle()
    run_configs_by_task_composite_id.set({ [composite_id]: [TWIN] })
    await component.$set({ tools: [TOOL_A, TOOL_B] })
    await settle()
    expect(shown("selected_run_config_id")).toBe("custom")
  })

  it("saves the config as last used again once it is selected again", async () => {
    last_used_run_config_store.set({ [composite_id]: "tools_first" })
    const { component } = render(Harness, {
      props: {
        project_id,
        current_task: task,
        with_saved_configs_dropdown: true,
      },
    })
    await waitFor(() => expect(shown("tools")).toContain(TOOL_A))
    await settle()
    expect(shown("selected_run_config_id")).toBe("tools_first")

    await component.$set({ tools: [TOOL_A, TOOL_B, TOOL_C] })
    await settle()
    expect(get_last_used_run_config(composite_id)).toBe("custom")

    await component.$set({ tools: [TOOL_A, TOOL_B] })
    await settle()
    expect(shown("selected_run_config_id")).toBe("tools_first")
    expect(get_last_used_run_config(composite_id)).toBe("tools_first")
  })
})

describe("RunConfigComponent MCP and fine-tune run configs", () => {
  it("keeps an MCP run config selected", async () => {
    render(Harness, {
      props: {
        project_id,
        current_task: task,
        selected_run_config_id: "mcp_config",
      },
    })
    await settle()
    expect(shown("selected_run_config_id")).toBe("mcp_config")
  })

  it("does not return to an MCP run config from custom", async () => {
    const { component } = render(Harness, {
      props: {
        project_id,
        current_task: task,
        selected_run_config_id: "mcp_config",
      },
    })
    await settle()
    await component.$set({ selected_run_config_id: "custom" })
    await settle()
    await component.$set({ tools: [TOOL_A] })
    await settle()
    await component.$set({ tools: [] })
    await settle()
    expect(shown("selected_run_config_id")).toBe("custom")
  })

  it("selects a fine-tune model's run config when the model is picked", async () => {
    const { component } = render(Harness, {
      props: {
        project_id,
        current_task: task,
        selected_run_config_id: "custom",
      },
    })
    await settle()
    await component.$set({ model: "openai/fine_tune_model" })
    await settle()
    expect(shown("selected_run_config_id")).toBe(FINE_TUNE_CONFIG_ID)
  })

  it("returns to a fine-tune model's run config when an edit is undone", async () => {
    const { component } = render(Harness, {
      props: {
        project_id,
        current_task: task,
        selected_run_config_id: "custom",
      },
    })
    await settle()
    await component.$set({ model: "openai/fine_tune_model" })
    await settle()

    await component.$set({ tools: [TOOL_A] })
    await settle()
    expect(shown("selected_run_config_id")).toBe("custom")

    await component.$set({ tools: [] })
    await settle()
    expect(shown("selected_run_config_id")).toBe(FINE_TUNE_CONFIG_ID)
  })

  it("leaves a fine-tune model's run config when the user picks another model", async () => {
    const { component } = render(Harness, {
      props: {
        project_id,
        current_task: task,
        selected_run_config_id: "custom",
      },
    })
    await settle()
    await component.$set({ model: "openai/fine_tune_model" })
    await settle()
    await component.$set({ model: "openai/gpt_5_4_mini" })
    await settle()
    expect(shown("selected_run_config_id")).toBe("custom")
  })
})
