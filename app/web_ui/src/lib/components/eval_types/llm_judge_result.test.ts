// @vitest-environment jsdom
import { describe, it, expect, vi } from "vitest"
import { render } from "@testing-library/svelte"
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

import LlmJudgeResult from "./llm_judge_result.svelte"

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
})
