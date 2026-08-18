// @vitest-environment jsdom
import { describe, it, expect, vi, beforeAll } from "vitest"
import { render, fireEvent } from "@testing-library/svelte"
import { tick } from "svelte"
import type { EvalOutputScore } from "$lib/types"
import { LLM_JUDGE_TOOL_ID, LLM_TOOL_ID } from "$lib/utils/built_in_tool_ids"

vi.mock("$lib/components/code_editor.svelte", async () => {
  const StubModule = await import("./__tests__/code_editor_stub.svelte")
  return { default: StubModule.default }
})

vi.mock("$lib/ui/dialog.svelte", async () => {
  const StubModule = await import("./__tests__/dialog_stub.svelte")
  return { default: StubModule.default }
})

vi.mock("$lib/utils/form_element.svelte", async () => {
  const StubModule = await import("./__tests__/form_element_stub.svelte")
  return { default: StubModule.default }
})

vi.mock("$lib/ui/run_config_component/tools_selector.svelte", async () => {
  const StubModule = await import("./__tests__/tools_selector_stub.svelte")
  return { default: StubModule.default }
})

const CodeEvalForm = (await import("./code_eval_form.svelte")).default
const { actionButtonsByTitle } = await import("./__tests__/dialog_stub.svelte")

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

function make_score(
  name: string,
  type: EvalOutputScore["type"],
): EvalOutputScore {
  return { name, type, instruction: null }
}

describe("CodeEvalForm", () => {
  it("renders without errors", () => {
    const { container } = render(CodeEvalForm)
    expect(container).toBeTruthy()
  })

  it("does not display a standalone Beta badge (consolidated into intro)", () => {
    const { container } = render(CodeEvalForm)
    const badge = container.querySelector(".badge")
    expect(badge).toBeNull()
  })

  it("renders Score Function as a header_only FormElement", () => {
    const { container } = render(CodeEvalForm)
    const el = container.querySelector(
      '[data-testid="form-element-code_eval_score_function"]',
    )
    expect(el).not.toBeNull()
    expect(el?.getAttribute("data-label")).toBe("Score Function")
    expect(el?.getAttribute("data-type")).toBe("header_only")
  })

  it("Score Function FormElement has subtitle description", () => {
    const { container } = render(CodeEvalForm)
    const el = container.querySelector(
      '[data-testid="form-element-code_eval_score_function"]',
    )
    expect(el?.getAttribute("data-description")).toBe(
      "Define a Python score function to evaluate the model's work.",
    )
  })

  it("Score Function FormElement has info_description tooltip", () => {
    const { container } = render(CodeEvalForm)
    const el = container.querySelector(
      '[data-testid="form-element-code_eval_score_function"]',
    )
    expect(el?.getAttribute("data-info-description")).toContain(
      "pragmatic scoring",
    )
  })

  it("Score Function info_description does not mention reference data", () => {
    const { container } = render(CodeEvalForm)
    const el = container.querySelector(
      '[data-testid="form-element-code_eval_score_function"]',
    )
    expect(el?.getAttribute("data-info-description")).toBe(
      "The Python function can use the model's output and trace to drive pragmatic scoring. Faster and cheaper than LLM as a judge.",
    )
  })

  it("Score Function FormElement has Examples inline action", () => {
    const { container } = render(CodeEvalForm)
    const el = container.querySelector(
      '[data-testid="form-element-code_eval_score_function"]',
    )
    expect(el?.getAttribute("data-inline-action-label")).toBe("Examples")
  })

  it("does not display the footer paragraph with range hints", () => {
    const { container } = render(CodeEvalForm)
    expect(container.textContent).not.toContain("pass/fail uses 0.0")
    expect(container.textContent).not.toContain("five-star uses 1.0")
    expect(container.textContent).not.toContain(
      "function that returns a dict of score names",
    )
  })

  it("renders the timeout FormElement", () => {
    const { container } = render(CodeEvalForm)
    const el = container.querySelector(
      '[data-testid="form-element-code_eval_timeout"]',
    )
    expect(el).not.toBeNull()
    expect(el?.getAttribute("data-label")).toBe("Timeout (seconds)")
    expect(el?.getAttribute("data-description")).toContain(
      "Maximum time allowed for the score function to execute",
    )
  })

  it("produces default CodeEvalProperties with correct type and default code", () => {
    const { component } = render(CodeEvalForm)
    const props = component.getProperties()
    expect(props.type).toBe("code_eval")
    expect(props.code).toContain("def score(")
    // Default raised to 180s to accommodate nested LLM tool latency.
    expect(props.timeout_seconds).toBe(180)
  })

  it("produces CodeEvalProperties with updated timeout", async () => {
    const { component, container } = render(CodeEvalForm)

    const input = container.querySelector(
      'input[type="number"]',
    ) as HTMLInputElement
    if (input) {
      await fireEvent.input(input, { target: { value: "60" } })
    }

    const props = component.getProperties()
    expect(props.type).toBe("code_eval")
  })

  it("getProperties always returns type code_eval", () => {
    const { component } = render(CodeEvalForm)
    const props = component.getProperties()
    expect(props.type).toBe("code_eval")
    expect(typeof props.code).toBe("string")
    expect(props.code.length).toBeGreaterThan(0)
  })

  it("accepts initial properties via props", () => {
    const customProps = {
      type: "code_eval" as const,
      code: 'def score(output, trace, reference_data, task_input):\n    return {"custom": 0.5}\n',
      reference_keys: [] as string[],
      timeout_seconds: 120,
    }
    const { component } = render(CodeEvalForm, {
      props: { properties: customProps },
    })
    const props = component.getProperties()
    expect(props.type).toBe("code_eval")
    expect(props.code).toContain("custom")
    expect(props.timeout_seconds).toBe(120)
  })

  it("default code contains the expected function signature", () => {
    const { component } = render(CodeEvalForm)
    const props = component.getProperties()
    expect(props.code).toContain("def score(output, trace, task_input)")
    expect(props.code).not.toContain("reference_data")
  })

  it("renders the examples dialog content", () => {
    const { container } = render(CodeEvalForm)
    const dialogStub = container.querySelector('[data-testid="dialog-stub"]')
    expect(dialogStub).not.toBeNull()
    expect(dialogStub?.getAttribute("data-title")).toBe("Code Judge Examples")
  })

  it("renders example tabs including the LLM tool examples", () => {
    const { container } = render(CodeEvalForm)
    const tabs = container.querySelectorAll(".tab")
    expect(tabs.length).toBe(5)
    expect(tabs[0].textContent?.trim()).toBe("Parse JSON")
    expect(tabs[1].textContent?.trim()).toBe("Check tool usage")
    expect(tabs[2].textContent?.trim()).toBe("Domain-specific grading")
    expect(tabs[3].textContent?.trim()).toBe("LLM judge")
    expect(tabs[4].textContent?.trim()).toBe("Triage then LLM judge")
  })

  it("switches active example tab on click", async () => {
    const { container } = render(CodeEvalForm)
    const tabs = container.querySelectorAll(".tab")

    expect(tabs[0].classList.contains("tab-active")).toBe(true)
    expect(tabs[1].classList.contains("tab-active")).toBe(false)

    await fireEvent.click(tabs[1])

    expect(tabs[0].classList.contains("tab-active")).toBe(false)
    expect(tabs[1].classList.contains("tab-active")).toBe(true)
  })

  it("renders code editor stub with default code", () => {
    const { container } = render(CodeEvalForm)
    const editorStub = container.querySelector(
      '[data-testid="code-editor-stub"]',
    )
    expect(editorStub).not.toBeNull()
  })
})

describe("tool allowlist picker", () => {
  it("renders the ToolsSelector in code-eval context", () => {
    const { container } = render(CodeEvalForm, {
      props: { project_id: "proj_123" },
    })
    const selector = container.querySelector(
      '[data-testid="tools-selector-stub"]',
    )
    expect(selector).not.toBeNull()
    expect(selector?.getAttribute("data-project-id")).toBe("proj_123")
    // The code-eval context is what makes llm_judge offerable here.
    expect(selector?.getAttribute("data-sandbox-code-context")).toBe(
      "code_eval",
    )
  })

  it("binds the picker to properties.tool_allowlist", () => {
    const customProps = {
      type: "code_eval" as const,
      code: 'def score(output):\n    return {"quality": 1.0}\n',
      reference_keys: [] as string[],
      timeout_seconds: 180,
      tool_allowlist: ["kiln_tool::llm"],
    }
    const { container } = render(CodeEvalForm, {
      props: { properties: customProps },
    })
    const selector = container.querySelector(
      '[data-testid="tools-selector-stub"]',
    )
    expect(JSON.parse(selector?.getAttribute("data-tools") ?? "[]")).toEqual([
      "kiln_tool::llm",
    ])
  })

  it("selecting a tool flows back into getProperties().tool_allowlist", async () => {
    const { component, container } = render(CodeEvalForm)
    const add_button = container.querySelector(
      '[data-testid="tools-selector-add"]',
    ) as HTMLButtonElement
    await fireEvent.click(add_button)
    const props = component.getProperties()
    expect(props.tool_allowlist).toEqual(["kiln_tool::llm_judge"])
  })
})

describe("examples grant the tools they call", () => {
  // Drives the real dialog action the "Use This Example" button is wired to.
  async function use_example(container: HTMLElement, tab_index: number) {
    const tabs = container.querySelectorAll(".tab")
    await fireEvent.click(tabs[tab_index])
    const buttons = actionButtonsByTitle["Code Judge Examples"]
    const use_button = buttons.find((b) => b.label === "Use This Example")
    expect(use_button).toBeTruthy()
    ;(use_button?.action as () => boolean)()
    await tick()
  }

  const LLM_JUDGE_TAB = 3
  const TRIAGE_TAB = 4
  const PARSE_JSON_TAB = 0

  it("grants llm_judge for the LLM judge example", async () => {
    const { component, container } = render(CodeEvalForm)
    await use_example(container, LLM_JUDGE_TAB)
    const props = component.getProperties()
    expect(props.code).toContain("tools.llm_judge(")
    expect(props.tool_allowlist).toEqual([LLM_JUDGE_TOOL_ID])
  })

  it("grants both llm and llm_judge for the triage example", async () => {
    const { component, container } = render(CodeEvalForm)
    await use_example(container, TRIAGE_TAB)
    const props = component.getProperties()
    expect(props.code).toContain("tools.llm(")
    expect(props.code).toContain("tools.llm_judge(")
    expect(props.tool_allowlist).toEqual([LLM_TOOL_ID, LLM_JUDGE_TOOL_ID])
  })

  it("grants nothing extra for an example that calls no tools", async () => {
    const { component, container } = render(CodeEvalForm, {
      props: {
        properties: {
          type: "code_eval" as const,
          code: "def score(output):\n    return {}\n",
          reference_keys: [] as string[],
          timeout_seconds: 180,
          tool_allowlist: ["mcp::remote::demo::search"],
        },
      },
    })
    await use_example(container, PARSE_JSON_TAB)
    const props = component.getProperties()
    expect(props.code).toContain("json.loads(output)")
    // Unchanged: no spurious grant, and the user's own pick is left alone.
    expect(props.tool_allowlist).toEqual(["mcp::remote::demo::search"])
  })

  it("adds to, rather than replaces, tools the user already selected", async () => {
    const { component, container } = render(CodeEvalForm, {
      props: {
        properties: {
          type: "code_eval" as const,
          code: "def score(output):\n    return {}\n",
          reference_keys: [] as string[],
          timeout_seconds: 180,
          tool_allowlist: ["mcp::remote::demo::search"],
        },
      },
    })
    await use_example(container, LLM_JUDGE_TAB)
    const props = component.getProperties()
    expect(props.tool_allowlist).toEqual([
      "mcp::remote::demo::search",
      LLM_JUDGE_TOOL_ID,
    ])
  })

  it("is idempotent when the same example is used twice", async () => {
    const { component, container } = render(CodeEvalForm)
    await use_example(container, TRIAGE_TAB)
    await use_example(container, TRIAGE_TAB)
    const props = component.getProperties()
    expect(props.tool_allowlist).toEqual([LLM_TOOL_ID, LLM_JUDGE_TOOL_ID])
  })
})

describe("dynamic default code via output_scores prop", () => {
  it("uses output_scores to generate the initial code", () => {
    const scores = [make_score("Relevance", "five_star")]
    const { component } = render(CodeEvalForm, {
      props: { output_scores: scores },
    })
    const props = component.getProperties()
    expect(props.code).toContain('"relevance"')
    expect(props.code).toContain("5.0")
    expect(props.code).not.toContain('"quality"')
  })

  it("falls back to generic code when output_scores is undefined", () => {
    const { component } = render(CodeEvalForm)
    const props = component.getProperties()
    expect(props.code).toContain('"quality"')
  })
})

describe("example code correctness", () => {
  function get_example_code(container: HTMLElement): string {
    return container.querySelector(".whitespace-pre")?.textContent ?? ""
  }

  it("Domain-specific grading uses KilnEvalHelpers.pass_fail with assert_contains result", async () => {
    const { container } = render(CodeEvalForm)
    const tabs = container.querySelectorAll(".tab")
    await fireEvent.click(tabs[2])
    const domainCode = get_example_code(container)
    expect(domainCode).toContain("KilnEvalHelpers.pass_fail(contains)")
  })

  it("Domain-specific grading asserts against a literal marker", async () => {
    const { container } = render(CodeEvalForm)
    const tabs = container.querySelectorAll(".tab")
    await fireEvent.click(tabs[2])
    const domainCode = get_example_code(container)
    expect(domainCode).toContain(
      'contains = KilnEvalHelpers.assert_contains(output, "Summary:")',
    )
    expect(domainCode).not.toContain("if expected else True")
  })

  it("no example mentions reference data", async () => {
    const { container } = render(CodeEvalForm)
    const tabs = container.querySelectorAll(".tab")
    for (let i = 0; i < tabs.length; i++) {
      await fireEvent.click(tabs[i])
      expect(get_example_code(container)).not.toContain("reference_data")
    }
  })

  it("Check tool usage example clamps five_star lower bound to 1", async () => {
    const scores = [make_score("Rating", "five_star")]
    const { container } = render(CodeEvalForm, {
      props: { output_scores: scores },
    })
    const tabs = container.querySelectorAll(".tab")
    await fireEvent.click(tabs[1])
    const toolCode = get_example_code(container)
    expect(toolCode).toContain("max(min(call_count, 5), 1)")
  })

  it("Parse JSON example uses KilnEvalHelpers.pass_fail(passed)", () => {
    const { container } = render(CodeEvalForm)
    const parseCode = get_example_code(container)
    expect(parseCode).toContain("KilnEvalHelpers.pass_fail(passed)")
  })

  it("examples use fallback quality key when no output_scores", () => {
    const { container } = render(CodeEvalForm)
    const parseCode = get_example_code(container)
    expect(parseCode).toContain('"quality"')
  })

  it("examples use real score keys from output_scores", async () => {
    const scores = [
      make_score("Accuracy", "pass_fail"),
      make_score("Depth", "five_star"),
    ]
    const { container } = render(CodeEvalForm, {
      props: { output_scores: scores },
    })
    const parseCode = get_example_code(container)
    expect(parseCode).toContain('"accuracy"')
    expect(parseCode).toContain('"depth"')
    expect(parseCode).not.toContain('"quality"')
  })
})
