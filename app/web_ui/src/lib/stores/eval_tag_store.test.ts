import { describe, it, expect } from "vitest"
import type { Eval, Spec } from "$lib/types"
import { count_eval_tags } from "./eval_tag_store"

function make_spec(overrides: Partial<Spec> = {}): Spec {
  return {
    id: "spec1",
    name: "Spec One",
    definition: "definition",
    properties: { spec_type: "toxicity" },
    priority: 1,
    status: "active",
    tags: [],
    eval_id: "eval1",
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  } as Spec
}

function make_eval(overrides: Partial<Eval> = {}): Eval {
  return {
    id: "eval1",
    name: "Eval One",
    eval_set_filter_id: "tag::eval_set",
    eval_configs_filter_id: "tag::golden",
    output_scores: [{ name: "score", type: "pass_fail" }],
    priority: 1,
    status: "active",
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  } as Eval
}

describe("count_eval_tags", () => {
  it("counts how many evals use each tag", () => {
    const specs = [
      make_spec({ id: "s1", eval_id: "e1", tags: ["billing", "v3"] }),
      make_spec({ id: "s2", eval_id: "e2", tags: ["v3"] }),
    ]
    const evals = [make_eval({ id: "e1" }), make_eval({ id: "e2" })]

    expect(count_eval_tags(specs, evals)).toEqual({ billing: 1, v3: 2 })
  })

  it("leaves out evals archived on the eval", () => {
    const specs = [
      make_spec({ id: "s1", eval_id: "e1", tags: ["kept"] }),
      make_spec({ id: "s2", eval_id: "e2", tags: ["retired"] }),
    ]
    const evals = [
      make_eval({ id: "e1" }),
      make_eval({ id: "e2", status: "archived" }),
    ]

    expect(count_eval_tags(specs, evals)).toEqual({ kept: 1 })
  })

  it("leaves out evals archived on the spec when the eval has no status", () => {
    const specs = [
      make_spec({
        id: "s1",
        eval_id: "e1",
        status: "archived",
        tags: ["retired"],
      }),
    ]
    const evals = [make_eval({ id: "e1", status: undefined })]

    expect(count_eval_tags(specs, evals)).toEqual({})
  })
})
