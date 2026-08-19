// @vitest-environment jsdom
/**
 * Prop-relay guard for JudgeConfigFields.
 *
 * Each judge form is rendered through <svelte:component>, so a missing prop is
 * silently swallowed: the form falls back to its default (an empty project_id),
 * and the tools picker inside it spins forever instead of erroring. These tests
 * assert the project context actually reaches the forms that need it.
 */
import { describe, it, expect, vi, beforeAll, afterEach } from "vitest"
import { render, cleanup } from "@testing-library/svelte"
import { tick } from "svelte"
import { available_tools } from "$lib/stores"
import type { ToolSetApiDescription } from "$lib/types"

vi.mock("$lib/components/code_editor.svelte", async () => {
  const { default: Stub } = await import("./__tests__/code_editor_stub.svelte")
  return { default: Stub }
})

vi.mock("$lib/ui/dialog.svelte", async () => {
  const { default: Stub } = await import("./__tests__/dialog_stub.svelte")
  return { default: Stub }
})

vi.mock("$lib/utils/form_element.svelte", async () => {
  const { default: Stub } = await import("./__tests__/form_element_stub.svelte")
  return { default: Stub }
})

vi.mock("$lib/ui/collapse.svelte", async () => {
  const { default: Stub } = await import("./__tests__/collapse_stub.svelte")
  return { default: Stub }
})

vi.mock("$lib/ui/run_config_component/tools_selector.svelte", async () => {
  const { default: Stub } = await import(
    "./__tests__/tools_selector_stub.svelte"
  )
  return { default: Stub }
})

// FormList is deliberately NOT stubbed: the real one seeds an empty row, which
// is what renders the tool-call-check dropdown these tests read.
const JudgeConfigFields = (await import("./judge_config_fields.svelte")).default

const PROJECT_ID = "proj_judge_fields"
const TASK_ID = "task_judge_fields"

const mcp_tool_set: ToolSetApiDescription = {
  type: "mcp",
  set_name: "MCP Server: demo",
  tools: [
    {
      id: "mcp::remote::demo::search",
      name: "Search",
      description: "Search the web",
      function_name: "search",
    },
  ],
}

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

afterEach(() => {
  cleanup()
  available_tools.set({})
})

describe("JudgeConfigFields project context relay", () => {
  it("gives the code judge a project_id, so its tools picker can load", () => {
    const { container } = render(JudgeConfigFields, {
      props: {
        eval_config_type: "code_eval",
        project_id: PROJECT_ID,
        task_id: TASK_ID,
      },
    })

    const tools_selector = container.querySelector(
      '[data-testid="tools-selector-stub"]',
    )
    expect(tools_selector).not.toBeNull()
    expect(tools_selector?.getAttribute("data-project-id")).toBe(PROJECT_ID)
  })

  it("gives the tool call check judge both a project_id and a task_id", async () => {
    available_tools.set({ [PROJECT_ID]: [mcp_tool_set] })

    const { container } = render(JudgeConfigFields, {
      props: {
        eval_config_type: "tool_call_check",
        project_id: PROJECT_ID,
        task_id: TASK_ID,
      },
    })

    // Let the store subscription fire, then flush reactivity.
    await new Promise((resolve) => setTimeout(resolve, 0))
    await tick()

    // The form builds its dropdown options only once it has a non-empty
    // project_id (to key into the loaded tools) AND task_id, so one option
    // proves both props arrived.
    expect(
      container.querySelector('[data-testid="fancy-option-search"]'),
    ).not.toBeNull()
  })
})
