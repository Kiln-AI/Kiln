// @vitest-environment jsdom
// The Environment Preset field is only for callers that start a run: other
// callers (evals, run config dialogs) must render and behave exactly as before.
import {
  describe,
  it,
  expect,
  vi,
  beforeAll,
  beforeEach,
  afterEach,
} from "vitest"
import { render, cleanup } from "@testing-library/svelte"
import { tick } from "svelte"
import { available_tools, get_task_composite_id } from "$lib/stores"
import { run_configs_by_task_composite_id } from "$lib/stores/run_configs_store"
import { tools_store } from "$lib/stores/tools_store"
import type { RunOpenEnvServer, Task, TaskRunConfig } from "$lib/types"

vi.mock("$app/navigation", () => ({ goto: vi.fn() }))
vi.mock("$app/stores", async () => {
  const { readable } = await import("svelte/store")
  return {
    page: readable({ url: new URL("http://localhost/run"), params: {} }),
  }
})

vi.mock("$lib/api_client", () => ({
  client: {
    GET: vi.fn(async () => ({ data: [], error: undefined })),
    POST: vi.fn(async () => ({ data: [], error: undefined })),
  },
  base_url: "http://test",
}))

const lookup = vi.fn<[string, string, string[]], Promise<RunOpenEnvServer>>()
vi.mock("$lib/api/openenv_server_api", () => ({
  lookup_run_openenv_server: (...args: [string, string, string[]]) =>
    lookup(...args),
}))

// Only the tool picker and the new field matter here; the other pickers load
// models and prompts this test has no data for.
vi.mock("./advanced_run_options.svelte", async () => {
  const { default: Stub } = await import("./__tests__/empty_stub.svelte")
  return { default: Stub }
})
vi.mock("./prompt_type_selector.svelte", async () => {
  const { default: Stub } = await import("./__tests__/empty_stub.svelte")
  return { default: Stub }
})
vi.mock("./available_models_dropdown.svelte", async () => {
  const { default: Stub } = await import("./__tests__/empty_stub.svelte")
  return { default: Stub }
})
vi.mock(
  "$lib/ui/run_config_component/mcp_run_config_panel.svelte",
  async () => {
    const { default: Stub } = await import("./__tests__/empty_stub.svelte")
    return { default: Stub }
  },
)

const RunConfigComponent = (await import("./run_config_component.svelte"))
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
const OPENENV_TOOL = "kiln_tool::openenv::openenv_1::list_items"
const TASK = { id: "task_1", name: "Triage" } as unknown as Task

const MCP_CONFIG = {
  id: "rc_mcp",
  name: "Search directly",
  run_config_properties: {
    type: "mcp",
    tool_reference: { tool_server_id: "s1", tool_name: "search" },
  },
} as unknown as TaskRunConfig

beforeEach(() => {
  lookup.mockReset()
  lookup.mockResolvedValue({
    openenv_server: {
      id: "openenv_1",
      name: "Acme",
      is_archived: false,
      named_reset_kwargs: [
        { name: "Acme Tech", reset_kwargs: { role: "tech" } },
      ],
    },
    error: null,
  })
  available_tools.set({
    [project_id]: [
      {
        type: "openenv",
        set_name: "OpenEnv Server: Acme",
        tools: [
          {
            id: OPENENV_TOOL,
            name: "list_items",
            description: "List work items",
            function_name: "list_items",
          },
        ],
      },
    ],
  })
  tools_store.set({ selected_tool_ids_by_task_id: { task_1: [OPENENV_TOOL] } })
  run_configs_by_task_composite_id.set({
    [get_task_composite_id(project_id, "task_1")]: [MCP_CONFIG],
  })
})

afterEach(() => cleanup())

async function render_component(props: Record<string, unknown>) {
  const result = render(RunConfigComponent, {
    props: {
      project_id,
      current_task: TASK,
      show_name_field: false,
      ...props,
    },
  })
  for (let i = 0; i < 5; i++) {
    await new Promise((resolve) => setTimeout(resolve, 0))
    await tick()
  }
  return result
}

function has_field(container: HTMLElement): boolean {
  return container.textContent?.includes("Environment Preset") ?? false
}

describe("RunConfigComponent Environment Preset", () => {
  it("is off by default: no field, no lookup, no reset arguments", async () => {
    const { container, component } = await render_component({})
    expect(has_field(container)).toBe(false)
    expect(await component.get_openenv_reset_kwargs()).toBeNull()
    expect(lookup).not.toHaveBeenCalled()
  })

  it("shows the field and gives its reset arguments when turned on", async () => {
    const { container, component } = await render_component({
      show_environment_preset: true,
    })
    expect(await component.get_openenv_reset_kwargs()).toEqual({ role: "tech" })
    expect(lookup).toHaveBeenCalledWith(project_id, "task_1", [OPENENV_TOOL])
    await tick()
    expect(has_field(container)).toBe(true)
    // Inside Advanced Options, which starts collapsed, so it can't shift the page.
    const advanced = container.querySelector(".collapse-content")
    expect(advanced?.textContent).toContain("Environment Preset")
  })

  it("has no field for an MCP run config", async () => {
    const { container, component } = await render_component({
      show_environment_preset: true,
      selected_run_config_id: "rc_mcp",
    })
    expect(has_field(container)).toBe(false)
    expect(await component.get_openenv_reset_kwargs()).toBeNull()
    expect(lookup).not.toHaveBeenCalled()
  })
})
