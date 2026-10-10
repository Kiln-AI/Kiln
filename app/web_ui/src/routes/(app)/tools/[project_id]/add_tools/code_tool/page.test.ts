// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, cleanup, fireEvent, waitFor } from "@testing-library/svelte"
import { tick } from "svelte"

// ---------------------------------------------------------------------------
// Hoisted mocks (must exist before the page module import)
// ---------------------------------------------------------------------------
const { mockPageStore, mockGoto, mockPushState, setInitialState, mockPost } =
  vi.hoisted(() => {
    type PageValue = {
      params: Record<string, string>
      state: Record<string, unknown>
    }
    let value: PageValue = { params: { project_id: "proj1" }, state: {} }
    const subs = new Set<(v: PageValue) => void>()
    function emit() {
      subs.forEach((fn) => fn(value))
    }
    const mockPageStore = {
      subscribe(fn: (v: PageValue) => void) {
        subs.add(fn)
        fn(value)
        return () => subs.delete(fn)
      },
    }
    const mockGoto = vi.fn()
    // Mirror SvelteKit pushState: it replaces page.state with the given object.
    const mockPushState = vi.fn(
      (_url: string, state: Record<string, unknown>) => {
        value = { ...value, state }
        emit()
      },
    )
    function setInitialState(state: Record<string, unknown>) {
      value = { ...value, state }
      emit()
    }
    const mockPost = vi.fn()
    return { mockPageStore, mockGoto, mockPushState, setInitialState, mockPost }
  })

vi.mock("$app/stores", () => ({ page: mockPageStore }))
vi.mock("$app/navigation", () => ({
  goto: mockGoto,
  pushState: mockPushState,
  beforeNavigate: vi.fn(),
}))

vi.mock("$lib/api_client", () => ({
  client: { GET: vi.fn(), POST: (...args: unknown[]) => mockPost(...args) },
}))

vi.mock("$lib/stores", () => {
  const { writable } = require("svelte/store")
  return {
    uncache_available_tools: vi.fn(),
    available_tools: writable({}),
    ui_state: writable({ current_task_id: "task1" }),
  }
})

vi.mock("posthog-js", () => ({ default: { capture: vi.fn() } }))
vi.mock("$lib/agent", () => ({ agentInfo: { set: vi.fn() } }))

// Stub heavy child components (same specifiers the page imports).
vi.mock("../../../../app_page.svelte", async () => ({
  default: (await import("./__tests__/app_page_stub.svelte")).default,
}))
vi.mock(
  "../../../../../(fullscreen)/setup/(setup)/create_task/schema_section.svelte",
  async () => ({
    default: (await import("./__tests__/schema_section_stub.svelte")).default,
  }),
)
vi.mock("$lib/components/code_editor.svelte", async () => ({
  default: (await import("./__tests__/code_editor_stub.svelte")).default,
}))
vi.mock("$lib/components/code_tools/code_tool_test_panel.svelte", async () => ({
  default: (await import("./__tests__/code_tool_test_panel_stub.svelte"))
    .default,
}))
vi.mock("$lib/components/code_tools/code_trust_dialog.svelte", async () => ({
  default: (await import("./__tests__/code_trust_dialog_stub.svelte")).default,
}))
vi.mock("$lib/ui/run_config_component/tools_selector.svelte", async () => ({
  default: (await import("./__tests__/tools_selector_stub.svelte")).default,
}))
vi.mock("$lib/ui/collapse.svelte", async () => ({
  default: (await import("./__tests__/collapse_stub.svelte")).default,
}))
vi.mock("$lib/ui/dialog.svelte", async () => ({
  default: (await import("./__tests__/dialog_stub.svelte")).default,
}))

import CodeToolPage from "./+page.svelte"

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

beforeEach(() => {
  mockPost.mockReset()
  mockPost.mockResolvedValue({
    data: { id: "new-code-tool-id", not_trusted: false },
    error: null,
  })
})

async function set_input(container: HTMLElement, id: string, value: string) {
  const el = container.querySelector(`#${id}`) as HTMLInputElement
  await fireEvent.input(el, { target: { value } })
  await tick()
}

function button_with_text(container: HTMLElement, text: string): HTMLElement {
  const btn = Array.from(container.querySelectorAll("button")).find((b) =>
    b.textContent?.includes(text),
  )
  if (!btn) throw new Error(`button "${text}" not found`)
  return btn as HTMLElement
}

// Drive the two-step wizard to the create POST and return the POSTed body.
async function create_and_get_body(container: HTMLElement) {
  // Step 1 -> Step 2
  await fireEvent.click(button_with_text(container, "Continue"))
  const create_btn = await waitFor(() => {
    const btn = container.querySelector('[data-testid="create-btn"]')
    if (!btn) throw new Error("create button not shown yet")
    return btn as HTMLElement
  })
  // Step 2: create
  await fireEvent.click(create_btn)
  await waitFor(() => expect(mockPost).toHaveBeenCalled())
  // Let the code-editor setValue timer (scheduled on step transition) fire
  // while the component is still mounted, so it doesn't error after cleanup.
  await new Promise((r) => setTimeout(r, 0))
  return mockPost.mock.calls[0][1].body
}

describe("Code tool create page provenance stamping", () => {
  it("fresh create sends human-origin provenance with no parent", async () => {
    setInitialState({})
    const { container } = render(CodeToolPage)
    await tick()

    await set_input(container, "name", "My Tool")
    await set_input(container, "tool_function_name", "my_tool")

    const body = await create_and_get_body(container)
    expect(body.provenance).toEqual({ origin: "human" })
  })

  it("clone create stamps derived_from_ids with the source code tool id", async () => {
    setInitialState({
      name: "My Tool (copy)",
      tool_function_name: "my_tool_copy",
      tool_description: "Looks up a user.",
      parameters_schema_string: JSON.stringify({
        type: "object",
        properties: {},
      }),
      code: "def run():\n    return 1\n",
      timeout_seconds: 60,
      tool_allowlist: [],
      clone_source_id: "src-code-tool-id",
    })
    const { container } = render(CodeToolPage)
    await tick()

    const body = await create_and_get_body(container)
    expect(body.provenance).toEqual({
      origin: "human",
      derived_from_ids: ["src-code-tool-id"],
    })
  })
})
