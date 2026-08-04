import { describe, it, expect } from "vitest"
import { eval_type_display, judge_type_from_config } from "./eval_type_display"
import type { Eval, Spec } from "$lib/types"

function make_spec(spec_type: string): Spec {
  return { properties: { spec_type } } as Spec
}

function make_eval(template: Eval["template"]): Eval {
  return { template } as Eval
}

describe("eval_type_display", () => {
  it("shows the judge label for programmatic default judges", () => {
    expect(eval_type_display(null, make_eval(null), "code_eval")).toBe("Code")
    expect(eval_type_display(null, make_eval("kiln_issue"), "code_eval")).toBe(
      "Code",
    )
    expect(eval_type_display(null, make_eval(null), "exact_match")).toBe(
      "Exact Match",
    )
    expect(
      eval_type_display(
        make_spec("appropriate_tool_use"),
        null,
        "tool_call_check",
      ),
    ).toBe("Tool Call Check")
  })

  it("shows LLM with the spec flavor for LLM-judged spec evals", () => {
    expect(eval_type_display(make_spec("toxicity"), null, "llm_judge")).toBe(
      "LLM (Toxicity)",
    )
    // Spec-backed evals are never legacy, even with a V1 judge config.
    expect(eval_type_display(make_spec("issue"), null, "g_eval")).toBe(
      "LLM (Issue)",
    )
  })

  it("shows LLM with the template flavor for spec-less v2 LLM evals", () => {
    expect(eval_type_display(null, make_eval("kiln_issue"), "llm_judge")).toBe(
      "LLM (Issue)",
    )
  })

  it("marks true legacy evals with a Legacy prefix", () => {
    // No spec + V1 judge config type = pre-spec eval.
    expect(eval_type_display(null, make_eval("bias"), "llm_as_judge")).toBe(
      "Legacy LLM (Bias)",
    )
    expect(eval_type_display(null, make_eval("toxicity"), "g_eval")).toBe(
      "Legacy LLM (Toxicity)",
    )
    // Legacy custom-goal evals: no template, V1 judge.
    expect(eval_type_display(null, make_eval(null), "g_eval")).toBe(
      "Legacy LLM",
    )
    // No spec + template + no default judge: only the old system left evals
    // in this state (the current flows always set a judge at creation).
    expect(eval_type_display(null, make_eval("bias"), null)).toBe(
      "Legacy LLM (Bias)",
    )
  })

  it("shows plain LLM when there is no spec or template", () => {
    expect(eval_type_display(null, make_eval(null), "llm_judge")).toBe("LLM")
  })

  it("falls back to the implied judge when no default judge is set", () => {
    expect(eval_type_display(make_spec("toxicity"), null, null)).toBe(
      "LLM (Toxicity)",
    )
    expect(
      eval_type_display(make_spec("appropriate_tool_use"), null, null),
    ).toBe("Tool Call Check")
  })

  it("shows None for programmatic evals with no default judge", () => {
    expect(eval_type_display(null, make_eval(null), null)).toBe("None")
    expect(eval_type_display(null, null, null)).toBe("None")
  })
})

describe("judge_type_from_config", () => {
  it("uses the v2 properties type when present", () => {
    expect(
      judge_type_from_config({
        config_type: "v2",
        properties: { type: "code_eval" },
      }),
    ).toBe("code_eval")
  })

  it("falls back to config_type for legacy configs", () => {
    expect(
      judge_type_from_config({ config_type: "g_eval", properties: {} }),
    ).toBe("g_eval")
  })

  it("returns null for missing configs", () => {
    expect(judge_type_from_config(null)).toBeNull()
    expect(judge_type_from_config(undefined)).toBeNull()
  })
})
