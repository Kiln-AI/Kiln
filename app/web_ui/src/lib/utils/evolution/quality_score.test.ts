import { describe, it, expect } from "vitest"
import type { components } from "$lib/api_schema"
import type { Eval } from "$lib/types"
import { build_lens_data, type LensData } from "./score_lens"
import { build_score_families, type ScoreFamily } from "./score_families"
import {
  axis_phrase,
  below_gate_reason,
  family_quality_breakdown,
  is_borderline,
  quality_key_metas,
  quality_tooltip_lines,
  weakest_family_quality,
} from "./quality_score"

type EvalResultsSummaryResponse =
  components["schemas"]["EvalResultsSummaryResponse"]
type ScoreType = components["schemas"]["TaskOutputRatingType"]
type ScoreDirection = components["schemas"]["ScoreDirection"]
type Spec = components["schemas"]["Spec"]

type ScoreSpec = {
  name: string
  type: ScoreType
  direction?: ScoreDirection
}

/** A lens over the given evals, with per-config means and (optional) counts. */
function lens_of(
  evals: { id: string; scores: ScoreSpec[] }[],
  means: Record<string, Record<string, Record<string, number>>>,
  counts: Record<string, Record<string, Record<string, number>>> = {},
): LensData {
  const evals_by_id: Record<string, unknown> = {}
  const eval_models: Eval[] = []
  for (const spec of evals) {
    evals_by_id[spec.id] = {
      name: spec.id.toUpperCase(),
      output_score_keys: spec.scores.map((score) => score.name),
      default_judge_config_id: null,
      dataset_size: 25,
    }
    eval_models.push({
      id: spec.id,
      name: spec.id.toUpperCase(),
      output_scores: spec.scores.map((score) => ({
        name: score.name,
        type: score.type,
        direction: score.direction ?? "higher_is_better",
        instruction: null,
      })),
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any)
  }

  const cells: Record<string, Record<string, unknown>> = {}
  for (const [runConfigId, by_eval] of Object.entries(means)) {
    cells[runConfigId] = {}
    for (const [evalId, values] of Object.entries(by_eval)) {
      cells[runConfigId][evalId] = {
        mean_scores: values,
        percent_complete: 1,
        n_used_by_score_key: counts[runConfigId]?.[evalId],
      }
    }
  }

  return build_lens_data(
    {
      evals_by_id,
      run_configs_by_id: {},
      scores_by_run_config_by_eval: cells,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any,
    eval_models,
  )
}

/** Specs declaring `fam_*` tags, the way a real task carries them. */
function families_of(
  by_eval: Record<string, string>,
): Map<string, ScoreFamily> {
  const specs = Object.entries(by_eval).map(
    ([evalId, family]) =>
      ({
        id: `spec_${evalId}`,
        eval_id: evalId,
        tags: [`fam_${family}`],
      }) as unknown as Spec,
  )
  return build_score_families(specs)
}

describe("quality_key_metas", () => {
  it("keeps the criteria and drops the informational ones", () => {
    const data = lens_of(
      [
        {
          id: "e1",
          scores: [
            { name: "pass", type: "pass_fail" },
            { name: "note", type: "pass_fail", direction: "informational" },
          ],
        },
      ],
      { rc1: { e1: { pass: 1, note: 1 } } },
    )
    expect(quality_key_metas(data.keyMetas).map((m) => m.scoreKey)).toEqual([
      "pass",
    ])
  })

  it("drops a metrics eval whole, direction or no direction", () => {
    const data = lens_of(
      [
        { id: "e1", scores: [{ name: "pass", type: "pass_fail" }] },
        {
          id: "eff",
          scores: [
            { name: "cost_usd", type: "custom", direction: "lower_is_better" },
            {
              name: "cache_hit_rate",
              type: "custom",
              direction: "higher_is_better",
            },
          ],
        },
      ],
      {
        rc1: { e1: { pass: 1 }, eff: { cost_usd: 1, cache_hit_rate: 0.5 } },
        rc2: { e1: { pass: 0 }, eff: { cost_usd: 2, cache_hit_rate: 0.9 } },
      },
    )
    expect(quality_key_metas(data.keyMetas).map((m) => m.evalId)).toEqual([
      "e1",
    ])
  })
})

describe("weakest_family_quality", () => {
  // Three families over four criteria, so a mean and a minimum differ.
  const data = lens_of(
    [
      {
        id: "tool",
        scores: [{ name: "tool_call_errored", type: "pass_fail" }],
      },
      {
        id: "skill",
        scores: [{ name: "failed_skill_read", type: "pass_fail" }],
      },
      {
        id: "write",
        scores: [{ name: "write_correctness", type: "pass_fail" }],
      },
      {
        id: "ground",
        scores: [{ name: "answer_matches_data", type: "pass_fail" }],
      },
    ],
    {
      rc1: {
        tool: { tool_call_errored: 0.8 },
        skill: { failed_skill_read: 0.9 },
        write: { write_correctness: 0.48 },
        ground: { answer_matches_data: 0.88 },
      },
    },
    {
      rc1: {
        tool: { tool_call_errored: 22 },
        skill: { failed_skill_read: 23 },
        write: { write_correctness: 21 },
        ground: { answer_matches_data: 25 },
      },
    },
  )
  const families = families_of({
    tool: "structural",
    skill: "structural",
    write: "data_integrity",
    ground: "grounded",
  })

  it("is the weakest family's mean, not the mean of the criteria", () => {
    const result = weakest_family_quality(data, families, "rc1")
    // structural (0.8 + 0.9)/2 = 0.85, data_integrity 0.48, grounded 0.88
    expect(result?.quality).toBeCloseTo(0.48, 6)
    expect(result?.weakest?.label).toBe("Data Integrity")
    expect(result?.mode).toBe("families")
    // The flat mean would have been 0.765, which clears a 70% gate on a
    // criterion that is a coin flip.
    expect(result?.quality).toBeLessThan(0.7)
  })

  it("pools the family's n so a family interval is tighter than an axis one", () => {
    const result = weakest_family_quality(data, families, "rc1")
    const structural = result?.families.find((f) => f.id === "structural")
    expect(structural?.pooled_n).toBe(45)
    expect(structural?.value).toBeCloseTo(0.85, 6)
  })

  it("orders the families the way the ring does", () => {
    const result = weakest_family_quality(data, families, "rc1")
    expect(result?.families.map((f) => f.label)).toEqual([
      "Data Integrity",
      "Grounded",
      "Structural",
    ])
  })

  it("breaks a tie without caring which family it picked", () => {
    const tied = lens_of(
      [
        { id: "a", scores: [{ name: "x", type: "pass_fail" }] },
        { id: "b", scores: [{ name: "y", type: "pass_fail" }] },
      ],
      { rc1: { a: { x: 0.5 }, b: { y: 0.5 } } },
    )
    const result = weakest_family_quality(
      tied,
      families_of({ a: "one", b: "two" }),
      "rc1",
    )
    expect(result?.quality).toBeCloseTo(0.5, 6)
    expect(["One", "Two"]).toContain(result?.weakest?.label)
  })

  it("averages a family over the axes it HAS, and says how many it does not", () => {
    const partial = lens_of(
      [
        { id: "tool", scores: [{ name: "a", type: "pass_fail" }] },
        { id: "skill", scores: [{ name: "b", type: "pass_fail" }] },
        { id: "write", scores: [{ name: "c", type: "pass_fail" }] },
      ],
      { rc1: { tool: { a: 0.6 }, write: { c: 0.9 } } },
    )
    const result = weakest_family_quality(
      partial,
      families_of({
        tool: "structural",
        skill: "structural",
        write: "data_integrity",
      }),
      "rc1",
    )
    const structural = result?.families.find((f) => f.id === "structural")
    expect(structural?.value).toBeCloseTo(0.6, 6)
    expect(structural?.axes).toHaveLength(1)
    expect(structural?.unscored).toBe(1)
  })

  it("is null when a whole declared family went unmeasured", () => {
    // The case this rule comes from: one config had no runs at all on a
    // write-safety judge every other config had 15-25 of, and a best-effort
    // mean over the rest would have ranked it above configs that ran it.
    const missing = lens_of(
      [
        { id: "tool", scores: [{ name: "a", type: "pass_fail" }] },
        { id: "write", scores: [{ name: "c", type: "pass_fail" }] },
      ],
      { rc1: { tool: { a: 0.9 } } },
    )
    expect(
      weakest_family_quality(
        missing,
        families_of({ tool: "structural", write: "data_integrity" }),
        "rc1",
      ),
    ).toBeNull()
  })

  it("is null for a config with no criterion scores at all", () => {
    expect(weakest_family_quality(data, families, "never_run")).toBeNull()
  })

  it("falls back to the flat mean when the task declares no families", () => {
    const result = weakest_family_quality(data, new Map(), "rc1")
    expect(result?.mode).toBe("flat")
    expect(result?.weakest).toBeNull()
    // (0.8 + 0.9 + 0.48 + 0.88) / 4
    expect(result?.quality).toBeCloseTo(0.765, 6)
  })

  it("falls back when the grouping puts everything in one family", () => {
    const result = weakest_family_quality(
      data,
      families_of({
        tool: "same",
        skill: "same",
        write: "same",
        ground: "same",
      }),
      "rc1",
    )
    expect(result?.mode).toBe("flat")
    expect(result?.quality).toBeCloseTo(0.765, 6)
  })

  it("leaves the metrics eval out of every family", () => {
    const with_metrics = lens_of(
      [
        { id: "tool", scores: [{ name: "a", type: "pass_fail" }] },
        { id: "write", scores: [{ name: "c", type: "pass_fail" }] },
        {
          id: "eff",
          scores: [
            { name: "cost_usd", type: "custom", direction: "lower_is_better" },
          ],
        },
      ],
      {
        rc1: { tool: { a: 0.9 }, write: { c: 0.5 }, eff: { cost_usd: 1 } },
        rc2: { tool: { a: 0.1 }, write: { c: 0.1 }, eff: { cost_usd: 9 } },
      },
    )
    const result = weakest_family_quality(
      with_metrics,
      families_of({
        tool: "structural",
        write: "data_integrity",
        eff: "efficiency",
      }),
      "rc1",
    )
    expect(result?.families.map((f) => f.id).sort()).toEqual([
      "data_integrity",
      "structural",
    ])
    // rc1 is the cheapest, and that buys it nothing
    expect(result?.quality).toBeCloseTo(0.5, 6)
  })

  // The measured case: the Nova task's test lane, five configs, three families.
  it("reproduces the family means measured on a real five-config task", () => {
    const axes: Record<string, { family: string; values: number[] }> = {
      tool_call_errored: {
        family: "structural",
        values: [0.7727272727, 0.16, 0.2777777778, 0.2, 0.44],
      },
      failed_skill_read: {
        family: "structural",
        values: [0.7391304348, 1, 1, 0.2, 0.48],
      },
      one_at_a_time_writes: {
        family: "structural",
        values: [1, 1, 1, 0, 0],
      },
      write_correctness: {
        family: "data_integrity",
        values: [0.4761904762, 0.5454545455, 0.6818181818, 0.32, 0],
      },
      false_done_claim: {
        family: "data_integrity",
        values: [1, 1, 0.88, 1, 0.96],
      },
      answer_matches_data: {
        family: "grounded",
        values: [0.88, 0.9583333333, 0.875, 0.72, 0],
      },
    }
    const configs = ["luna", "flash", "pro", "gpt5p4", "mini"]
    // From the investigation's family table
    const expected_min = [0.738, 0.72, 0.759, 0.133, 0]
    const expected_weakest = [
      "Data Integrity",
      "Structural",
      "Structural",
      "Structural",
      "Grounded",
    ]

    const means: Record<string, Record<string, Record<string, number>>> = {}
    configs.forEach((id, i) => {
      means[id] = Object.fromEntries(
        Object.entries(axes).map(([key, axis]) => [
          key,
          { [key]: axis.values[i] },
        ]),
      )
    })
    const real = lens_of(
      Object.keys(axes).map((key) => ({
        id: key,
        scores: [{ name: key, type: "pass_fail" as ScoreType }],
      })),
      means,
    )
    const real_families = families_of(
      Object.fromEntries(
        Object.entries(axes).map(([key, axis]) => [key, axis.family]),
      ),
    )

    configs.forEach((id, i) => {
      const result = weakest_family_quality(real, real_families, id)
      expect(result?.quality).toBeCloseTo(expected_min[i], 3)
      expect(result?.weakest?.label).toBe(expected_weakest[i])
    })

    // ...and the gate verdicts the investigation reports: three clear 50, 60
    // and 70, none clears 80.
    for (const floor of [0.5, 0.6, 0.7]) {
      const clearing = configs.filter(
        (id) =>
          (weakest_family_quality(real, real_families, id)?.quality ?? 0) >=
          floor,
      )
      expect(clearing).toEqual(["luna", "flash", "pro"])
    }
    expect(
      configs.filter(
        (id) =>
          (weakest_family_quality(real, real_families, id)?.quality ?? 0) >=
          0.8,
      ),
    ).toEqual([])
  })
})

describe("family_quality_breakdown", () => {
  const data = lens_of(
    [
      {
        id: "write",
        scores: [{ name: "write_correctness", type: "pass_fail" }],
      },
      { id: "done", scores: [{ name: "false_done_claim", type: "pass_fail" }] },
    ],
    {
      rc1: {
        write: { write_correctness: 0.4761904762 },
        done: { false_done_claim: 1 },
      },
    },
    {
      rc1: { write: { write_correctness: 21 }, done: { false_done_claim: 25 } },
    },
  )
  const families = families_of({
    write: "data_integrity",
    done: "data_integrity",
  })

  it("carries the interval and the n for each pass-fail axis", () => {
    const [family] = family_quality_breakdown(data, families, "rc1")
    const axis = family.axes.find((a) => a.scoreKey === "write_correctness")
    expect(axis?.n).toBe(21)
    expect(axis?.interval?.lower).toBeCloseTo(0.283, 2)
    expect(axis?.interval?.upper).toBeCloseTo(0.676, 2)
  })

  it("has no interval for a score type Wilson does not apply to", () => {
    const five = lens_of(
      [{ id: "e1", scores: [{ name: "stars", type: "five_star" }] }],
      { rc1: { e1: { stars: 3 } } },
      { rc1: { e1: { stars: 20 } } },
    )
    const [family] = family_quality_breakdown(five, new Map(), "rc1")
    expect(family.axes[0].interval).toBeNull()
    // ...and it still counts, on its own normalized scale
    expect(family.axes[0].value).toBeCloseTo(0.5, 6)
    expect(family.axes[0].raw).toBe(3)
  })

  it("has a null pooled n when the payload carries no counts", () => {
    const uncounted = lens_of(
      [{ id: "e1", scores: [{ name: "pass", type: "pass_fail" }] }],
      { rc1: { e1: { pass: 1 } } },
    )
    expect(
      family_quality_breakdown(uncounted, new Map(), "rc1")[0].pooled_n,
    ).toBeNull()
  })
})

describe("is_borderline", () => {
  const near_the_floor = (value: number, n: number) => ({
    quality: value,
    weakest: {
      id: "f",
      label: "F",
      value,
      axes: [],
      unscored: 0,
      pooled_n: n,
    },
    families: [],
    mode: "families" as const,
  })

  it("flags a config whose interval straddles the floor", () => {
    expect(is_borderline(near_the_floor(0.72, 25), 0.7)).toBe(true)
  })

  it("does not flag one the sample can separate", () => {
    expect(is_borderline(near_the_floor(0.95, 400), 0.7)).toBe(false)
  })

  it("flags wider as n shrinks, which is the point of the annotation", () => {
    expect(is_borderline(near_the_floor(0.5, 500), 0.6)).toBe(false)
    expect(is_borderline(near_the_floor(0.5, 12), 0.6)).toBe(true)
  })

  it("never flags without a gate, a breakdown, or an n", () => {
    expect(is_borderline(near_the_floor(0.72, 25), null)).toBe(false)
    expect(is_borderline(null, 0.7)).toBe(false)
    expect(is_borderline(near_the_floor(0.72, 0), 0.7)).toBe(false)
  })
})

describe("tooltip copy", () => {
  const data = lens_of(
    [
      {
        id: "tool",
        scores: [{ name: "tool_call_errored", type: "pass_fail" }],
      },
      {
        id: "skill",
        scores: [{ name: "failed_skill_read", type: "pass_fail" }],
      },
      {
        id: "write",
        scores: [{ name: "write_correctness", type: "pass_fail" }],
      },
      { id: "done", scores: [{ name: "false_done_claim", type: "pass_fail" }] },
      {
        id: "ground",
        scores: [{ name: "answer_matches_data", type: "pass_fail" }],
      },
    ],
    {
      rc1: {
        tool: { tool_call_errored: 0.8 },
        skill: { failed_skill_read: 0.88 },
        write: { write_correctness: 0.4761904762 },
        done: { false_done_claim: 1 },
        ground: { answer_matches_data: 0.88 },
      },
    },
    {
      rc1: {
        tool: { tool_call_errored: 22 },
        skill: { failed_skill_read: 23 },
        write: { write_correctness: 21 },
        done: { false_done_claim: 25 },
        ground: { answer_matches_data: 25 },
      },
    },
  )
  const families = families_of({
    tool: "structural",
    skill: "structural",
    write: "data_integrity",
    done: "data_integrity",
    ground: "grounded",
  })
  const breakdown = weakest_family_quality(data, families, "rc1")

  it("leads with the number and the area that bound it", () => {
    const lines = quality_tooltip_lines(breakdown)
    expect(lines[0]).toBe("Quality 74% — weakest area: Data Integrity")
    expect(lines[1]).toBe("Data Integrity 74% · Grounded 88% · Structural 84%")
    expect(lines[2]).toBe(
      "Data Integrity: write_correctness 48% [28–68%] (n=21) · false_done_claim 100% [87–100%] (n=25)",
    )
  })

  it("appends the borderline note only against a floor it is close to", () => {
    expect(quality_tooltip_lines(breakdown, 0.7)).toContain(
      "Borderline at this sample size",
    )
    expect(quality_tooltip_lines(breakdown, 0.1)).not.toContain(
      "Borderline at this sample size",
    )
    expect(quality_tooltip_lines(breakdown)).not.toContain(
      "Borderline at this sample size",
    )
  })

  it("says what the number is when there are no families to name", () => {
    const flat = weakest_family_quality(data, new Map(), "rc1")
    const lines = quality_tooltip_lines(flat)
    expect(lines[0]).toContain("mean of every criterion")
    expect(lines[0]).not.toContain("weakest area")
  })

  it("has nothing to say about a config with no quality", () => {
    expect(quality_tooltip_lines(null)).toEqual([])
  })

  it("names the failing area and its axes on a ghost", () => {
    expect(below_gate_reason(breakdown, 0.8)).toBe(
      "Below the gate: Data Integrity 74% < 80% (write_correctness 48% · false_done_claim 100%)",
    )
  })

  it("gives no gate reason to a config that cleared it", () => {
    expect(below_gate_reason(breakdown, 0.5)).toBeNull()
    expect(below_gate_reason(breakdown, null)).toBeNull()
  })

  it("prints an axis with everything it knows, and nothing it does not", () => {
    expect(
      axis_phrase({
        evalId: "e",
        evalName: "E",
        scoreKey: "write_correctness",
        value: 0.4761904762,
        raw: 0.4761904762,
        n: 21,
        interval: { lower: 0.2834, upper: 0.6763 },
      }),
    ).toBe("write_correctness 48% [28–68%] (n=21)")
    expect(
      axis_phrase({
        evalId: "e",
        evalName: "E",
        scoreKey: "stars",
        value: 0.5,
        raw: 3,
        n: null,
        interval: null,
      }),
    ).toBe("stars 50%")
  })
})
