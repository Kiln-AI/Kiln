import { describe, it, expect } from "vitest"
import type { Eval, Spec } from "$lib/types"
import { compute_table, resolved_priority, resolved_status } from "./spec_table"

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

function by_id(...evals: Eval[]): Map<string, Eval> {
  return new Map(evals.map((e) => [e.id ?? "", e]))
}

describe("resolved priority/status", () => {
  it("prefers the eval's values over the spec's", () => {
    const spec = make_spec({ priority: 1, status: "active" })
    const evaluator = make_eval({ priority: 3, status: "archived" })
    expect(resolved_priority(spec, by_id(evaluator))).toBe(3)
    expect(resolved_status(spec, by_id(evaluator))).toBe("archived")
  })

  it("falls back to the spec when the eval is missing or unset", () => {
    const spec = make_spec({ priority: 2, status: "deprecated" })
    expect(resolved_priority(spec, by_id())).toBe(2)
    expect(resolved_status(spec, by_id())).toBe("deprecated")

    const unset_eval = make_eval({ priority: null, status: null })
    expect(resolved_priority(spec, by_id(unset_eval))).toBe(2)
    expect(resolved_status(spec, by_id(unset_eval))).toBe("deprecated")
  })
})

describe("compute_table archive partitioning", () => {
  // Regression guard for the archive-from-the-list flow: archiving updates
  // the EVAL's status, so the row must leave the active section based on the
  // eval, not the spec's stale copy.
  it("a spec whose eval is archived leaves the active rows", () => {
    const spec = make_spec({ status: "active" })
    const archived_eval = make_eval({ status: "archived" })

    const hidden = compute_table(
      [spec],
      [archived_eval],
      by_id(archived_eval),
      new Map(),
      false,
      [],
      "created_at",
      "desc",
    )
    expect(hidden.rows).toEqual([])
    expect(hidden.filtered).toEqual([])

    const shown = compute_table(
      [spec],
      [archived_eval],
      by_id(archived_eval),
      new Map(),
      true,
      [],
      "created_at",
      "desc",
    )
    expect(shown.rows?.length).toBe(1)
  })

  it("archived spec-less evals are hidden unless show_archived", () => {
    const legacy = make_eval({ id: "legacy1", status: "archived" })

    const hidden = compute_table(
      [],
      [legacy],
      by_id(legacy),
      new Map(),
      false,
      [],
      "created_at",
      "desc",
    )
    expect(hidden.rows).toEqual([])

    const shown = compute_table(
      [],
      [legacy],
      by_id(legacy),
      new Map(),
      true,
      [],
      "created_at",
      "desc",
    )
    expect(shown.rows?.map((r) => r.type)).toEqual(["legacy_eval"])
  })

  it("sorts by the eval's priority for spec rows", () => {
    const eval_a = make_eval({ id: "eval_a", priority: 3 })
    const eval_b = make_eval({ id: "eval_b", priority: 0 })
    const spec_a = make_spec({ id: "spec_a", eval_id: "eval_a", priority: 0 })
    const spec_b = make_spec({ id: "spec_b", eval_id: "eval_b", priority: 3 })

    const { rows } = compute_table(
      [spec_a, spec_b],
      [eval_a, eval_b],
      by_id(eval_a, eval_b),
      new Map(),
      false,
      [],
      "priority",
      "desc",
    )
    // Highest priority (P0) first, taken from the EVAL (spec values inverted)
    expect(rows?.map((r) => r.data.id)).toEqual(["spec_b", "spec_a"])
  })
})
