import { describe, it, expect } from "vitest"
import {
  parseSpecWorkflow,
  implied_judge_for_spec_type,
  eval_template_for_spec_type,
  next_page_after_template,
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

  it("only leaves the judge open for desired behaviour and issue", () => {
    const open = ALL_SPEC_TYPES.filter(
      (spec_type) => implied_judge_for_spec_type(spec_type) === null,
    )
    expect(open.sort()).toEqual(["desired_behaviour", "issue"])
  })

  it("pins every other template to an LLM judge", () => {
    const llm_judged = ALL_SPEC_TYPES.filter(
      (spec_type) => implied_judge_for_spec_type(spec_type) === "llm_judge",
    )
    expect(llm_judged).toContain("reference_answer_accuracy")
    expect(llm_judged).toContain("toxicity")
    expect(llm_judged).not.toContain("appropriate_tool_use")
  })
})

describe("eval_template_for_spec_type", () => {
  // Spec-less evals record their origin template. Every template that can
  // reach a non-LLM judge (and so save without a spec) must have a mapping.
  it("maps every template that can reach a non-LLM judge", () => {
    const non_llm_reachable = ALL_SPEC_TYPES.filter(
      (spec_type) => implied_judge_for_spec_type(spec_type) !== "llm_judge",
    )
    for (const spec_type of non_llm_reachable) {
      expect(eval_template_for_spec_type(spec_type)).not.toBeNull()
    }
    expect(eval_template_for_spec_type("issue")).toBe("kiln_issue")
    expect(eval_template_for_spec_type("desired_behaviour")).toBe(
      "desired_behaviour",
    )
    expect(eval_template_for_spec_type("appropriate_tool_use")).toBe(
      "tool_call",
    )
  })
})

describe("next_page_after_template", () => {
  it("sends open templates to the judge picker, carrying the workflow", () => {
    expect(next_page_after_template("p1", "t1", "issue", "pro")).toBe(
      "/specs/p1/t1/select_judge?type=issue&workflow=pro",
    )
  })

  it("skips the judge picker for rubric templates, going to the LLM judge form", () => {
    const url = next_page_after_template("p1", "t1", "toxicity", "manual")
    expect(url).toContain("/specs/p1/t1/spec_builder?")
    expect(url).toContain("type=toxicity")
    expect(url).toContain("judge=llm_judge")
    expect(url).toContain("workflow=manual")
  })

  it("skips the judge picker for tool call, prefilling the tool call judge", () => {
    const url = next_page_after_template(
      "p1",
      "t1",
      "appropriate_tool_use",
      "manual",
    )
    expect(url).toContain("/specs/p1/t1/spec_builder?")
    expect(url).toContain("type=appropriate_tool_use")
    expect(url).toContain("judge=tool_call_check")
    expect(url).toContain("workflow=manual")
  })

  it("skips the judge picker for reference answer, going to the LLM judge form", () => {
    const url = next_page_after_template(
      "p1",
      "t1",
      "reference_answer_accuracy",
      "pro",
    )
    expect(url).toContain("/specs/p1/t1/spec_builder?")
    expect(url).toContain("judge=llm_judge")
    expect(url).toContain("workflow=pro")
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
