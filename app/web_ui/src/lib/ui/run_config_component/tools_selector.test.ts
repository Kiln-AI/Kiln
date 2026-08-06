// @vitest-environment jsdom
import { describe, it, expect, vi, beforeAll } from "vitest"
import { render } from "@testing-library/svelte"
import { tick } from "svelte"
import { available_tools } from "$lib/stores"
import type { ToolSetApiDescription } from "$lib/types"

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
  type: "builtin",
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
  code_eval_context: boolean,
  project_id: string,
): Promise<string[]> {
  available_tools.set({ [project_id]: [ai_models_set] })
  const { container } = render(ToolsSelector, {
    props: {
      project_id,
      settings: { code_eval_context },
    },
  })
  await new Promise((resolve) => setTimeout(resolve, 0))
  await tick()
  const el = container.querySelector('[data-testid="form-element-options"]')
  return JSON.parse(el?.getAttribute("data-option-values") ?? "[]")
}

async function options_for(
  tool_sets: ToolSetApiDescription[],
  project_id: string,
): Promise<{ label: string; description?: string }[]> {
  available_tools.set({ [project_id]: tool_sets })
  const { container } = render(ToolsSelector, { props: { project_id } })
  await new Promise((resolve) => setTimeout(resolve, 0))
  await tick()
  const el = container.querySelector('[data-testid="form-element-options"]')
  return JSON.parse(el?.getAttribute("data-options") ?? "[]")
}

describe("ToolsSelector option labels", () => {
  it("shows the display name, with the function name when it differs", async () => {
    const options = await options_for(
      [
        {
          type: "code",
          set_name: "Code Tools",
          tools: [
            {
              id: "kiln_tool::code::a",
              name: "Doc Search V1",
              description: "Search the docs",
              function_name: "search_docs",
            },
            {
              id: "kiln_tool::code::b",
              name: "Doc Search V2",
              description: "Search the docs",
              function_name: "search_docs",
            },
          ],
        },
      ],
      "proj_ts_labels",
    )

    expect(options.map((option) => option.label)).toEqual([
      "Doc Search V1",
      "Doc Search V2",
    ])
    for (const option of options) {
      expect(option.description).toBe("search_docs\nSearch the docs")
    }
  })

  it("does not repeat the function name when it matches the display name", async () => {
    const options = await options_for(
      [
        {
          type: "mcp",
          set_name: "MCP Server: Docs",
          tools: [
            {
              id: "kiln_tool::mcp::remote::docs::search",
              name: "search",
              description: "Search",
              function_name: "search",
            },
          ],
        },
      ],
      "proj_ts_labels_same",
    )
    expect(options.map((option) => option.description)).toEqual(["Search"])
  })
})

describe("ToolsSelector code-eval-only tool filtering", () => {
  it("hides llm_judge outside a code-eval context (keeps llm)", async () => {
    const values = await option_values(false, "proj_ts_off")
    expect(values).toContain("kiln_tool::llm")
    expect(values).not.toContain("kiln_tool::llm_judge")
  })

  it("shows llm_judge inside a code-eval context", async () => {
    const values = await option_values(true, "proj_ts_on")
    expect(values).toContain("kiln_tool::llm")
    expect(values).toContain("kiln_tool::llm_judge")
  })
})
