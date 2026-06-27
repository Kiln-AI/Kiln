import { describe, it, expect } from "vitest"
import { build_eval_options } from "./eval_options"
import type { Eval, Spec } from "$lib/types"

function make_eval(id: string, name: string): Eval {
  return {
    id,
    name,
    eval_set_filter_id: `tag::eval_set_${id}`,
  } as Eval
}

function make_spec(id: string, name: string, eval_id: string | null): Spec {
  return {
    id,
    name,
    eval_id,
  } as Spec
}

describe("build_eval_options", () => {
  it("returns an empty list when there are no specs or evals", () => {
    expect(build_eval_options([], {})).toEqual([])
  })

  it("lists evals from specs, preferring the spec name", () => {
    const evals_by_id = { e1: make_eval("e1", "Eval One") }
    const specs = [make_spec("s1", "Spec One", "e1")]
    expect(build_eval_options(specs, evals_by_id)).toEqual([
      { name: "Spec One", eval_id: "e1" },
    ])
  })

  it("lists legacy evals that have no spec", () => {
    const evals_by_id = { e1: make_eval("e1", "Legacy Eval") }
    expect(build_eval_options([], evals_by_id)).toEqual([
      { name: "Legacy Eval", eval_id: "e1" },
    ])
  })

  it("combines specs and legacy evals, de-duped by eval id", () => {
    const evals_by_id = {
      e1: make_eval("e1", "Eval One"),
      e2: make_eval("e2", "Legacy Eval"),
    }
    const specs = [make_spec("s1", "Spec One", "e1")]
    const options = build_eval_options(specs, evals_by_id)
    expect(options).toEqual([
      { name: "Spec One", eval_id: "e1" },
      { name: "Legacy Eval", eval_id: "e2" },
    ])
  })

  it("ignores specs without an eval_id", () => {
    const specs = [make_spec("s1", "No Eval Spec", null)]
    expect(build_eval_options(specs, {})).toEqual([])
  })

  it("does not duplicate an eval referenced by multiple specs", () => {
    const evals_by_id = { e1: make_eval("e1", "Eval One") }
    const specs = [
      make_spec("s1", "Spec One", "e1"),
      make_spec("s2", "Spec Two", "e1"),
    ]
    expect(build_eval_options(specs, evals_by_id)).toEqual([
      { name: "Spec One", eval_id: "e1" },
    ])
  })

  it("keeps a spec whose eval is not yet loaded so it stays selectable", () => {
    const specs = [make_spec("s1", "Spec One", "missing_eval")]
    expect(build_eval_options(specs, {})).toEqual([
      { name: "Spec One", eval_id: "missing_eval" },
    ])
  })
})
