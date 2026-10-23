import { describe, it, expect } from "vitest"
import type { components } from "$lib/api_schema"
import type { Eval } from "$lib/types"
import {
  NO_SCORE_COLOR,
  SCORE_BIN_COLORS,
  STRIP_BETTER_COLOR,
  STRIP_EMPTY_COLOR,
  STRIP_NEUTRAL_COLOR,
  STRIP_WORSE_COLOR,
  build_lens_data,
  delta_vs_parent,
  lens_color,
  lens_key,
  normalized_lens_value,
  normalized_score,
  parse_lens_key,
  percent_complete,
  raw_lens_value,
  raw_score,
  run_count,
  score_key_id,
  strip_cell_color,
  strip_cells,
} from "./score_lens"
import { build_metric_axes } from "./metric_axes"

type EvalResultsSummaryResponse =
  components["schemas"]["EvalResultsSummaryResponse"]
type ScoreType = components["schemas"]["TaskOutputRatingType"]
type ScoreDirection = components["schemas"]["ScoreDirection"]

type ScoreSpec = {
  name: string
  type: ScoreType
  direction?: ScoreDirection
}

// One eval with the given scores, plus per-run-config mean values keyed by
// the eval's JSON score keys.
function make_summary(
  evals: { id: string; name: string; scores: ScoreSpec[] }[],
  scores_by_run_config: Record<
    string,
    Record<string, { means: Record<string, number>; percent?: number }>
  >,
): { summary: EvalResultsSummaryResponse; evals: Eval[] } {
  const evals_by_id: Record<string, unknown> = {}
  const eval_models: Eval[] = []
  for (const spec of evals) {
    evals_by_id[spec.id] = {
      name: spec.name,
      output_score_keys: spec.scores.map((score) =>
        score.name.toLowerCase().replace(/ /g, "_"),
      ),
      default_judge_config_id: null,
      dataset_size: 10,
    }
    eval_models.push({
      id: spec.id,
      name: spec.name,
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
  for (const [run_config_id, by_eval] of Object.entries(scores_by_run_config)) {
    cells[run_config_id] = {}
    for (const [eval_id, cell] of Object.entries(by_eval)) {
      cells[run_config_id][eval_id] = {
        mean_scores: cell.means,
        percent_complete: cell.percent ?? 1,
      }
    }
  }

  return {
    summary: {
      evals_by_id,
      run_configs_by_id: {},
      scores_by_run_config_by_eval: cells,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any,
    evals: eval_models,
  }
}

describe("lens keys", () => {
  it("round-trips every lens kind", () => {
    expect(score_key_id("e1", "pass_fail")).toBe("e1::pass_fail")
    expect(lens_key({ kind: "none" })).toBe("none")
    expect(lens_key({ kind: "aggregate" })).toBe("aggregate")
    expect(lens_key({ kind: "single", evalId: "e1", scoreKey: "acc" })).toBe(
      "e1::acc",
    )
    expect(parse_lens_key("e1::acc")).toEqual({
      kind: "single",
      evalId: "e1",
      scoreKey: "acc",
    })
    expect(parse_lens_key("aggregate")).toEqual({ kind: "aggregate" })
  })

  // The default moved to "none". A saved view that wanted the aggregate says so
  // in the key, so only the unset and malformed cases land on the new default.
  it("defaults to no lens, and keeps an explicit aggregate", () => {
    for (const bad of [null, "", "none", "::acc", "e1::", "nosep"]) {
      expect(parse_lens_key(bad)).toEqual({ kind: "none" })
    }
  })
})

describe("the no-lens default", () => {
  const { summary, evals } = make_summary(
    [
      {
        id: "e1",
        name: "Eval One",
        scores: [{ name: "Acc", type: "pass_fail" }],
      },
    ],
    { rc1: { e1: { means: { acc: 1 } } } },
  )
  const data = build_lens_data(summary, evals)

  it("has no value to show, under either accessor", () => {
    expect(normalized_lens_value(data, "rc1", { kind: "none" })).toBeNull()
    expect(raw_lens_value(data, "rc1", { kind: "none" })).toBeNull()
  })
})

describe("run_count", () => {
  // One run scores every key of its eval, so a run config's count for that
  // eval is the largest per-key count and not their sum; different evals are
  // different runs of the task, so those do add up.
  function data_with_counts(counts: Record<string, Record<string, number>>) {
    const { summary, evals } = make_summary(
      [
        {
          id: "e1",
          name: "Eval One",
          scores: [
            { name: "Acc", type: "pass_fail" },
            { name: "Tone", type: "pass_fail" },
          ],
        },
        {
          id: "e2",
          name: "Eval Two",
          scores: [{ name: "Latency", type: "pass_fail" }],
        },
      ],
      {
        rc1: {
          e1: { means: { acc: 1, tone: 1 } },
          e2: { means: { latency: 1 } },
        },
      },
    )
    for (const [eval_id, keys] of Object.entries(counts)) {
      const cell = summary.scores_by_run_config_by_eval["rc1"][eval_id]
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ;(cell as any).n_used_by_score_key = keys
    }
    return build_lens_data(summary, evals)
  }

  it("takes the largest count per eval and sums across evals", () => {
    const data = data_with_counts({
      e1: { acc: 25, tone: 24 },
      e2: { latency: 40 },
    })
    expect(run_count(data, "rc1")).toBe(65)
  })

  it("is zero for a config with nothing behind it", () => {
    expect(run_count(data_with_counts({}), "rc2")).toBe(0)
  })

  // A payload from a server that predates n_used_by_score_key carries scores
  // and no counts; the card says 0 runs rather than inventing one.
  it("is zero when the payload has no counts at all", () => {
    expect(run_count(data_with_counts({}), "rc1")).toBe(0)
  })
})

describe("build_lens_data normalization", () => {
  it("scales each known score type against its own full range", () => {
    const { summary, evals } = make_summary(
      [
        {
          id: "e1",
          name: "Eval One",
          scores: [
            { name: "five", type: "five_star" },
            { name: "pass", type: "pass_fail" },
            { name: "critical", type: "pass_fail_critical" },
          ],
        },
      ],
      {
        rc1: { e1: { means: { five: 3, pass: 0.75, critical: 0 } } },
      },
    )
    const data = build_lens_data(summary, evals)

    // five_star spans 1..5, so the midpoint 3 normalizes to 0.5
    expect(normalized_score(data, "rc1", "e1", "five")).toBeCloseTo(0.5, 6)
    // pass_fail spans 0..1, so the raw value passes through
    expect(normalized_score(data, "rc1", "e1", "pass")).toBeCloseTo(0.75, 6)
    // pass_fail_critical spans -1..1, so 0 is the midpoint
    expect(normalized_score(data, "rc1", "e1", "critical")).toBeCloseTo(0.5, 6)
    // Raw values are preserved untouched alongside the normalized ones
    expect(raw_score(data, "rc1", "e1", "five")).toBe(3)
  })

  it("clamps out-of-range values into 0..1", () => {
    const { summary, evals } = make_summary(
      [
        {
          id: "e1",
          name: "Eval One",
          scores: [
            { name: "low", type: "five_star" },
            { name: "high", type: "pass_fail" },
          ],
        },
      ],
      { rc1: { e1: { means: { low: -4, high: 12 } } } },
    )
    const data = build_lens_data(summary, evals)
    expect(normalized_score(data, "rc1", "e1", "low")).toBe(0)
    expect(normalized_score(data, "rc1", "e1", "high")).toBe(1)
  })

  it("min-max scales custom scores across the run configs that have them", () => {
    const { summary, evals } = make_summary(
      [
        {
          id: "e1",
          name: "Eval One",
          scores: [{ name: "cost", type: "custom" }],
        },
      ],
      {
        rc1: { e1: { means: { cost: 100 } } },
        rc2: { e1: { means: { cost: 200 } } },
        rc3: { e1: { means: { cost: 150 } } },
      },
    )
    const data = build_lens_data(summary, evals)
    expect(normalized_score(data, "rc1", "e1", "cost")).toBe(0)
    expect(normalized_score(data, "rc2", "e1", "cost")).toBe(1)
    expect(normalized_score(data, "rc3", "e1", "cost")).toBeCloseTo(0.5, 6)
  })

  it("puts every run config at 0.5 when a custom score has no spread", () => {
    const { summary, evals } = make_summary(
      [
        {
          id: "e1",
          name: "Eval One",
          scores: [{ name: "cost", type: "custom" }],
        },
      ],
      {
        rc1: { e1: { means: { cost: 42 } } },
        rc2: { e1: { means: { cost: 42 } } },
      },
    )
    const data = build_lens_data(summary, evals)
    expect(normalized_score(data, "rc1", "e1", "cost")).toBe(0.5)
    expect(normalized_score(data, "rc2", "e1", "cost")).toBe(0.5)
  })

  it("inverts lower_is_better scores so higher normalized is always better", () => {
    const { summary, evals } = make_summary(
      [
        {
          id: "e1",
          name: "Eval One",
          scores: [
            { name: "errors", type: "custom", direction: "lower_is_better" },
          ],
        },
      ],
      {
        rc1: { e1: { means: { errors: 0 } } },
        rc2: { e1: { means: { errors: 10 } } },
      },
    )
    const data = build_lens_data(summary, evals)
    expect(normalized_score(data, "rc1", "e1", "errors")).toBe(1)
    expect(normalized_score(data, "rc2", "e1", "errors")).toBe(0)
  })

  it("defaults an unmatched score key to higher_is_better with no type", () => {
    // The eval list is empty, so no output_score meta backs the summary's keys
    const { summary } = make_summary(
      [
        {
          id: "e1",
          name: "Eval One",
          scores: [{ name: "mystery", type: "custom" }],
        },
      ],
      { rc1: { e1: { means: { mystery: 1 } } } },
    )
    const data = build_lens_data(summary, [])
    const meta = data.keyMetas.find((m) => m.scoreKey === "mystery")!
    expect(meta.type).toBeNull()
    expect(meta.direction).toBe("higher_is_better")
    expect(meta.evalName).toBe("Eval One")
  })

  it("returns empty data for a missing summary and skips non-finite means", () => {
    const empty = build_lens_data(null, [])
    expect(empty.keyMetas).toEqual([])
    expect(empty.raw.size).toBe(0)

    const { summary, evals } = make_summary(
      [
        {
          id: "e1",
          name: "Eval One",
          scores: [{ name: "pass", type: "pass_fail" }],
        },
      ],
      { rc1: { e1: { means: { pass: NaN } } } },
    )
    const data = build_lens_data(summary, evals)
    expect(raw_score(data, "rc1", "e1", "pass")).toBeNull()
    expect(normalized_score(data, "rc1", "e1", "pass")).toBeNull()
  })

  it("records per-eval completion", () => {
    const { summary, evals } = make_summary(
      [
        {
          id: "e1",
          name: "Eval One",
          scores: [{ name: "pass", type: "pass_fail" }],
        },
      ],
      { rc1: { e1: { means: { pass: 1 }, percent: 0.4 } } },
    )
    const data = build_lens_data(summary, evals)
    expect(percent_complete(data, "rc1", "e1")).toBe(0.4)
    expect(percent_complete(data, "rc1", "missing")).toBeNull()
    expect(percent_complete(data, "missing", "e1")).toBeNull()
  })
})

describe("lens values", () => {
  const { summary, evals } = make_summary(
    [
      {
        id: "e1",
        name: "Eval One",
        scores: [
          { name: "pass", type: "pass_fail" },
          { name: "five", type: "five_star" },
          { name: "notes", type: "custom", direction: "informational" },
        ],
      },
    ],
    {
      rc1: { e1: { means: { pass: 1, five: 3, notes: 999 } } },
      rc2: { e1: { means: { pass: 0, five: 1, notes: 0 } } },
      rc3: { e1: { means: {} } },
    },
  )
  const data = build_lens_data(summary, evals)

  it("averages the non-informational normalized scores for the aggregate lens", () => {
    // rc1: pass 1.0, five 0.5 -> 0.75 (the informational key is skipped)
    expect(
      normalized_lens_value(data, "rc1", { kind: "aggregate" }),
    ).toBeCloseTo(0.75, 6)
    expect(normalized_lens_value(data, "rc2", { kind: "aggregate" })).toBe(0)
  })

  it("returns null for the aggregate when a run config has no scores", () => {
    expect(normalized_lens_value(data, "rc3", { kind: "aggregate" })).toBeNull()
  })

  it("reads a single-score lens straight through", () => {
    const lens = { kind: "single" as const, evalId: "e1", scoreKey: "five" }
    expect(normalized_lens_value(data, "rc1", lens)).toBeCloseTo(0.5, 6)
    // The raw lens value is the score's own value, not the normalized one
    expect(raw_lens_value(data, "rc1", lens)).toBe(3)
  })

  it("uses the normalized mean as the aggregate's displayed raw value", () => {
    expect(raw_lens_value(data, "rc1", { kind: "aggregate" })).toBeCloseTo(
      0.75,
      6,
    )
  })

  it("computes the delta against a parent, and null when either side is missing", () => {
    const lens = { kind: "aggregate" as const }
    expect(delta_vs_parent(data, "rc1", "rc2", lens)).toBeCloseTo(0.75, 6)
    expect(delta_vs_parent(data, "rc2", "rc1", lens)).toBeCloseTo(-0.75, 6)
    expect(delta_vs_parent(data, "rc1", null, lens)).toBeNull()
    expect(delta_vs_parent(data, "rc1", "rc3", lens)).toBeNull()
  })
})

// A latency eval's keys are authored `informational` on purpose: they are
// metrics, not quality, and pulling them into "overall quality" would be wrong.
// The performance-metrics radar plots them anyway, because being a metric is
// the entire point of that chart. Those two facts have to hold at once, so they
// are asserted together: the aggregate is the thing that must not move.
describe("informational metrics reach the chart, not the aggregate", () => {
  const quality: ScoreSpec[] = [
    { name: "pass", type: "pass_fail" },
    { name: "five", type: "five_star" },
  ]
  const latency: ScoreSpec[] = [
    "latency_ms_total",
    "latency_ms_turn1",
    "latency_ms_turn2",
    "latency_ms_turn3",
    "latency_ms_per_call",
  ].map((name) => ({
    name,
    type: "custom" as ScoreType,
    direction: "informational" as ScoreDirection,
  }))

  const latency_means = {
    latency_ms_total: 42_000,
    latency_ms_turn1: 12_000,
    latency_ms_turn2: 14_000,
    latency_ms_turn3: 16_000,
    latency_ms_per_call: 3_500,
  }

  const quality_only = make_summary(
    [{ id: "e1", name: "Quality", scores: quality }],
    { rc1: { e1: { means: { pass: 1, five: 3 } } } },
  )
  const plus_latency = make_summary(
    [
      { id: "e1", name: "Quality", scores: quality },
      { id: "l1", name: "Latency", scores: latency },
    ],
    {
      rc1: {
        e1: { means: { pass: 1, five: 3 } },
        l1: { means: latency_means },
      },
    },
  )
  const without = build_lens_data(quality_only.summary, quality_only.evals)
  const with_latency = build_lens_data(plus_latency.summary, plus_latency.evals)

  it("plots every informational latency key on the metrics radar", () => {
    const keys = build_metric_axes(with_latency.keyMetas).map(
      (axis) => axis.key,
    )
    expect(keys).toContain("l1::latency_ms_turn1")
    expect(keys).toContain("l1::latency_ms_turn2")
    expect(keys).toContain("l1::latency_ms_turn3")
    expect(keys).toContain("l1::latency_ms_per_call")
    // latency_ms_total is the quantity the usage rollup already reports, so it
    // is deduplicated into that axis rather than plotted twice
    expect(keys).toContain("cost::mean_total_llm_latency_ms")
    expect(keys).not.toContain("l1::latency_ms_total")
  })

  it("leaves the aggregate exactly where it was", () => {
    const lens = { kind: "aggregate" as const }
    const baseline = normalized_lens_value(without, "rc1", lens)
    expect(baseline).toBeCloseTo(0.75, 6)
    expect(normalized_lens_value(with_latency, "rc1", lens)).toBe(baseline)
  })

  it("does not let a large informational value drag the aggregate", () => {
    // Five keys in the tens of thousands next to two scores on 0..1: if they
    // were counted at all, the mean could not still be 0.75
    const lens = { kind: "aggregate" as const }
    expect(normalized_lens_value(with_latency, "rc1", lens)).toBeCloseTo(
      0.75,
      6,
    )
  })
})

// A metrics eval's keys are `custom` and NOT informational - cost_usd,
// total_tokens, cache_hit_rate all declare a direction, because the metrics
// radar needs one. That made them non-informational keys of the aggregate,
// which is a category error: a custom key has no scale of its own, so it is
// min-max scaled across the run configs in the summary, and "cheapest of the
// thirteen ever run here" was being averaged in with pass rates as if it were
// one.
describe("metric evals stay out of the aggregate", () => {
  const quality: ScoreSpec[] = [
    { name: "pass", type: "pass_fail" },
    { name: "grounded", type: "pass_fail" },
  ]
  // Directions declared, exactly as a real metrics eval declares them
  const metrics: ScoreSpec[] = [
    { name: "cost_usd", type: "custom", direction: "lower_is_better" },
    { name: "total_tokens", type: "custom", direction: "lower_is_better" },
    { name: "cache_hit_rate", type: "custom", direction: "higher_is_better" },
  ]

  const built = make_summary(
    [
      { id: "e1", name: "Quality", scores: quality },
      { id: "m1", name: "Efficiency", scores: metrics },
    ],
    {
      // The expensive, good config
      rc1: {
        e1: { means: { pass: 1, grounded: 1 } },
        m1: { means: { cost_usd: 10, total_tokens: 1000, cache_hit_rate: 0 } },
      },
      // The cheap, bad one
      rc2: {
        e1: { means: { pass: 0, grounded: 0 } },
        m1: { means: { cost_usd: 1, total_tokens: 100, cache_hit_rate: 1 } },
      },
    },
  )
  const data = build_lens_data(built.summary, built.evals)
  const lens = { kind: "aggregate" as const }

  it("is the quality mean, whatever the metrics say", () => {
    expect(normalized_lens_value(data, "rc1", lens)).toBeCloseTo(1, 6)
    expect(normalized_lens_value(data, "rc2", lens)).toBeCloseTo(0, 6)
  })

  it("does not let cheapness read as quality", () => {
    // Unfixed, rc2 scored 3 of the 5 keys at 1.0 (cheapest cost, fewest
    // tokens, best cache rate) and came out at 0.6 - ABOVE the config that
    // passes every criterion, on the number that gates a price chart.
    const rc1 = normalized_lens_value(data, "rc1", lens) as number
    const rc2 = normalized_lens_value(data, "rc2", lens) as number
    expect(rc1).toBeGreaterThan(rc2)
  })

  it("counts a custom key that sits beside graded ones, since its eval grades", () => {
    // is_metric_eval is about the EVAL, not the key: an eval with any bounded
    // score is a criterion eval and every key on it is a criterion key.
    const mixed = make_summary(
      [
        {
          id: "e1",
          name: "Judge",
          scores: [
            { name: "pass", type: "pass_fail" },
            {
              name: "odd_scale",
              type: "custom",
              direction: "higher_is_better",
            },
          ],
        },
      ],
      {
        rc1: { e1: { means: { pass: 1, odd_scale: 10 } } },
        rc2: { e1: { means: { pass: 1, odd_scale: 0 } } },
      },
    )
    const mixed_data = build_lens_data(mixed.summary, mixed.evals)
    expect(normalized_lens_value(mixed_data, "rc1", lens)).toBeCloseTo(1, 6)
    expect(normalized_lens_value(mixed_data, "rc2", lens)).toBeCloseTo(0.5, 6)
  })

  it("has no aggregate at all for a task that only reports metrics", () => {
    const only = make_summary(
      [{ id: "m1", name: "Efficiency", scores: metrics }],
      {
        rc1: {
          m1: {
            means: { cost_usd: 10, total_tokens: 1000, cache_hit_rate: 0 },
          },
        },
      },
    )
    const only_data = build_lens_data(only.summary, only.evals)
    expect(normalized_lens_value(only_data, "rc1", lens)).toBeNull()
  })

  // The measured case this came from: the Nova task's test lane, five pinned
  // configs, six quality keys and eleven non-informational metric keys. The
  // decontaminated aggregate has to be the flat pass-fail mean, and it is what
  // the investigation's (a′) column reports.
  it("reproduces the pass-fail means measured on a real five-config task", () => {
    const axes = {
      tool_call_errored: [0.7727272727, 0.16, 0.2777777778, 0.2, 0.44],
      failed_skill_read: [0.7391304348, 1, 1, 0.2, 0.48],
      one_at_a_time_writes: [1, 1, 1, 0, 0],
      write_correctness: [0.4761904762, 0.5454545455, 0.6818181818, 0.32, 0],
      false_done_claim: [1, 1, 0.88, 1, 0.96],
      answer_matches_data: [0.88, 0.9583333333, 0.875, 0.72, 0],
    }
    const configs = ["luna", "flash", "pro", "gpt5p4", "mini"]
    const expected = [
      0.8113413639, 0.7772979798, 0.7857659933, 0.4066666667, 0.3133333333,
    ]

    const cells: Record<
      string,
      Record<string, { means: Record<string, number> }>
    > = {}
    configs.forEach((id, i) => {
      cells[id] = {
        q: {
          means: Object.fromEntries(
            Object.entries(axes).map(([key, values]) => [key, values[i]]),
          ),
        },
        // Eleven metric keys, all with declared directions, on values that
        // min-max to whatever the cheap arm wants them to be
        eff: {
          means: Object.fromEntries(
            Array.from({ length: 11 }, (_, k) => [`m${k}`, (i + 1) * (k + 1)]),
          ),
        },
      }
    })

    const real = make_summary(
      [
        {
          id: "q",
          name: "Quality",
          scores: Object.keys(axes).map((name) => ({
            name,
            type: "pass_fail" as ScoreType,
          })),
        },
        {
          id: "eff",
          name: "Efficiency",
          scores: Array.from({ length: 11 }, (_, k) => ({
            name: `m${k}`,
            type: "custom" as ScoreType,
            direction: "lower_is_better" as ScoreDirection,
          })),
        },
      ],
      cells,
    )
    const real_data = build_lens_data(real.summary, real.evals)
    configs.forEach((id, i) => {
      expect(normalized_lens_value(real_data, id, lens)).toBeCloseTo(
        expected[i],
        6,
      )
    })
  })
})

describe("lens_color", () => {
  it("bins normalized values darkest-is-best and grays out no score", () => {
    expect(lens_color(null)).toBe(NO_SCORE_COLOR)
    expect(lens_color(NaN)).toBe(NO_SCORE_COLOR)
    expect(lens_color(0)).toBe(SCORE_BIN_COLORS[0])
    expect(lens_color(0.39)).toBe(SCORE_BIN_COLORS[0])
    expect(lens_color(0.4)).toBe(SCORE_BIN_COLORS[1])
    expect(lens_color(0.59)).toBe(SCORE_BIN_COLORS[1])
    expect(lens_color(0.6)).toBe(SCORE_BIN_COLORS[2])
    expect(lens_color(0.75)).toBe(SCORE_BIN_COLORS[3])
    expect(lens_color(0.9)).toBe(SCORE_BIN_COLORS[4])
    expect(lens_color(1)).toBe(SCORE_BIN_COLORS[4])
  })
})

describe("strip_cells", () => {
  const { summary, evals } = make_summary(
    [
      {
        id: "e1",
        name: "Eval One",
        scores: [
          { name: "pass", type: "pass_fail" },
          { name: "tiny", type: "pass_fail" },
          { name: "gone", type: "pass_fail" },
          { name: "notes", type: "custom", direction: "informational" },
        ],
      },
    ],
    {
      child: { e1: { means: { pass: 1, tiny: 0.5, notes: 7 } } },
      parent: { e1: { means: { pass: 0.2, tiny: 0.5, gone: 1, notes: 3 } } },
    },
  )
  const data = build_lens_data(summary, evals)
  const by_key = (cells: ReturnType<typeof strip_cells>, key: string) =>
    cells.find((cell) => cell.scoreKey === key)!

  it("emits one cell per score key, always in the same order", () => {
    const with_parent = strip_cells(data, "child", "parent")
    const without = strip_cells(data, "child", null)
    expect(with_parent.map((c) => c.scoreKey)).toEqual(
      data.keyMetas.map((m) => m.scoreKey),
    )
    expect(without.map((c) => c.scoreKey)).toEqual(
      with_parent.map((c) => c.scoreKey),
    )
  })

  it("colors a real improvement as a better delta", () => {
    const cell = by_key(strip_cells(data, "child", "parent"), "pass")
    expect(cell.mode).toBe("delta")
    expect(cell.sign).toBe(1)
    expect(cell.color).toBe(STRIP_BETTER_COLOR)
    expect(cell.title).toContain("+0.80 vs parent")
    expect(cell.title).toContain("Eval One · Pass")
  })

  it("colors a regression as a worse delta", () => {
    const cell = by_key(strip_cells(data, "parent", "child"), "pass")
    expect(cell.sign).toBe(-1)
    expect(cell.color).toBe(STRIP_WORSE_COLOR)
    expect(cell.title).toContain("−0.80 vs parent")
  })

  it("treats a move inside the epsilon dead zone as neutral", () => {
    const cell = by_key(strip_cells(data, "child", "parent"), "tiny")
    expect(cell.mode).toBe("delta")
    expect(cell.sign).toBe(0)
    expect(cell.color).toBe(STRIP_NEUTRAL_COLOR)
    expect(cell.title).toContain("±0.00")
  })

  it("falls back to the absolute lens color when there is no parent at all", () => {
    const cell = by_key(strip_cells(data, "child", null), "pass")
    expect(cell.mode).toBe("absolute")
    expect(cell.sign).toBeNull()
    expect(cell.color).toBe(lens_color(1))
    expect(cell.title).toContain("no parent baseline")
  })

  it("falls back to absolute when the parent has no score for that key", () => {
    // "tiny" exists on both, but the parent has no "pass" if we flip who's who:
    // here the child has no "gone", so scoring the parent against the child
    // leaves that key without a baseline.
    const cell = by_key(strip_cells(data, "parent", "child"), "gone")
    expect(cell.mode).toBe("absolute")
    expect(cell.title).toContain("no parent baseline")
  })

  it("always shows informational keys absolutely, never as a delta", () => {
    const cell = by_key(strip_cells(data, "child", "parent"), "notes")
    expect(cell.mode).toBe("absolute")
    expect(cell.sign).toBeNull()
    expect(cell.title).toContain("informational")
  })

  it("leaves an unscored key blank", () => {
    const cell = by_key(strip_cells(data, "child", "parent"), "gone")
    expect(cell.mode).toBe("empty")
    expect(cell.sign).toBeNull()
    expect(cell.color).toBe(STRIP_EMPTY_COLOR)
    expect(cell.title).toContain("not scored")
  })
})

describe("strip_cell_color", () => {
  it("maps a delta sign to its fill", () => {
    expect(strip_cell_color(1)).toBe(STRIP_BETTER_COLOR)
    expect(strip_cell_color(-1)).toBe(STRIP_WORSE_COLOR)
    expect(strip_cell_color(0)).toBe(STRIP_NEUTRAL_COLOR)
    expect(strip_cell_color(null)).toBe(STRIP_NEUTRAL_COLOR)
  })
})
