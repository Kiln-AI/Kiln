import { describe, it, expect } from "vitest"
import { llm_judge_steps_derivable } from "./llm_judge_gate"
import type { Eval } from "$lib/types"

function make_eval(
  template: Eval["template"],
  template_properties: Eval["template_properties"] = null,
): Eval {
  return { template, template_properties } as Eval
}

describe("llm_judge_steps_derivable", () => {
  it("always derives for spec-backed evals", () => {
    expect(llm_judge_steps_derivable(make_eval(null), true)).toBe(true)
    expect(llm_judge_steps_derivable(null, true)).toBe(true)
  })

  it("derives for static-step and requirement templates without a spec", () => {
    for (const template of [
      "toxicity",
      "bias",
      "maliciousness",
      "factual_correctness",
      "jailbreak",
      "kiln_requirements",
      "rag",
    ] as const) {
      expect(llm_judge_steps_derivable(make_eval(template), false)).toBe(true)
    }
  })

  it("derives for kiln_issue only when issue_prompt is recorded", () => {
    expect(
      llm_judge_steps_derivable(
        make_eval("kiln_issue", { issue_prompt: "No clickbait" }),
        false,
      ),
    ).toBe(true)
    expect(llm_judge_steps_derivable(make_eval("kiln_issue"), false)).toBe(
      false,
    )
  })

  it("derives for tool_call only when tool_function_name is recorded", () => {
    expect(
      llm_judge_steps_derivable(
        make_eval("tool_call", { tool_function_name: "get_weather" }),
        false,
      ),
    ).toBe(true)
    expect(llm_judge_steps_derivable(make_eval("tool_call"), false)).toBe(false)
  })

  it("does not derive with no spec and no derivable template", () => {
    expect(llm_judge_steps_derivable(make_eval(null), false)).toBe(false)
    expect(
      llm_judge_steps_derivable(make_eval("desired_behaviour"), false),
    ).toBe(false)
    expect(llm_judge_steps_derivable(null, false)).toBe(false)
    expect(llm_judge_steps_derivable(undefined, false)).toBe(false)
  })
})
