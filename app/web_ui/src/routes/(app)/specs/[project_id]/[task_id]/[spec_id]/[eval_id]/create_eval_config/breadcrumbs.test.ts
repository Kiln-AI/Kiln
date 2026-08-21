import { describe, it, expect } from "vitest"
import { buildCreateEvalBreadcrumbs } from "./breadcrumbs"
import type { Spec } from "$lib/types"

const spec = { name: "My Spec" } as Spec

describe("buildCreateEvalBreadcrumbs", () => {
  it("includes the spec crumb for spec-backed evals", () => {
    const crumbs = buildCreateEvalBreadcrumbs(
      "proj1",
      "task1",
      "spec1",
      "eval1",
      spec,
      null,
    )
    expect(crumbs.map((c) => c.label)).toEqual(["Evals", "My Spec", "Eval"])
    expect(crumbs[1].href).toBe("/specs/proj1/task1/spec1")
    expect(crumbs[2].href).toBe("/specs/proj1/task1/spec1/eval1")
  })

  it("drops the spec crumb for spec-less (legacy) evals", () => {
    const crumbs = buildCreateEvalBreadcrumbs(
      "proj1",
      "task1",
      "legacy",
      "eval1",
      null,
      null,
    )
    expect(crumbs.map((c) => c.label)).toEqual(["Evals", "Eval"])
    expect(crumbs[1].href).toBe("/specs/proj1/task1/legacy/eval1")
  })

  it("appends the Compare Judges crumb for next_page=eval_configs", () => {
    const crumbs = buildCreateEvalBreadcrumbs(
      "proj1",
      "task1",
      "legacy",
      "eval1",
      null,
      "eval_configs",
    )
    expect(crumbs.map((c) => c.label)).toEqual([
      "Evals",
      "Eval",
      "Compare Judges",
    ])
    expect(crumbs[2].href).toBe("/specs/proj1/task1/legacy/eval1/eval_configs")
  })

  it("appends the Compare Run Configurations crumb for next_page=compare_run_configs", () => {
    const crumbs = buildCreateEvalBreadcrumbs(
      "proj1",
      "task1",
      "spec1",
      "eval1",
      spec,
      "compare_run_configs",
    )
    expect(crumbs.map((c) => c.label)).toEqual([
      "Evals",
      "My Spec",
      "Eval",
      "Compare Run Configurations",
    ])
  })
})
