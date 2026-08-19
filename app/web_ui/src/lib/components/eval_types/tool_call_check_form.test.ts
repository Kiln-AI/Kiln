// @vitest-environment jsdom
import { describe, it, expect, vi } from "vitest"
import { render } from "@testing-library/svelte"
import { tick } from "svelte"
import { available_tools } from "$lib/stores"
import type { ToolSetApiDescription } from "$lib/types"

vi.mock("$lib/utils/form_element.svelte", async () => {
  const StubModule = await import("./__tests__/form_element_stub.svelte")
  return { default: StubModule.default }
})

vi.mock("$lib/utils/form_list.svelte", async () => {
  const StubModule = await import("./__tests__/form_list_stub.svelte")
  return { default: StubModule.default }
})

vi.mock("$lib/ui/collapse.svelte", async () => {
  const StubModule = await import("./__tests__/collapse_stub.svelte")
  return { default: StubModule.default }
})

const ToolCallCheckForm = (await import("./tool_call_check_form.svelte"))
  .default

const mcp_set: ToolSetApiDescription = {
  type: "mcp",
  set_name: "MCP Server: demo",
  tools: [
    {
      id: "mcp::remote::demo::search_docs",
      name: "search_docs",
      description: "Search the docs",
      function_name: "search_docs",
    },
  ],
}

const code_tool_set: ToolSetApiDescription = {
  type: "code",
  set_name: "Code Tools",
  tools: [
    {
      id: "code_tool::abc",
      name: "Word Count",
      description: "Count words in the output",
      function_name: "word_count",
    },
  ],
}

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
  ],
}

const skill_set: ToolSetApiDescription = {
  type: "skill",
  set_name: "Skills",
  tools: [
    {
      id: "kiln_skill::xyz",
      name: "Research",
      description: "Do research",
      function_name: "Research",
    },
  ],
}

type RenderedOption = {
  value: string
  label: string
  description: string
  badge: string
}

async function render_options(
  tool_sets: ToolSetApiDescription[],
  expected_tool_names: string[] = [""],
): Promise<{ options: RenderedOption[]; group_labels: string[] }> {
  const project_id = "proj_" + Math.random().toString(36).slice(2)
  available_tools.set({ [project_id]: tool_sets })
  const { container } = render(ToolCallCheckForm, {
    props: {
      project_id,
      task_id: "task_1",
      properties: {
        type: "tool_call_check",
        expected_tools: expected_tool_names.map((tool_name) => ({
          tool_name,
          expected_args: null,
        })),
        match_mode: "all",
        on_unexpected_tools: "ignore",
      },
    },
  })
  await tick()
  const select = container.querySelector(
    '[data-testid="fancy-select-tool_name_0"]',
  )
  const options = Array.from(
    select?.querySelectorAll("[data-value]") ?? [],
  ).map((el) => ({
    value: el.getAttribute("data-value") ?? "",
    label: el.querySelector("span")?.textContent?.trim() ?? "",
    description: el.getAttribute("data-option-description") ?? "",
    badge: el.getAttribute("data-badge") ?? "",
  }))
  return {
    options,
    group_labels: JSON.parse(select?.getAttribute("data-group-labels") ?? "[]"),
  }
}

describe("ToolCallCheckForm tool dropdown", () => {
  it("labels by tool name and subtitles by the tool's own description", async () => {
    // Regression: label and subtitle were both the function name, so every MCP,
    // Kiln-task, search and skill tool -- where the two match -- showed the same
    // string twice and dropped its real description.
    const { options } = await render_options([mcp_set])
    expect(options).toEqual([
      {
        value: "search_docs",
        label: "search_docs",
        description: "Search the docs",
        badge: "",
      },
    ])
  })

  it("shows the function name beside a tool whose display name differs", async () => {
    const { options } = await render_options([code_tool_set])
    expect(options).toEqual([
      {
        value: "word_count",
        label: "Word Count",
        description: "Count words in the output",
        badge: "word_count",
      },
    ])
  })

  it("selects the function name a trace records, not the tool id", async () => {
    const { options } = await render_options([code_tool_set, mcp_set])
    expect(options.map((option) => option.value)).toEqual([
      "word_count",
      "search_docs",
    ])
  })

  it("collapses every skill into one option", async () => {
    const { options, group_labels } = await render_options([mcp_set, skill_set])
    expect(options.map((option) => option.value)).toEqual([
      "search_docs",
      "skill",
    ])
    expect(group_labels).toEqual(["MCP Server: demo", "Skills"])
  })

  it("offers the skill option in a project that has only skills", async () => {
    const { options } = await render_options([skill_set])
    expect(options.map((option) => option.value)).toEqual(["skill"])
  })

  it("excludes sandbox-only tools, which can never appear in a trace", async () => {
    const { options } = await render_options([ai_models_set, mcp_set])
    expect(options.map((option) => option.value)).toEqual(["search_docs"])
  })

  it("keeps a saved tool name the project no longer offers", async () => {
    const { options, group_labels } = await render_options(
      [mcp_set],
      ["deleted_tool"],
    )
    expect(options.map((option) => option.value)).toEqual([
      "search_docs",
      "deleted_tool",
    ])
    expect(group_labels).toEqual(["MCP Server: demo", "Other"])
  })

  it("does not treat a known tool as a custom value", async () => {
    const { group_labels } = await render_options([mcp_set], ["search_docs"])
    expect(group_labels).toEqual(["MCP Server: demo"])
  })
})
