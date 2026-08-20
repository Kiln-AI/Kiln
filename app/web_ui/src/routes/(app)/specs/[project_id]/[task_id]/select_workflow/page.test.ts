// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest"
import { render, cleanup } from "@testing-library/svelte"
import { tick } from "svelte"

// ---------------------------------------------------------------------------
// Module-level mocks — must come before the dynamic page import
// ---------------------------------------------------------------------------

const {
  mockPage,
  mockGoto,
  mockClientGET,
  set_page_query,
  set_default_run_config_tools,
} = vi.hoisted(() => {
  const PROJECT_ID = "proj1"
  const TASK_ID = "task1"
  const DEFAULT_QUERY = "type=toxicity&judge=llm_judge"

  const page_value = {
    params: { project_id: PROJECT_ID, task_id: TASK_ID },
    url: new URL(
      `http://localhost/specs/${PROJECT_ID}/${TASK_ID}/select_workflow?${DEFAULT_QUERY}`,
    ),
  }
  const set_page_query = (query: string = DEFAULT_QUERY) => {
    page_value.url = new URL(
      `http://localhost/specs/${PROJECT_ID}/${TASK_ID}/select_workflow?${query}`,
    )
  }
  const mockPage = {
    subscribe(fn: (value: typeof page_value) => void) {
      fn(page_value)
      return () => {}
    },
  }

  let default_run_config_tools: string[] = []
  const set_default_run_config_tools = (tools: string[]) => {
    default_run_config_tools = tools
  }

  const mockClientGET = vi.fn().mockImplementation((path: string) => {
    if (path.endsWith("/tasks/{task_id}")) {
      return Promise.resolve({
        data: {
          v: 1,
          id: TASK_ID,
          name: "Test Task",
          instruction: "Do the thing.",
          requirements: [],
          default_run_config_id: "rc_default",
          model_type: "task",
        },
        error: null,
      })
    }
    if (path.endsWith("/run_configs")) {
      return Promise.resolve({
        data: [
          {
            v: 1,
            id: "rc_default",
            name: "Default Run Config",
            run_config_properties: {
              type: "kiln_agent",
              model_name: "gpt-4o",
              model_provider_name: "openai",
              prompt_id: "simple_prompt_builder",
              top_p: 1,
              temperature: 1,
              structured_output_mode: "default",
              tools_config: { tools: default_run_config_tools },
            },
            starred: false,
            model_type: "task_run_config",
          },
        ],
        error: null,
      })
    }
    return Promise.resolve({ data: null, error: null })
  })

  return {
    mockPage,
    mockGoto: vi.fn(),
    mockClientGET,
    set_page_query,
    set_default_run_config_tools,
  }
})

// Svelte 4 onMount callbacks do not execute in jsdom/vitest, and the page keeps
// its loading state until the onMount task load settles. Run it here instead,
// deferred to a microtask so the component's reactive statements (the route
// params and query the callback reads) have been computed first.
vi.mock("svelte", async (importOriginal) => {
  const actual = await importOriginal<typeof import("svelte")>()
  return {
    ...actual,
    // @testing-library/svelte probes this Svelte 5 only export to pick a mount strategy.
    mount: undefined,
    onMount: (fn: () => unknown) => queueMicrotask(() => void fn()),
  }
})

vi.mock("$app/stores", () => ({
  page: mockPage,
}))

vi.mock("$app/navigation", () => ({
  goto: mockGoto,
}))

vi.mock("$lib/api_client", () => ({
  client: {
    GET: mockClientGET,
  },
}))

vi.mock("$lib/agent", () => ({
  agentInfo: { set: vi.fn() },
}))

vi.mock("posthog-js", () => ({
  default: { capture: vi.fn() },
}))

vi.mock("../../../../app_page.svelte", async () => {
  const Stub = await import("../__tests__/app_page_stub.svelte")
  return { default: Stub.default }
})

// Dynamic imports after all mocks
const SelectWorkflowPage = (await import("./+page.svelte")).default
const { run_configs_by_task_composite_id } = await import(
  "$lib/stores/run_configs_store"
)

const TOOLS_NOTE =
  "Tool calling is not yet supported in Kiln Pro. Please create this eval manually for now."
const TOOLS_TOOLTIP = "Not supported for tasks with tools"

async function render_page() {
  const result = render(SelectWorkflowPage)
  // onMount awaits the task load and the run config load before rendering the
  // body, so flush a few macrotask turns.
  for (let i = 0; i < 5; i++) {
    await new Promise((r) => setTimeout(r, 0))
    await tick()
  }
  return result
}

function workflow_button(container: HTMLElement, label: string) {
  const button = Array.from(container.querySelectorAll("button")).find(
    (candidate) => candidate.textContent?.trim() === label,
  )
  expect(button).toBeTruthy()
  return button as HTMLButtonElement
}

afterEach(() => {
  cleanup()
  mockGoto.mockClear()
  set_page_query()
  set_default_run_config_tools([])
  // The run config store caches by task, so a stale entry would leak between tests.
  run_configs_by_task_composite_id.set({})
})

describe("select workflow screen — tool-enabled default run config", () => {
  // Regression: this screen used to redirect straight to the manual builder
  // when the default run config had tools, so users never learned Kiln Pro
  // existed or why it was unavailable.
  it("renders the workflow choice instead of redirecting to the manual builder", async () => {
    set_default_run_config_tools(["mcp::local::weather"])

    const { getByText } = await render_page()

    expect(mockGoto).not.toHaveBeenCalled()
    expect(getByText("Choose your Eval Creation Workflow")).toBeTruthy()
  })

  it("disables Kiln Pro and explains why, in a note and a tooltip", async () => {
    set_default_run_config_tools(["mcp::local::weather"])

    const { container, getByText } = await render_page()

    expect(getByText(TOOLS_NOTE)).toBeTruthy()
    const tooltip = container.querySelector(`[data-tip="${TOOLS_TOOLTIP}"]`)
    expect(tooltip).toBeTruthy()
    // The button sits in the rightmost column of a table inside an
    // overflow-x-auto container. A top-positioned bubble is centered on the
    // button and overhangs the container's right edge, where it gets clipped
    // and adds phantom horizontal scroll; opening it leftwards keeps it inside.
    expect(tooltip?.className).toContain("tooltip-left")
    expect(workflow_button(container, "Use Kiln Pro").disabled).toBe(true)
    expect(workflow_button(container, "Create Manually").disabled).toBe(false)
  })
})

describe("select workflow screen — default run config without tools", () => {
  it("offers Kiln Pro with no limitation note", async () => {
    const { container, queryByText } = await render_page()

    expect(mockGoto).not.toHaveBeenCalled()
    expect(queryByText(TOOLS_NOTE)).toBeNull()
    expect(container.querySelector("[data-tip]")).toBeNull()
    expect(workflow_button(container, "Use Kiln Pro").disabled).toBe(false)
  })
})

describe("select workflow screen — spec types Kiln Pro can't build", () => {
  // The spec-type level skip is intentional and must survive: it proves the
  // "no redirect" assertions above would catch a reinstated redirect.
  it("redirects to the manual builder for a non-LLM judge", async () => {
    set_page_query("type=issue&judge=code_eval")

    await render_page()

    expect(mockGoto).toHaveBeenCalledTimes(1)
    const [url, options] = mockGoto.mock.calls[0]
    expect(url).toContain("/specs/proj1/task1/spec_builder?")
    expect(url).toContain("workflow=manual")
    expect(options).toEqual({ replaceState: true })
  })
})
