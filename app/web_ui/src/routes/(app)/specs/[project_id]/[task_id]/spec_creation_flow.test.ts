import { describe, it, expect } from "vitest"
import {
  parseSpecWorkflow,
  implied_judge_for_spec_type,
  eval_template_for_spec_type,
  next_page_after_template,
  next_page_after_judge,
  copilot_supported,
  judge_only_builder_url,
  spec_builder_url,
  buildSpecDefinition,
} from "./spec_utils"
import {
  spec_field_configs,
  core_field_config,
} from "./select_template/spec_templates"
import type { SpecType } from "$lib/types"

const ALL_SPEC_TYPES = Object.keys(spec_field_configs) as SpecType[]

describe("parseSpecWorkflow", () => {
  it("returns pro only for an explicit pro param", () => {
    expect(parseSpecWorkflow("pro")).toBe("pro")
  })

  // Kiln Pro must never appear to someone who chose Manual, so anything that
  // isn't an explicit "pro" has to fall back to manual.
  it.each([["manual"], [null], [""], ["PRO"], ["garbage"]])(
    "falls back to manual for %s",
    (value) => {
      expect(parseSpecWorkflow(value)).toBe("manual")
    },
  )
})

describe("core field invariant", () => {
  // The non-LLM judge flow only shows the core field and saves every other field
  // from its template default. If a template ever lacks a core field, or has a
  // required field with no default, that flow would POST a spec the backend
  // property validators reject.
  it.each(ALL_SPEC_TYPES)(
    "%s has exactly one core field, and every other required field has a default",
    (spec_type) => {
      const fields = spec_field_configs[spec_type]
      const core_fields = fields.filter((field) => field.core)
      expect(core_fields).toHaveLength(1)

      const unfillable = fields.filter(
        (field) =>
          !field.core && field.required && field.default_value === undefined,
      )
      expect(unfillable).toEqual([])
    },
  )

  it.each(ALL_SPEC_TYPES)(
    "%s builds a non-empty definition from just its core field",
    (spec_type) => {
      // Spec.definition is min_length=1 on the backend. Reproduce what the spec
      // builder saves for a non-LLM judge: template defaults + the core field.
      const values: Record<string, string | null> = {}
      for (const field of spec_field_configs[spec_type]) {
        if (field.default_value !== undefined) {
          values[field.key] = field.default_value
        }
      }
      values[core_field_config(spec_type).key] = "The user's description."

      expect(buildSpecDefinition(spec_type, values).trim()).not.toBe("")
    },
  )
})

describe("implied_judge_for_spec_type", () => {
  it("pins tool call evals to the tool call check judge", () => {
    expect(implied_judge_for_spec_type("appropriate_tool_use")).toBe(
      "tool_call_check",
    )
  })

  it("pins every other template to an LLM judge", () => {
    const llm_judged = ALL_SPEC_TYPES.filter(
      (spec_type) => implied_judge_for_spec_type(spec_type) === "llm_judge",
    )
    expect(llm_judged).toContain("desired_behaviour")
    expect(llm_judged).toContain("issue")
    expect(llm_judged).toContain("reference_answer_accuracy")
    expect(llm_judged).toContain("toxicity")
    expect(llm_judged).not.toContain("appropriate_tool_use")
  })
})

describe("eval_template_for_spec_type", () => {
  it("maps the open behaviour templates", () => {
    expect(eval_template_for_spec_type("issue")).toBe("kiln_issue")
    expect(eval_template_for_spec_type("desired_behaviour")).toBe(
      "desired_behaviour",
    )
  })

  // The legacy "tool_call" template means a pre-spec LLM judge over the
  // trace; new tool evals are the template-less Tool Call Check judge, so
  // recording that template on them would conflate the two.
  it("never records the legacy tool_call template on new tool evals", () => {
    expect(eval_template_for_spec_type("appropriate_tool_use")).toBe(null)
  })
})

describe("next_page_after_template", () => {
  it("sends the open behaviour templates to the workflow screen (LLM implied)", () => {
    const url = next_page_after_template("p1", "t1", "issue")
    expect(url).toContain("/specs/p1/t1/select_workflow?")
    expect(url).toContain("type=issue")
    expect(url).toContain("judge=llm_judge")
  })

  it("sends rubric templates to the Pro-vs-Manual workflow screen", () => {
    const url = next_page_after_template("p1", "t1", "toxicity")
    expect(url).toContain("/specs/p1/t1/select_workflow?")
    expect(url).toContain("type=toxicity")
    expect(url).toContain("judge=llm_judge")
  })

  it("skips both pickers for tool call, prefilling the tool call judge", () => {
    const url = next_page_after_template("p1", "t1", "appropriate_tool_use")
    expect(url).toContain("/specs/p1/t1/spec_builder?")
    expect(url).toContain("type=appropriate_tool_use")
    expect(url).toContain("judge=tool_call_check")
    expect(url).toContain("workflow=manual")
  })

  // Kiln Pro doesn't support RAG specs, so the workflow screen is skipped.
  it("skips the workflow screen for reference answer, going manual", () => {
    const url = next_page_after_template(
      "p1",
      "t1",
      "reference_answer_accuracy",
    )
    expect(url).toContain("/specs/p1/t1/spec_builder?")
    expect(url).toContain("judge=llm_judge")
    expect(url).toContain("workflow=manual")
  })
})

describe("next_page_after_judge", () => {
  it("sends copilot-eligible combos to the workflow screen", () => {
    const url = next_page_after_judge("p1", "t1", "issue", "llm_judge")
    expect(url).toContain("/specs/p1/t1/select_workflow?")
    expect(url).toContain("type=issue")
    expect(url).toContain("judge=llm_judge")
  })

  it("sends non-LLM judges straight to the manual builder", () => {
    const url = next_page_after_judge("p1", "t1", "issue", "code_eval")
    expect(url).toContain("/specs/p1/t1/spec_builder?")
    expect(url).toContain("judge=code_eval")
    expect(url).toContain("workflow=manual")
  })
})

describe("copilot_supported", () => {
  it("requires an LLM judge", () => {
    expect(copilot_supported("issue", "llm_judge")).toBe(true)
    expect(copilot_supported("issue", "code_eval")).toBe(false)
    expect(copilot_supported("issue", "exact_match")).toBe(false)
  })

  it("excludes tool call and RAG spec types", () => {
    expect(copilot_supported("appropriate_tool_use", "llm_judge")).toBe(false)
    expect(copilot_supported("reference_answer_accuracy", "llm_judge")).toBe(
      false,
    )
    expect(copilot_supported("toxicity", "llm_judge")).toBe(true)
  })
})

describe("judge_only_builder_url", () => {
  it("routes to the spec builder with judge and manual workflow, no type", () => {
    const url = new URL(
      judge_only_builder_url("p1", "t1", "code_eval"),
      "http://localhost",
    )
    expect(url.pathname).toBe("/specs/p1/t1/spec_builder")
    expect(url.searchParams.get("judge")).toBe("code_eval")
    expect(url.searchParams.get("workflow")).toBe("manual")
    expect(url.searchParams.get("type")).toBeNull()
  })
})

describe("spec_builder_url", () => {
  it("encodes the template, workflow, and judge", () => {
    const url = new URL(
      spec_builder_url("p1", "t1", "issue", "manual", "pattern_match"),
      "http://localhost",
    )
    expect(url.pathname).toBe("/specs/p1/t1/spec_builder")
    expect(url.searchParams.get("type")).toBe("issue")
    expect(url.searchParams.get("workflow")).toBe("manual")
    expect(url.searchParams.get("judge")).toBe("pattern_match")
  })
})
