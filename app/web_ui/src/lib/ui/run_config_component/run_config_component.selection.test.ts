// @vitest-environment jsdom
// A saved run config stays selected until the user changes one of its options.
// The component holds tools and skills in two pickers and joins them as tools
// first, then skills, while a saved config may list them in any order. These
// tests pin that the order of the saved list is not read as a user's change.
import {
  describe,
  it,
  expect,
  vi,
  beforeAll,
  beforeEach,
  afterEach,
} from "vitest"
import { render, cleanup, screen, waitFor } from "@testing-library/svelte"
import { tick } from "svelte"
import {
  available_models,
  available_tools,
  get_task_composite_id,
} from "$lib/stores"
import { tools_store } from "$lib/stores/tools_store"
import { skills_store } from "$lib/stores/skills_store"
import { run_configs_by_task_composite_id } from "$lib/stores/run_configs_store"
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

// The advanced panel is not what these tests are about, and its input-transform
// modal pulls a large dialog subtree into jsdom.
vi.mock("./advanced_run_options.svelte", async () => {
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

const MODELS = [
  {
    provider_name: "OpenAI",
    provider_id: "openai",
    models: [{ id: "gpt_5_4_mini", name: "GPT 5.4 Mini" }],
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

function saved_config(id: string, tool_ids: string[]): TaskRunConfig {
  return {
    v: 1,
    id,
    name: id,
    run_config_properties: {
      type: "kiln_agent",
      model_name: "gpt_5_4_mini",
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
// The order a config gets when tools and skills are added to it in turns.
const MIXED_ORDER = saved_config("mixed_order", [
  TOOL_A,
  SKILL_A,
  TOOL_B,
  SKILL_B,
])

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
    [get_task_composite_id(project_id, "task_1")]: [TOOLS_FIRST, MIXED_ORDER],
  })
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
