// @vitest-environment jsdom
import { describe, it, expect, vi, beforeAll } from "vitest"
import { render, fireEvent } from "@testing-library/svelte"
import type { EvalOutputScore } from "$lib/types"

vi.mock("$lib/components/code_editor.svelte", async () => {
  const StubModule = await import("./__tests__/code_editor_stub.svelte")
  return { default: StubModule.default }
})

vi.mock("$lib/ui/dialog.svelte", async () => {
  const StubModule = await import("./__tests__/dialog_stub.svelte")
  return { default: StubModule.default }
})

const CodeEvalForm = (await import("./code_eval_form.svelte")).default

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

  it("displays the Beta badge", () => {
    const { container } = render(CodeEvalForm)
    const badge = container.querySelector(".badge")
    expect(badge?.textContent?.trim()).toBe("Beta")
  })

  it("displays the Score Function label", () => {
    const { container } = render(CodeEvalForm)
    expect(container.textContent).toContain("Score Function")
  })

  it("displays the See examples button", () => {
    const { container } = render(CodeEvalForm)
    const btn = container.querySelector("button.btn-ghost")
    expect(btn).not.toBeNull()
    expect(btn?.textContent).toContain("See examples")
  })

  it("displays the score function signature hint", () => {
    const { container } = render(CodeEvalForm)
    expect(container.textContent).toContain(
      "score(output, trace, reference_data, task_input)",
    )
  })

  it("displays updated helper text mentioning per-type ranges", () => {
    const { container } = render(CodeEvalForm)
    const text = container.textContent ?? ""
    expect(text).toContain("pass/fail uses 0.0")
    expect(text).toContain("five-star")
    expect(text).toContain("1.0–5.0")
  })

  it("renders the timeout input with default value of 30", () => {
    const { container } = render(CodeEvalForm)
    expect(container.textContent).toContain("Timeout (seconds)")
    expect(container.textContent).toContain(
      "Maximum time allowed for the score function to execute",
    )
  })

  it("produces default CodeEvalProperties with correct type and default code", () => {
    const { component } = render(CodeEvalForm)
    const props = component.getProperties()
    expect(props.type).toBe("code_eval")
    expect(props.code).toContain("def score(")
    expect(props.timeout_seconds).toBe(30)
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
    expect(props.code).toContain(
      "def score(output, trace, reference_data, task_input)",
    )
  })

  it("renders the examples dialog content", () => {
    const { container } = render(CodeEvalForm)
    const dialogStub = container.querySelector('[data-testid="dialog-stub"]')
    expect(dialogStub).not.toBeNull()
    expect(dialogStub?.getAttribute("data-title")).toBe("Code Eval Examples")
  })

  it("renders example tabs (Parse JSON, Check tool usage, Domain-specific grading)", () => {
    const { container } = render(CodeEvalForm)
    const tabs = container.querySelectorAll(".tab")
    expect(tabs.length).toBe(3)
    expect(tabs[0].textContent?.trim()).toBe("Parse JSON")
    expect(tabs[1].textContent?.trim()).toBe("Check tool usage")
    expect(tabs[2].textContent?.trim()).toBe("Domain-specific grading")
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

  it("Domain-specific grading handles empty expected gracefully", async () => {
    const { container } = render(CodeEvalForm)
    const tabs = container.querySelectorAll(".tab")
    await fireEvent.click(tabs[2])
    const domainCode = get_example_code(container)
    expect(domainCode).toContain("if expected else True")
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
