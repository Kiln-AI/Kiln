import { describe, expect, it } from "vitest"
import type { Eval, Spec } from "$lib/types"
import {
  buildCoverageData,
  pass_rate_for,
  type RunConfigEvalScoresSummary,
} from "./eval_coverage_data"

const CONSTITUTION = `## 6. Principles\n1. Exact records.\n2. Wait before delete.\n3. Right numbers.\n4. Honest claims.\n`

function make_spec(over: Partial<Spec> = {}): Spec {
  return {
    id: "s1",
    name: "Spec One",
    definition: "d",
    properties: { spec_type: "issue", issue_description: "x" },
    priority: 1,
    status: "active",
    tags: [],
    eval_id: "e1",
    ...over,
  } as Spec
}

function make_eval(over: Partial<Eval> = {}): Eval {
  return {
    id: "e1",
    name: "Eval One",
    output_scores: [{ name: "Eval One", type: "pass_fail", instruction: "" }],
    priority: 1,
    status: "active",
    ...over,
  } as unknown as Eval
}

const SCORES: RunConfigEvalScoresSummary = {
  eval_results: [
    {
      eval_id: "e1",
      eval_name: "Eval One",
      dataset_size: 40,
      missing_default_eval_config: false,
      eval_config_result: {
        eval_config_id: "c",
        percent_complete: 1,
        n_excluded: 0,
        results: { eval_one: { mean_score: 0.75 } },
      },
    },
    {
      eval_id: "e2",
      eval_name: "Never Run",
      dataset_size: 10,
      missing_default_eval_config: true,
      eval_config_result: null,
    },
  ],
} as unknown as RunConfigEvalScoresSummary

describe("pass_rate_for", () => {
  it("reads the pass_fail score mean", () => {
    expect(pass_rate_for("e1", make_eval(), SCORES)).toEqual({
      pass_rate: 0.75,
      dataset_size: 40,
    })
  })
  it("is null when the eval never ran or is absent", () => {
    expect(pass_rate_for("e2", undefined, SCORES)).toEqual({
      pass_rate: null,
      dataset_size: 10,
    })
    expect(pass_rate_for("zz", undefined, SCORES).pass_rate).toBeNull()
    expect(pass_rate_for("e1", make_eval(), null).pass_rate).toBeNull()
  })
})

describe("buildCoverageData", () => {
  const base = { project_id: "p", task_id: "t", eval_scores: SCORES }

  it("sizes by priority and has no gaps without a constitution", () => {
    const data = buildCoverageData({
      ...base,
      task_description: "just prose",
      specs: [
        make_spec({ id: "s1", eval_id: "e1" }),
        make_spec({ id: "s3", eval_id: "e3", priority: 3 }),
      ],
      evals: [
        make_eval({ id: "e1", priority: 0 }),
        make_eval({ id: "e3", priority: 3 }),
      ],
    })
    expect(data.covered).toBeNull()
    expect(data.nodes.map((n) => n.kind)).toEqual(["eval", "eval"])
    const [a, b] = data.nodes
    expect(a.weight / b.weight).toBeCloseTo(8)
    expect(a.pass_rate).toBe(0.75)
    expect(a.href).toBe("/specs/p/t/s1")
  })

  it("splits the constitution between evals, planned specs and gaps", () => {
    const data = buildCoverageData({
      ...base,
      task_description: CONSTITUTION,
      specs: [
        make_spec({
          id: "s1",
          eval_id: "e1",
          tags: ["principle_1", "principle_2"],
        }),
        make_spec({
          id: "s2",
          eval_id: "e2",
          tags: ["principle_3"],
          status: "future",
        }),
        make_spec({
          id: "old",
          eval_id: "e9",
          tags: ["principle_4"],
          status: "archived",
        }),
      ],
      evals: [
        make_eval({ id: "e1" }),
        make_eval({ id: "e2", status: "future" }),
        make_eval({ id: "e9", status: "archived" }),
      ],
    })
    expect(data.active_count).toBe(1)
    expect(data.covered).toBeCloseTo(0.5)
    const by_id = new Map(data.nodes.map((n) => [n.id, n]))
    expect(by_id.get("s1")?.weight).toBeCloseTo(0.5)
    expect(by_id.get("s2")?.kind).toBe("planned")
    expect(by_id.get("s2")?.weight).toBeCloseTo(0.25)
    expect(by_id.get("gap-4")?.kind).toBe("gap")
    expect(by_id.get("gap-4")?.href).toBe(
      "/specs/p/t/builder?description=Principle%204%3A%20Honest%20claims.",
    )
    expect(by_id.get("gap-4")?.weight).toBeCloseTo(0.25)
    expect(by_id.get("gap-3")).toBeUndefined()
    expect(by_id.get("old")).toBeUndefined()
    const sum = data.nodes.reduce((s, n) => s + n.weight, 0)
    expect(sum).toBeCloseTo(1)
  })

  it("includes legacy evals with no spec", () => {
    const data = buildCoverageData({
      ...base,
      task_description: CONSTITUTION,
      specs: [],
      evals: [make_eval({ id: "e1" })],
    })
    const legacy = data.nodes.find((n) => n.id === "e1")
    expect(legacy?.href).toBe("/specs/p/t/legacy/e1")
    expect(legacy?.principles).toEqual([])
    expect(legacy?.weight).toBeGreaterThan(0)
    expect(data.nodes.filter((n) => n.kind === "gap")).toHaveLength(4)
  })
})
