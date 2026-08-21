// @vitest-environment jsdom
import { describe, it, expect, vi, beforeAll } from "vitest"
import { render } from "@testing-library/svelte"
import { tick } from "svelte"
<<<<<<< HEAD
import { available_tools } from "$lib/stores"
import type { ToolSetApiDescription } from "$lib/types"
=======
import { get } from "svelte/store"
import { available_tools } from "$lib/stores"
import { tools_store } from "$lib/stores/tools_store"
import type { ToolSetApiDescription } from "$lib/types"
import type { SandboxCodeContext } from "$lib/stores/tools_store"
>>>>>>> 721c4941b

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
<<<<<<< HEAD
  type: "builtin",
=======
  type: "sandbox_code",
>>>>>>> 721c4941b
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
<<<<<<< HEAD
  code_eval_context: boolean,
  project_id: string,
): Promise<string[]> {
  available_tools.set({ [project_id]: [ai_models_set] })
  const { container } = render(ToolsSelector, {
    props: {
      project_id,
      settings: { code_eval_context },
=======
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
>>>>>>> 721c4941b
    },
  })
  await new Promise((resolve) => setTimeout(resolve, 0))
  await tick()
  const el = container.querySelector('[data-testid="form-element-options"]')
<<<<<<< HEAD
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
=======
  return {
    values: JSON.parse(el?.getAttribute("data-option-values") ?? "[]"),
    group_count: Number(el?.getAttribute("data-option-group-count") ?? -1),
  }
}

const mcp_set: ToolSetApiDescription = {
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

// The value actually bound out of the picker (and written to tools_store), as
// opposed to the options it displays.
async function bound_tools(props: {
  project_id: string
  sandbox_code_context: SandboxCodeContext
  task_id?: string | null
  pending_tool_id?: string | null
  tool_sets?: ToolSetApiDescription[]
}): Promise<string[]> {
  available_tools.set({
    [props.project_id]: props.tool_sets ?? [ai_models_set, mcp_set],
  })
  const { container } = render(ToolsSelector, {
    props: {
      project_id: props.project_id,
      task_id: props.task_id ?? null,
      pending_tool_id: props.pending_tool_id ?? null,
      settings: { sandbox_code_context: props.sandbox_code_context },
    },
  })
  await new Promise((resolve) => setTimeout(resolve, 0))
  await tick()
  const el = container.querySelector('[data-testid="form-element-options"]')
  return JSON.parse(el?.getAttribute("data-value") ?? "null")
}

function seed_persisted_tools(task_id: string, tool_ids: string[]) {
  tools_store.set({ selected_tool_ids_by_task_id: { [task_id]: tool_ids } })
}

function persisted_tools(task_id: string): string[] | undefined {
  return get(tools_store).selected_tool_ids_by_task_id[task_id]
}

describe("ToolsSelector context scoping on the write path", () => {
  it("drops a persisted llm_judge outside a code-eval context", async () => {
    const task_id = "task_persisted_none"
    seed_persisted_tools(task_id, [
      "kiln_tool::llm_judge",
      "mcp::remote::demo::search",
    ])

    const tools = await bound_tools({
      project_id: "proj_write_none",
      sandbox_code_context: "none",
      task_id,
    })

    expect(tools).toEqual(["mcp::remote::demo::search"])
    // The store is the thing that outlives the page, so assert it directly.
    expect(persisted_tools(task_id)).toEqual(["mcp::remote::demo::search"])
  })

  it("keeps a persisted llm_judge in a code-eval context", async () => {
    // Positive control: the previous test must fail because of the context, not
    // because persisted tools never survive at all.
    const task_id = "task_persisted_eval"
    seed_persisted_tools(task_id, [
      "kiln_tool::llm_judge",
      "mcp::remote::demo::search",
    ])

    const tools = await bound_tools({
      project_id: "proj_write_eval",
      sandbox_code_context: "code_eval",
      task_id,
    })

    expect(tools).toEqual(["kiln_tool::llm_judge", "mcp::remote::demo::search"])
    expect(persisted_tools(task_id)).toEqual([
      "kiln_tool::llm_judge",
      "mcp::remote::demo::search",
    ])
  })

  it("drops a persisted llm_judge in a code-tool context", async () => {
    // llm_judge needs a code judge's score schema, so a code tool may never hold it
    // even though the rest of the sandbox_code set is fair game there.
    const task_id = "task_persisted_tool"
    seed_persisted_tools(task_id, ["kiln_tool::llm", "kiln_tool::llm_judge"])

    const tools = await bound_tools({
      project_id: "proj_write_tool",
      sandbox_code_context: "code_tool",
      task_id,
    })

    expect(tools).toEqual(["kiln_tool::llm"])
    expect(persisted_tools(task_id)).toEqual(["kiln_tool::llm"])
  })

  it("refuses a pending llm_judge outside a code-eval context", async () => {
    const task_id = "task_pending_none"
    seed_persisted_tools(task_id, [])

    const tools = await bound_tools({
      project_id: "proj_pending_none",
      sandbox_code_context: "none",
      task_id,
      pending_tool_id: "kiln_tool::llm_judge",
    })

    expect(tools).toEqual([])
    expect(persisted_tools(task_id)).toEqual([])
  })

  it("applies a pending llm_judge in a code-eval context", async () => {
    // Positive control for the pending path: ?tool_id= still works where allowed.
    const task_id = "task_pending_eval"
    seed_persisted_tools(task_id, [])

    const tools = await bound_tools({
      project_id: "proj_pending_eval",
      sandbox_code_context: "code_eval",
      task_id,
      pending_tool_id: "kiln_tool::llm_judge",
    })

    expect(tools).toEqual(["kiln_tool::llm_judge"])
    expect(persisted_tools(task_id)).toEqual(["kiln_tool::llm_judge"])
  })

  it("still drops tools the server no longer offers", async () => {
    // The context rule is layered on top of the availability rule, not in place of it.
    const task_id = "task_removed_tool"
    seed_persisted_tools(task_id, [
      "mcp::remote::demo::search",
      "mcp::remote::demo::deleted",
    ])

    const tools = await bound_tools({
      project_id: "proj_removed",
      sandbox_code_context: "none",
      task_id,
    })

    expect(tools).toEqual(["mcp::remote::demo::search"])
  })
})

describe("ToolsSelector sandbox-only tool filtering", () => {
  it("hides both sandbox built-ins outside any sandboxed-code context", async () => {
    const { values } = await option_values("none", "proj_ts_off")
    expect(values).not.toContain("kiln_tool::llm")
    expect(values).not.toContain("kiln_tool::llm_judge")
  })

  it("offers llm but not llm_judge in a code-tool context", async () => {
    const { values } = await option_values("code_tool", "proj_ts_tool")
>>>>>>> 721c4941b
    expect(values).toContain("kiln_tool::llm")
    expect(values).not.toContain("kiln_tool::llm_judge")
  })

<<<<<<< HEAD
  it("shows llm_judge inside a code-eval context", async () => {
    const values = await option_values(true, "proj_ts_on")
    expect(values).toContain("kiln_tool::llm")
    expect(values).toContain("kiln_tool::llm_judge")
  })
=======
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
      mcp_set,
    ])
    expect(values).toEqual(["mcp::remote::demo::search"])
  })
>>>>>>> 721c4941b
})
