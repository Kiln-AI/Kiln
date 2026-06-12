// @vitest-environment jsdom
import { describe, it, expect } from "vitest"
import { render } from "@testing-library/svelte"
import CodeEvalResult from "./code_eval_result.svelte"
import type { EvalConfig } from "$lib/types"

function makeConfig(overrides: Record<string, unknown> = {}): EvalConfig {
  return {
    v: 1,
    name: "test",
    config_type: "v2",
    model_type: "eval_config",
    properties: {
      type: "code_eval",
      timeout_seconds: 30,
      ...overrides,
    },
  } as EvalConfig
}

describe("CodeEvalResult", () => {
  it("renders without errors", () => {
    const { container } = render(CodeEvalResult)
    expect(container).toBeTruthy()
  })

  it("shows Beta badge with correct styling", () => {
    const { container } = render(CodeEvalResult)
    const badge = container.querySelector(".badge-outline.badge-sm")
    expect(badge).toBeTruthy()
    expect(badge?.textContent).toContain("Beta")
  })

  it("does not show pass/fail badge (custom scores)", () => {
    const { container } = render(CodeEvalResult, {
      props: {
        scores: { accuracy: 0.5, completeness: 0.8 },
        eval_config: makeConfig(),
      },
    })
    expect(container.querySelector(".badge-success")).toBeFalsy()
    expect(container.querySelector(".badge-error")).toBeFalsy()
  })

  it("delegates skipped display to EvalResultScores", () => {
    const { container } = render(CodeEvalResult, {
      props: {
        skipped_reason: "timeout",
        skipped_detail: "Code execution timed out",
      },
    })
    expect(container.textContent).toContain("Skipped")
    expect(container.textContent).toContain("Code execution timed out")
  })

  it("shows timeout from config", () => {
    const { container } = render(CodeEvalResult, {
      props: {
        scores: { result: 1.0 },
        eval_config: makeConfig({ timeout_seconds: 60 }),
      },
    })
    expect(container.textContent).toContain("Timeout:")
    expect(container.textContent).toContain("60s")
  })

  it("shows scores via EvalResultScores", () => {
    const { container } = render(CodeEvalResult, {
      props: { scores: { accuracy: 0.75 } },
    })
    expect(container.textContent).toContain("accuracy:")
    expect(container.textContent).toContain("0.75")
  })
})
