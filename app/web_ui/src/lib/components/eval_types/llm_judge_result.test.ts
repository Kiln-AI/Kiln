// @vitest-environment jsdom
import { describe, it, expect, vi } from "vitest"
import { render, fireEvent } from "@testing-library/svelte"
import type { EvalConfig } from "$lib/types"

vi.mock("$lib/stores", async () => {
  const { writable } = await import("svelte/store")
  return {
    model_info: writable(null),
    model_name: (id: string | undefined) => {
      if (!id) return "Unknown"
      return "Model ID: " + id
    },
  }
})

vi.mock("$lib/ui/dialog.svelte", async () => {
  const StubModule = await import("./__tests__/dialog_stub.svelte")
  return { default: StubModule.default }
})

const LlmJudgeResult = (await import("./llm_judge_result.svelte")).default

function makeConfig(overrides: Record<string, unknown> = {}): EvalConfig {
  return {
    v: 1,
    name: "test",
    config_type: "v2",
    model_type: "eval_config",
    properties: {
      type: "llm_judge",
      model_name: "gpt-4o",
      model_provider: "openai",
      g_eval: false,
      ...overrides,
    },
  } as EvalConfig
}

describe("LlmJudgeResult", () => {
  it("renders without errors", () => {
    const { container } = render(LlmJudgeResult)
    expect(container).toBeTruthy()
  })

  it("does not show pass/fail badge (float scores)", () => {
    const { container } = render(LlmJudgeResult, {
      props: { scores: { quality: 0.75 }, eval_config: makeConfig() },
    })
    expect(container.querySelector(".badge-success")).toBeFalsy()
    expect(container.querySelector(".badge-error")).toBeFalsy()
  })

  it("delegates skipped display to EvalResultScores", () => {
    const { container } = render(LlmJudgeResult, {
      props: {
        skipped_reason: "error",
        skipped_detail: "Model unavailable",
      },
    })
    expect(container.textContent).toContain("Skipped")
    expect(container.textContent).toContain("Model unavailable")
  })

  it("shows model name from config", () => {
    const { container } = render(LlmJudgeResult, {
      props: {
        scores: { quality: 0.8 },
        eval_config: makeConfig({ model_name: "gpt-4o" }),
      },
    })
    expect(container.textContent).toContain("Model:")
    expect(container.textContent).toContain("Model ID: gpt-4o")
  })

  it("shows G-Eval badge and label when g_eval is true", () => {
    const { container } = render(LlmJudgeResult, {
      props: {
        scores: { quality: 0.9 },
        eval_config: makeConfig({ g_eval: true }),
      },
    })
    expect(container.textContent).toContain("G-Eval")
    expect(container.textContent).toContain("Chain-of-thought scoring")
    expect(container.querySelector(".badge-outline")).toBeTruthy()
  })

  it("does not show G-Eval badge when g_eval is false", () => {
    const { container } = render(LlmJudgeResult, {
      props: {
        scores: { quality: 0.9 },
        eval_config: makeConfig({ g_eval: false }),
      },
    })
    expect(container.textContent).not.toContain("G-Eval")
    expect(container.textContent).not.toContain("Chain-of-thought scoring")
  })

  it("shows scores via EvalResultScores", () => {
    const { container } = render(LlmJudgeResult, {
      props: { scores: { quality: 0.85 } },
    })
    expect(container.textContent).toContain("quality:")
    expect(container.textContent).toContain("0.85")
  })

  it("does not show config details when eval_config is null", () => {
    const { container } = render(LlmJudgeResult, {
      props: { scores: { quality: 0.9 } },
    })
    expect(container.textContent).toContain("quality:")
    expect(container.textContent).not.toContain("Model:")
    expect(container.textContent).not.toContain("G-Eval")
    expect(container.textContent).not.toContain("Chain-of-thought")
  })

  it("shows View reasoning link when reasoning is present via reasoning key", () => {
    const { container } = render(LlmJudgeResult, {
      props: {
        scores: { quality: 0.8 },
        eval_config: makeConfig(),
        intermediate_outputs: { reasoning: "The model output was good." },
      },
    })
    expect(container.textContent).toContain("View reasoning")
  })

  it("shows View reasoning link when reasoning is present via chain_of_thought key", () => {
    const { container } = render(LlmJudgeResult, {
      props: {
        scores: { quality: 0.8 },
        eval_config: makeConfig(),
        intermediate_outputs: {
          chain_of_thought: "Step 1: Check grammar.",
        },
      },
    })
    expect(container.textContent).toContain("View reasoning")
  })

  it("hides View reasoning when intermediate_outputs is null", () => {
    const { container } = render(LlmJudgeResult, {
      props: {
        scores: { quality: 0.8 },
        eval_config: makeConfig(),
        intermediate_outputs: null,
      },
    })
    expect(container.textContent).not.toContain("View reasoning")
  })

  it("hides View reasoning when intermediate_outputs has no reasoning keys", () => {
    const { container } = render(LlmJudgeResult, {
      props: {
        scores: { quality: 0.8 },
        eval_config: makeConfig(),
        intermediate_outputs: { some_other_key: "value" },
      },
    })
    expect(container.textContent).not.toContain("View reasoning")
  })

  it("opens dialog when View reasoning is clicked", async () => {
    const { container } = render(LlmJudgeResult, {
      props: {
        scores: { quality: 0.8 },
        eval_config: makeConfig(),
        intermediate_outputs: { reasoning: "The model output was good." },
      },
    })

    const link = container.querySelector("button.link")
    expect(link).toBeTruthy()
    expect(link!.textContent).toContain("View reasoning")

    await fireEvent.click(link!)

    const dialog = container.querySelector('[data-testid="dialog-stub"]')
    expect(dialog).toBeTruthy()
    expect(dialog!.getAttribute("data-title")).toBe("Judge Reasoning")
    expect(dialog!.textContent).toContain("The model output was good.")
  })

  it("shows View reasoning even without eval_config (fallback path)", () => {
    const { container } = render(LlmJudgeResult, {
      props: {
        scores: { quality: 0.8 },
        eval_config: null,
        intermediate_outputs: { reasoning: "Some reasoning text" },
      },
    })
    expect(container.textContent).toContain("View reasoning")
  })
})
