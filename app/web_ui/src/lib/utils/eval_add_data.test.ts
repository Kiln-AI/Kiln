import { describe, it, expect } from "vitest"
import type { Eval, Spec, ToolSetApiDescription } from "$lib/types"
import {
  EVAL_INPUT_TEST_SPLIT_MESSAGE,
  MISSING_TAG_MESSAGE,
  eval_add_data_link,
  eval_id_from_param,
  plan_eval_add_data,
  type EvalAddDataInput,
} from "./eval_add_data"

function make_eval(fields: Partial<Eval>): Eval {
  return {
    id: "e1",
    name: "Eval",
    output_scores: [],
    eval_set_filter_id: null,
    eval_configs_filter_id: "tag::golden_tag",
    splits: {
      train: { source: "task_run", filter_id: "tag::train_tag" },
      val: { source: "task_run", filter_id: "tag::val_tag" },
      test: { source: "task_run", filter_id: "tag::test_tag" },
    },
    ...fields,
  } as Eval
}

function make_input(fields: Partial<EvalAddDataInput>): EvalAddDataInput {
  return {
    project_id: "p1",
    task_id: "t1",
    evaluator: make_eval({}),
    spec: null,
    judge_properties: null,
    tool_sets: [],
    ...fields,
  }
}

function ready(input: EvalAddDataInput) {
  const plan = plan_eval_add_data(input)
  if (plan.kind !== "ready") {
    throw new Error(`expected a ready plan, got: ${plan.message}`)
  }
  return plan
}

describe("eval_add_data_link", () => {
  it("names only the reason and the eval", () => {
    expect(eval_add_data_link("p1", "t1", "e1")).toBe(
      "/dataset/p1/t1/add_data?reason=eval&eval_id=e1",
    )
  })
})

describe("eval_id_from_param", () => {
  it("accepts a plain eval id", () => {
    expect(eval_id_from_param("e1", "p1", "t1")).toBe("e1")
  })

  it("accepts the full id of an eval of this task", () => {
    expect(eval_id_from_param("p1::t1::e1", "p1", "t1")).toBe("e1")
  })

  it("rejects the full id of another task's eval", () => {
    expect(eval_id_from_param("p1::t2::e1", "p1", "t1")).toBeUndefined()
  })

  it("rejects an empty or missing param", () => {
    expect(eval_id_from_param(null, "p1", "t1")).toBeUndefined()
    expect(eval_id_from_param("", "p1", "t1")).toBeUndefined()
  })
})

describe("plan_eval_add_data", () => {
  it("allocates across all four tags and forwards the full eval id", () => {
    const plan = ready(make_input({}))
    expect(plan.splits).toEqual({
      train_tag: 0.4,
      val_tag: 0.25,
      test_tag: 0.25,
      golden_tag: 0.1,
    })
    expect(plan.splits_param).toBe(
      "train_tag:0.4,val_tag:0.25,test_tag:0.25,golden_tag:0.1",
    )
    expect(plan.full_eval_id).toBe("p1::t1::e1")
    expect(plan.template_id).toBeNull()
    expect(plan.tool_id).toBeNull()
  })

  it("links back through the spec that points at the eval", () => {
    const spec = { id: "s1", eval_id: "e1" } as Spec
    expect(ready(make_input({ spec })).eval_link).toBe("/specs/p1/t1/s1/e1")
  })

  it("links back through legacy for an eval with no spec", () => {
    expect(ready(make_input({})).eval_link).toBe("/specs/p1/t1/legacy/e1")
  })

  it("refuses an eval whose test split holds eval inputs", () => {
    const evaluator = make_eval({
      splits: { test: { source: "eval_input", filter_id: "tag::test_tag" } },
    })
    const plan = plan_eval_add_data(make_input({ evaluator }))
    expect(plan).toEqual({
      kind: "refused",
      message: EVAL_INPUT_TEST_SPLIT_MESSAGE,
      eval_link: "/specs/p1/t1/legacy/e1",
    })
  })

  it("refuses an eval with no test tag", () => {
    const evaluator = make_eval({
      splits: { test: { source: "task_run", filter_id: "high_rating" } },
    })
    const plan = plan_eval_add_data(make_input({ evaluator }))
    expect(plan.kind === "refused" && plan.message).toBe(MISSING_TAG_MESSAGE)
  })

  it("refuses a non-rag eval with no golden tag", () => {
    const evaluator = make_eval({ eval_configs_filter_id: null })
    const plan = plan_eval_add_data(make_input({ evaluator }))
    expect(plan.kind === "refused" && plan.message).toBe(MISSING_TAG_MESSAGE)
  })

  it("accepts a rag eval with no golden tag, and keeps the template", () => {
    const evaluator = make_eval({
      template: "rag",
      eval_configs_filter_id: null,
    })
    const plan = ready(make_input({ evaluator }))
    expect(plan.template_id).toBe("rag")
    expect(Object.keys(plan.splits)).not.toContain("golden_tag")
  })

  it("sends a test-only rag eval's whole allocation to test, past its golden tag", () => {
    // The rag flow has no human-ratings step, so a share dealt to golden would land in a
    // tag nothing reads.
    const evaluator = make_eval({
      template: "rag",
      eval_set_filter_id: "tag::test_x",
      eval_configs_filter_id: "tag::golden_x",
      splits: {},
    })
    expect(ready(make_input({ evaluator })).splits_param).toBe("test_x:1")
  })

  it("takes the tool of an appropriate_tool_use spec", () => {
    const evaluator = make_eval({ template: "tool_call" })
    const spec = {
      id: "s1",
      eval_id: "e1",
      properties: { spec_type: "appropriate_tool_use", tool_id: "tool_a" },
    } as unknown as Spec
    expect(ready(make_input({ evaluator, spec })).tool_id).toBe("tool_a")
  })

  it("takes the tool of a tool_call template eval", () => {
    const evaluator = make_eval({
      template: "tool_call",
      template_properties: { tool_id: "tool_b" },
    })
    expect(ready(make_input({ evaluator })).tool_id).toBe("tool_b")
  })

  it("resolves a tool_call_check judge's function name to a tool id", () => {
    const tool_sets = [
      {
        set_name: "Tools",
        tools: [
          { id: "tool_x", name: "Search", function_name: "search" },
          { id: "tool_y", name: "Lookup", function_name: "lookup" },
        ],
      },
    ] as unknown as ToolSetApiDescription[]
    const judge_properties = {
      type: "tool_call_check",
      expected_tools: [{ tool_name: "lookup" }],
    }
    expect(ready(make_input({ judge_properties, tool_sets })).tool_id).toBe(
      "tool_y",
    )
  })

  it("leaves the tool out when the judge names an unknown function", () => {
    const judge_properties = {
      type: "tool_call_check",
      expected_tools: [{ tool_name: "missing" }],
    }
    expect(ready(make_input({ judge_properties })).tool_id).toBeNull()
  })
})
