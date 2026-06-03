// @vitest-environment jsdom
import { describe, it, expect, beforeEach, vi } from "vitest"
import { render } from "@testing-library/svelte"
import { tick } from "svelte"
import type { AvailableModels, Task, TaskRunConfig } from "$lib/types"
import { available_models } from "$lib/stores"
import { run_configs_by_task_composite_id } from "$lib/stores/run_configs_store"
import { get_task_composite_id } from "$lib/stores"

// Replace all child components with a no-op stub so we exercise only the
// parent's reactive state machine (the source of the infinite-loop bug),
// without the children performing their own data loading.
vi.mock("../available_models_dropdown.svelte", async () => ({
  default: (await import("./empty_stub.svelte")).default,
}))
vi.mock("../prompt_type_selector.svelte", async () => ({
  default: (await import("./empty_stub.svelte")).default,
}))
vi.mock("../tools_selector.svelte", async () => ({
  default: (await import("./empty_stub.svelte")).default,
}))
vi.mock("../skills_selector.svelte", async () => ({
  default: (await import("./empty_stub.svelte")).default,
}))
vi.mock("../advanced_run_options.svelte", async () => ({
  default: (await import("./empty_stub.svelte")).default,
}))
vi.mock("../mcp_run_config_panel.svelte", async () => ({
  default: (await import("./empty_stub.svelte")).default,
}))

// Stub the API client. Data the parent needs is seeded directly into the
// stores below, so these only need to avoid real network calls.
vi.mock("$lib/api_client", () => ({
  client: {
    GET: vi.fn(async (path: string) => {
      if (path === "/api/available_models") {
        return { data: MODELS, error: null }
      }
      if (path.endsWith("/run_configs")) {
        return { data: [DEEP_LINKED_CONFIG], error: null }
      }
      if (path.endsWith("/prompts")) {
        return { data: { generators: [], prompts: [] }, error: null }
      }
      return { data: [], error: null }
    }),
    POST: vi.fn(async () => ({ data: null, error: null })),
  },
}))

const PROJECT_ID = "project-1"
const TASK: Task = { id: "task-1", name: "Test Task" } as unknown as Task

const MODELS = [
  {
    provider_name: "OpenAI",
    provider_id: "openai",
    models: [
      {
        id: "gpt-4o",
        name: "GPT-4o",
        structured_output_mode: "json_schema",
      },
      {
        id: "gpt-4o-mini",
        name: "GPT-4o mini",
        structured_output_mode: "json_schema",
      },
    ],
  },
] as unknown as AvailableModels[]

const DEEP_LINKED_CONFIG = {
  id: "rc-1",
  name: "Deep linked config",
  run_config_properties: {
    type: "kiln_agent",
    model_name: "gpt-4o",
    model_provider_name: "openai",
    prompt_id: "simple_prompt_builder",
    temperature: 1.0,
    top_p: 1.0,
    structured_output_mode: "json_schema",
    thinking_level: null,
    tools_config: { tools: [] },
  },
} as unknown as TaskRunConfig

// Flush a bounded number of reactive cycles to let the (fixed) component
// settle. If a regression reintroduces the infinite reactive loop, the
// assertions below will fail (or the runner will time out, since the runaway
// microtask cascade is exactly the "browser hang" this fixes).
async function flush(cycles = 100) {
  for (let i = 0; i < cycles; i++) {
    await tick()
  }
}

describe("RunConfigComponent deep-link + manual model change", () => {
  beforeEach(() => {
    available_models.set(MODELS)
    run_configs_by_task_composite_id.set({
      [get_task_composite_id(PROJECT_ID, TASK.id as string)]: [
        DEEP_LINKED_CONFIG,
      ],
    })
  })

  it("applies the deep-linked run config on load, then settles to custom when the model is changed manually (no infinite loop)", async () => {
    const Harness = (await import("./run_config_loop_harness.svelte")).default
    const { getByTestId, component } = render(Harness, {
      props: {
        project_id: PROJECT_ID,
        current_task: TASK,
        pending_run_config_id: "rc-1",
        model: "",
      },
    })

    await flush()

    // Deep link applied: the run config is selected and its model is filled in.
    expect(getByTestId("selected").textContent).toBe("rc-1")
    expect(getByTestId("model").textContent).toBe("openai/gpt-4o")

    // Simulate the user manually changing the model in the dropdown.
    component.$set({ model: "openai/gpt-4o-mini" })
    await flush()

    // It must settle: the run config deselects to "custom" and the user's
    // manual model choice is preserved (the deep link does not keep
    // re-forcing the original config, which previously caused an infinite loop).
    expect(getByTestId("model").textContent).toBe("openai/gpt-4o-mini")
    expect(getByTestId("selected").textContent).toBe("custom")
  })
})
