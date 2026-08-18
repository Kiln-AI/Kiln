// @vitest-environment jsdom
import { describe, it, expect, vi, beforeAll } from "vitest"
import { render } from "@testing-library/svelte"
import { tick } from "svelte"
import { available_tools } from "$lib/stores"
import type { ToolSetApiDescription } from "$lib/types"
import type { SandboxCodeContext } from "$lib/stores/tools_store"

vi.mock("$app/navigation", () => ({ goto: vi.fn() }))

vi.mock("$lib/utils/form_element.svelte", async () => {
  const { default: Stub } = await import(
    "./__tests__/form_element_options_stub.svelte"
  )
  return { default: Stub }
})

const ToolsSelector = (await import("./tools_selector.svelte")).default

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

async function option_values(
  sandbox_code_context: SandboxCodeContext,
  project_id: string,
  tool_sets: ToolSetApiDescription[] = [ai_models_set],
): Promise<{ values: string[]; group_count: number }> {
  available_tools.set({ [project_id]: tool_sets })
  const { container } = render(ToolsSelector, {
    props: {
      project_id,
      // hide_create_kiln_task_tool_button is left at its default (false), so this
      // matches the general agent picker — the configuration the empty state
      // regressed in.
      settings: { sandbox_code_context },
    },
  })
  await new Promise((resolve) => setTimeout(resolve, 0))
  await tick()
  const el = container.querySelector('[data-testid="form-element-options"]')
  return {
    values: JSON.parse(el?.getAttribute("data-option-values") ?? "[]"),
    group_count: Number(el?.getAttribute("data-option-group-count") ?? -1),
  }
}

describe("ToolsSelector sandbox-only tool filtering", () => {
  it("hides both sandbox built-ins outside any sandboxed-code context", async () => {
    const { values } = await option_values("none", "proj_ts_off")
    expect(values).not.toContain("kiln_tool::llm")
    expect(values).not.toContain("kiln_tool::llm_judge")
  })

  it("offers llm but not llm_judge in a code-tool context", async () => {
    const { values } = await option_values("code_tool", "proj_ts_tool")
    expect(values).toContain("kiln_tool::llm")
    expect(values).not.toContain("kiln_tool::llm_judge")
  })

  it("offers both in a code-eval context", async () => {
    const { values } = await option_values("code_eval", "proj_ts_eval")
    expect(values).toContain("kiln_tool::llm")
    expect(values).toContain("kiln_tool::llm_judge")
  })

  it("still shows the empty state when only unselectable tools exist", async () => {
    // Regression: the AI Models set ships in every project, so a raw
    // available_tools length check would hide the "Add tools" onboarding from
    // every project that has configured no tools of its own. FancySelect keys the
    // empty state off options.length === 0, so no groups at all is the assertion.
    const { group_count } = await option_values("none", "proj_ts_empty")
    expect(group_count).toBe(0)
  })

  it("hides a sandbox_code set by its type, not by tool id", async () => {
    // The coarse rule must survive a KilnBuiltInToolId rename: nothing here is
    // matched by id, so an unrecognised tool in a sandbox_code set is still hidden.
    const { values, group_count } = await option_values(
      "none",
      "proj_ts_renamed",
      [
        {
          type: "sandbox_code",
          set_name: "AI Models",
          tools: [
            {
              id: "kiln_tool::renamed_after_a_refactor",
              name: "LLM",
              description: "Call a model",
              function_name: "llm",
            },
          ],
        },
      ],
    )
    expect(values).toEqual([])
    expect(group_count).toBe(0)
  })

  it("keeps ordinary tool sets visible outside a sandboxed-code context", async () => {
    const { values } = await option_values("none", "proj_ts_mixed", [
      ai_models_set,
      {
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
      },
    ])
    expect(values).toEqual(["mcp::remote::demo::search"])
  })
})
