import { describe, it, expect } from "vitest"
import type { components } from "$lib/api_schema"
import type { Eval } from "$lib/types"
import {
  MATCH_LABELS,
  MIN_MATCHED_N,
  SHAPE_RATIO_LIMIT,
  build_matched_lens_data,
  build_matched_usage,
  match_param,
  matched_items_by_eval,
  parse_match_param,
  tool_call_source,
  undetectable_difference_pp,
  type RunIndexes,
} from "./run_matching"
import { build_lens_data, score_key_id } from "./score_lens"
import { wilson_interval, interval_half_width_pp } from "./score_intervals"

type EvalRunIndexResponse = components["schemas"]["EvalRunIndexResponse"]
type EvalResultsSummaryResponse =
  components["schemas"]["EvalResultsSummaryResponse"]
type ScoreType = components["schemas"]["TaskOutputRatingType"]
type ScoreDirection = components["schemas"]["ScoreDirection"]

type RowSpec = {
  item: string
  scores?: Record<string, number>
  total_tokens?: number
  input_tokens?: number
  output_tokens?: number
  cost?: number
  latency?: number
}

function index(
  evals: { eval_id: string; rows: RowSpec[] }[],
): EvalRunIndexResponse {
  return {
    split: null,
    evals: evals.map((entry) => ({
      eval_id: entry.eval_id,
      eval_config_id: `${entry.eval_id}_ec`,
      rows: entry.rows.map((row) => ({
        item_id: row.item,
        scores: row.scores ?? {},
        input_tokens: row.input_tokens ?? null,
        output_tokens: row.output_tokens ?? null,
        total_tokens: row.total_tokens ?? null,
        cost: row.cost ?? null,
        total_llm_latency_ms: row.latency ?? null,
      })),
    })),
  }
}

/** Two configs on one eval, over the item lists given. */
function simple_indexes(
  a_items: string[],
  b_items: string[],
  evalId = "e1",
): RunIndexes {
  return {
    a: index([
      {
        eval_id: evalId,
        rows: a_items.map((item) => ({ item, scores: { accuracy: 1 } })),
      },
    ]),
    b: index([
      {
        eval_id: evalId,
        rows: b_items.map((item) => ({ item, scores: { accuracy: 0 } })),
      },
    ]),
  }
}

function summary_of(matched: ReturnType<typeof matched_items_by_eval>) {
  return Object.fromEntries(matched.evals.map((e) => [e.evalId, e]))
}

describe("parse_match_param / match_param", () => {
  it("round-trips the three non-default predicates", () => {
    for (const value of ["shared", "length", "tools"] as const) {
      expect(parse_match_param(value)).toBe(value)
      expect(match_param(value)).toBe(value)
    }
  })

  it("keeps the default out of the URL and treats anything unknown as it", () => {
    expect(match_param("all")).toBeNull()
    expect(parse_match_param(null)).toBe("all")
    expect(parse_match_param("")).toBe("all")
    expect(parse_match_param("all")).toBe("all")
    expect(parse_match_param("SHARED")).toBe("all")
    expect(parse_match_param("similar_vibes")).toBe("all")
  })

  it("names every predicate", () => {
    expect(Object.keys(MATCH_LABELS).sort()).toEqual([
      "all",
      "length",
      "shared",
      "tools",
    ])
  })
})

describe("matched_items_by_eval - shared", () => {
  it("keeps only the items every basis config ran", () => {
    const result = matched_items_by_eval(
      simple_indexes(["i1", "i2", "i3"], ["i2", "i3", "i4"]),
      ["a", "b"],
      "shared",
    )
    expect([...(result.items_by_eval.get("e1") ?? [])].sort()).toEqual([
      "i2",
      "i3",
    ])
    const e1 = summary_of(result)["e1"]
    expect(e1.universe_by_config).toEqual({ a: 3, b: 3 })
    expect(e1.shared).toBe(2)
    expect(e1.matched).toBe(2)
    expect(e1.missing_shape).toBe(0)
  })

  it("keeps the union under `all`, which is today's basis", () => {
    const result = matched_items_by_eval(
      simple_indexes(["i1", "i2"], ["i3"]),
      ["a", "b"],
      "all",
    )
    expect([...(result.items_by_eval.get("e1") ?? [])].sort()).toEqual([
      "i1",
      "i2",
      "i3",
    ])
    // The shared count is still reported: it is what the banner's caveat is
    // about, and it has to be readable BEFORE the reader switches predicate.
    expect(summary_of(result)["e1"].shared).toBe(0)
  })

  it("zeroes out only the eval with no overlap", () => {
    const indexes: RunIndexes = {
      a: index([
        { eval_id: "e1", rows: [{ item: "i1" }] },
        { eval_id: "e2", rows: [{ item: "j1" }] },
      ]),
      b: index([
        { eval_id: "e1", rows: [{ item: "i9" }] },
        { eval_id: "e2", rows: [{ item: "j1" }] },
      ]),
    }
    const result = matched_items_by_eval(indexes, ["a", "b"], "shared")
    expect(result.items_by_eval.get("e1")?.size).toBe(0)
    expect([...(result.items_by_eval.get("e2") ?? [])]).toEqual(["j1"])
  })

  it("is the identity on a basis of one, and says which predicate it applied", () => {
    const result = matched_items_by_eval(
      simple_indexes(["i1", "i2"], []),
      ["a"],
      "tools",
    )
    expect(result.requested).toBe("tools")
    expect(result.applied).toBe("all")
    expect(result.items_by_eval.get("e1")?.size).toBe(2)
  })

  it("counts an eval a basis config has never been run against as zero", () => {
    const indexes: RunIndexes = {
      a: index([{ eval_id: "e1", rows: [{ item: "i1" }] }]),
      b: index([]),
    }
    const result = matched_items_by_eval(indexes, ["a", "b"], "shared")
    expect(summary_of(result)["e1"].universe_by_config).toEqual({ a: 1, b: 0 })
    expect(result.items_by_eval.get("e1")?.size).toBe(0)
  })
})

describe("matched_items_by_eval - length", () => {
  const length_indexes = (
    a: Record<string, number | null>,
    b: Record<string, number | null>,
  ): RunIndexes => ({
    a: index([
      {
        eval_id: "e1",
        rows: Object.entries(a).map(([item, tokens]) => ({
          item,
          scores: { accuracy: 1 },
          ...(tokens === null ? {} : { total_tokens: tokens }),
        })),
      },
    ]),
    b: index([
      {
        eval_id: "e1",
        rows: Object.entries(b).map(([item, tokens]) => ({
          item,
          scores: { accuracy: 0 },
          ...(tokens === null ? {} : { total_tokens: tokens }),
        })),
      },
    ]),
  })

  it("keeps a pair exactly at the tolerance and drops the one just past it", () => {
    const result = matched_items_by_eval(
      length_indexes(
        { at_limit: 100, past_limit: 100 },
        { at_limit: 100 * SHAPE_RATIO_LIMIT, past_limit: 151 },
      ),
      ["a", "b"],
      "length",
    )
    expect([...(result.items_by_eval.get("e1") ?? [])]).toEqual(["at_limit"])
  })

  it("compares max against min, whichever config is the larger", () => {
    const result = matched_items_by_eval(
      length_indexes({ i1: 200 }, { i1: 150 }),
      ["a", "b"],
      "length",
    )
    expect([...(result.items_by_eval.get("e1") ?? [])]).toEqual(["i1"])
  })

  it("drops an item whose floor is zero - there is no ratio to be inside", () => {
    const result = matched_items_by_eval(
      length_indexes({ zero: 0, both_zero: 0 }, { zero: 100, both_zero: 0 }),
      ["a", "b"],
      "length",
    )
    expect(result.items_by_eval.get("e1")?.size).toBe(0)
  })

  it("drops an item one config has no length for, and counts it", () => {
    const result = matched_items_by_eval(
      length_indexes({ i1: 100, i2: 100 }, { i1: 110, i2: null }),
      ["a", "b"],
      "length",
    )
    expect([...(result.items_by_eval.get("e1") ?? [])]).toEqual(["i1"])
    const e1 = summary_of(result)["e1"]
    expect(e1.shared).toBe(2)
    expect(e1.matched).toBe(1)
    expect(e1.missing_shape).toBe(1)
  })

  it("names a basis config that has no lengths at all", () => {
    const result = matched_items_by_eval(
      length_indexes({ i1: 100 }, { i1: null }),
      ["a", "b"],
      "length",
    )
    expect(result.configs_missing_shape).toEqual(["b"])
  })

  it("implies shared: an item only one config ran is never length-matched", () => {
    const result = matched_items_by_eval(
      length_indexes({ i1: 100, solo: 100 }, { i1: 100 }),
      ["a", "b"],
      "length",
    )
    expect([...(result.items_by_eval.get("e1") ?? [])]).toEqual(["i1"])
  })
})

describe("tool_call_source and the tools predicate", () => {
  const metric_metas = (evalId: string, keys: string[]) =>
    keys.map((scoreKey) => ({
      evalId,
      evalName: evalId,
      scoreKey,
      type: "custom" as ScoreType,
      direction: "lower_is_better" as ScoreDirection,
    }))

  it("finds tool_calls on an all-custom eval", () => {
    const source = tool_call_source([
      ...metric_metas("metrics", ["tool_calls", "cost_usd"]),
    ])
    expect(source).toEqual({ evalId: "metrics", scoreKey: "tool_calls" })
  })

  it("ignores a tool_calls key on a criterion eval", () => {
    // A bounded score anywhere on the eval makes it a criterion eval, and its
    // keys belong to the quality track whatever they are named.
    const source = tool_call_source([
      ...metric_metas("judge", ["tool_calls"]),
      {
        evalId: "judge",
        evalName: "judge",
        scoreKey: "passed",
        type: "pass_fail" as ScoreType,
        direction: "higher_is_better" as ScoreDirection,
      },
    ])
    expect(source).toBeNull()
  })

  it("returns null when nothing records tool calls", () => {
    expect(tool_call_source([])).toBeNull()
    expect(tool_call_source(metric_metas("metrics", ["cost_usd"]))).toBeNull()
  })

  it("picks the metrics eval with the most rows across the basis", () => {
    const indexes: RunIndexes = {
      a: index([
        {
          eval_id: "m_thin",
          rows: [{ item: "i1", scores: { tool_calls: 1 } }],
        },
        {
          eval_id: "m_fat",
          rows: [
            { item: "i1", scores: { tool_calls: 1 } },
            { item: "i2", scores: { tool_calls: 2 } },
          ],
        },
      ]),
    }
    const metas = [
      ...metric_metas("m_thin", ["tool_calls"]),
      ...metric_metas("m_fat", ["tool_calls"]),
    ]
    expect(tool_call_source(metas, indexes)?.evalId).toBe("m_fat")
    // With no coverage to weigh, the choice is at least deterministic
    expect(tool_call_source(metas)?.evalId).toBe("m_fat")
    expect(tool_call_source([...metas].reverse())?.evalId).toBe("m_fat")
  })

  it("reads tool_calls from the metrics eval when matching a judge's items", () => {
    const with_tools = (
      configId: string,
      judge: Record<string, number>,
      tools: Record<string, number>,
    ) => ({
      [configId]: index([
        {
          eval_id: "judge",
          rows: Object.entries(judge).map(([item, score]) => ({
            item,
            scores: { passed: score },
          })),
        },
        {
          eval_id: "metrics",
          rows: Object.entries(tools).map(([item, calls]) => ({
            item,
            scores: { tool_calls: calls },
          })),
        },
      ]),
    })
    const indexes: RunIndexes = {
      ...with_tools("a", { i1: 1, i2: 1 }, { i1: 10, i2: 10 }),
      ...with_tools("b", { i1: 0, i2: 0 }, { i1: 12, i2: 40 }),
    }
    const result = matched_items_by_eval(indexes, ["a", "b"], "tools", {
      evalId: "metrics",
      scoreKey: "tool_calls",
    })
    // i1 is 10 vs 12 (1.2x, in); i2 is 10 vs 40 (4x, out)
    expect([...(result.items_by_eval.get("judge") ?? [])]).toEqual(["i1"])
  })

  it("names a basis config with no tool-call rows and matches nothing", () => {
    const indexes: RunIndexes = {
      a: index([
        { eval_id: "judge", rows: [{ item: "i1", scores: { passed: 1 } }] },
        {
          eval_id: "metrics",
          rows: [{ item: "i1", scores: { tool_calls: 5 } }],
        },
      ]),
      b: index([
        { eval_id: "judge", rows: [{ item: "i1", scores: { passed: 0 } }] },
      ]),
    }
    const result = matched_items_by_eval(indexes, ["a", "b"], "tools", {
      evalId: "metrics",
      scoreKey: "tool_calls",
    })
    expect(result.items_by_eval.get("judge")?.size).toBe(0)
    expect(result.configs_missing_shape).toEqual(["b"])
    expect(summary_of(result)["judge"].missing_shape).toBe(1)
  })

  it("matches nothing when the task has no tool-call source at all", () => {
    const result = matched_items_by_eval(
      simple_indexes(["i1"], ["i1"]),
      ["a", "b"],
      "tools",
      null,
    )
    expect(result.items_by_eval.get("e1")?.size).toBe(0)
    expect(result.configs_missing_shape.sort()).toEqual(["a", "b"])
  })
})

describe("build_matched_lens_data", () => {
  const lens_of = (
    evals: {
      id: string
      name: string
      scores: { name: string; type: ScoreType }[]
    }[],
  ) => {
    const summary: EvalResultsSummaryResponse = {
      evals_by_id: Object.fromEntries(
        evals.map((e) => [
          e.id,
          {
            name: e.name,
            output_score_keys: e.scores.map((s) => s.name),
            default_judge_config_id: null,
            dataset_size: 10,
          },
        ]),
      ),
      run_configs_by_id: {},
      scores_by_run_config_by_eval: {},
      split: null,
    } as unknown as EvalResultsSummaryResponse
    const eval_models = evals.map(
      (e) =>
        ({
          id: e.id,
          name: e.name,
          output_scores: e.scores.map((s) => ({
            name: s.name,
            type: s.type,
            instruction: "",
            direction: "higher_is_better",
          })),
        }) as unknown as Eval,
    )
    return build_lens_data(summary, eval_models)
  }

  it("means and counts the matched rows only", () => {
    const indexes: RunIndexes = {
      a: index([
        {
          eval_id: "e1",
          rows: [
            { item: "i1", scores: { accuracy: 1 } },
            { item: "i2", scores: { accuracy: 0 } },
            // Not matched: must not move the mean
            { item: "i3", scores: { accuracy: 1 } },
          ],
        },
      ]),
      b: index([
        {
          eval_id: "e1",
          rows: [
            { item: "i1", scores: { accuracy: 1 } },
            { item: "i2", scores: { accuracy: 1 } },
          ],
        },
      ]),
    }
    const lens = lens_of([
      {
        id: "e1",
        name: "E1",
        scores: [{ name: "accuracy", type: "pass_fail" }],
      },
    ])
    const matched = new Map([["e1", new Set(["i1", "i2"])]])
    const data = build_matched_lens_data(lens, indexes, ["a", "b"], matched)

    const key = score_key_id("e1", "accuracy")
    expect(data.raw.get("a")?.get(key)).toBeCloseTo(0.5)
    expect(data.raw.get("b")?.get(key)).toBeCloseTo(1)
    expect(data.counts.get("a")?.get(key)).toBe(2)
    expect(data.counts.get("b")?.get(key)).toBe(2)
  })

  it("reproduces build_lens_data's means and counts when nothing is filtered out", () => {
    // The parity that makes the feature safe: with identical item sets and the
    // `shared` predicate, the matched numbers ARE the unfiltered numbers. Any
    // difference the reader sees under a predicate is filtering, not a second
    // implementation of the mean drifting from the server's.
    const items = ["i1", "i2", "i3", "i4"]
    const a_scores = [1, 0, 1, 1]
    const b_scores = [0, 0, 1, 0]
    const indexes: RunIndexes = {
      a: index([
        {
          eval_id: "e1",
          rows: items.map((item, i) => ({
            item,
            scores: { accuracy: a_scores[i] },
          })),
        },
      ]),
      b: index([
        {
          eval_id: "e1",
          rows: items.map((item, i) => ({
            item,
            scores: { accuracy: b_scores[i] },
          })),
        },
      ]),
    }

    // The server's own aggregate over the same rows
    const summary = {
      evals_by_id: {
        e1: {
          name: "E1",
          output_score_keys: ["accuracy"],
          default_judge_config_id: null,
          dataset_size: 4,
        },
      },
      run_configs_by_id: {},
      scores_by_run_config_by_eval: {
        a: {
          e1: {
            mean_scores: { accuracy: 0.75 },
            percent_complete: 1,
            n_used_by_score_key: { accuracy: 4 },
          },
        },
        b: {
          e1: {
            mean_scores: { accuracy: 0.25 },
            percent_complete: 1,
            n_used_by_score_key: { accuracy: 4 },
          },
        },
      },
      split: null,
    } as unknown as EvalResultsSummaryResponse
    const unfiltered = build_lens_data(summary, [
      {
        id: "e1",
        name: "E1",
        output_scores: [
          {
            name: "accuracy",
            type: "pass_fail",
            instruction: "",
            direction: "higher_is_better",
          },
        ],
      } as unknown as Eval,
    ])

    const matched = matched_items_by_eval(indexes, ["a", "b"], "shared")
    expect(matched.items_by_eval.get("e1")?.size).toBe(4)
    const data = build_matched_lens_data(
      unfiltered,
      indexes,
      ["a", "b"],
      matched.items_by_eval,
    )

    const key = score_key_id("e1", "accuracy")
    for (const id of ["a", "b"]) {
      expect(data.raw.get(id)?.get(key)).toBeCloseTo(
        unfiltered.raw.get(id)?.get(key) as number,
      )
      expect(data.counts.get(id)?.get(key)).toBe(
        unfiltered.counts.get(id)?.get(key),
      )
      // ...and pass_fail scales against its own range either way
      expect(data.normalized.get(id)?.get(key)).toBeCloseTo(
        unfiltered.normalized.get(id)?.get(key) as number,
      )
    }
  })

  it("min-max scales a custom key across the basis and flips lower_is_better", () => {
    const indexes: RunIndexes = {
      a: index([
        { eval_id: "m", rows: [{ item: "i1", scores: { tool_calls: 4 } }] },
      ]),
      b: index([
        { eval_id: "m", rows: [{ item: "i1", scores: { tool_calls: 12 } }] },
      ]),
      c: index([
        { eval_id: "m", rows: [{ item: "i1", scores: { tool_calls: 8 } }] },
      ]),
    }
    const lens = {
      keyMetas: [
        {
          evalId: "m",
          evalName: "Metrics",
          scoreKey: "tool_calls",
          type: "custom" as ScoreType,
          direction: "lower_is_better" as ScoreDirection,
        },
      ],
      raw: new Map(),
      normalized: new Map(),
      counts: new Map(),
      percentComplete: new Map(),
    }
    const matched = new Map([["m", new Set(["i1"])]])
    const data = build_matched_lens_data(
      lens,
      indexes,
      ["a", "b", "c"],
      matched,
    )
    const key = score_key_id("m", "tool_calls")
    // Fewest calls is best under lower_is_better
    expect(data.normalized.get("a")?.get(key)).toBeCloseTo(1)
    expect(data.normalized.get("b")?.get(key)).toBeCloseTo(0)
    expect(data.normalized.get("c")?.get(key)).toBeCloseTo(0.5)
  })

  it("gives every basis config the same custom value 0.5, never 0 or 1", () => {
    const indexes: RunIndexes = {
      a: index([
        { eval_id: "m", rows: [{ item: "i1", scores: { tool_calls: 7 } }] },
      ]),
      b: index([
        { eval_id: "m", rows: [{ item: "i1", scores: { tool_calls: 7 } }] },
      ]),
    }
    const lens = {
      keyMetas: [
        {
          evalId: "m",
          evalName: "Metrics",
          scoreKey: "tool_calls",
          type: "custom" as ScoreType,
          direction: "higher_is_better" as ScoreDirection,
        },
      ],
      raw: new Map(),
      normalized: new Map(),
      counts: new Map(),
      percentComplete: new Map(),
    }
    const data = build_matched_lens_data(
      lens,
      indexes,
      ["a", "b"],
      new Map([["m", new Set(["i1"])]]),
    )
    const key = score_key_id("m", "tool_calls")
    expect(data.normalized.get("a")?.get(key)).toBeCloseTo(0.5)
    expect(data.normalized.get("b")?.get(key)).toBeCloseTo(0.5)
  })

  it("carries percentComplete and keyMetas over unfiltered", () => {
    const lens = lens_of([
      {
        id: "e1",
        name: "E1",
        scores: [{ name: "accuracy", type: "pass_fail" }],
      },
    ])
    lens.percentComplete.set("a", new Map([["e1", 0.4]]))
    const data = build_matched_lens_data(
      lens,
      { a: index([{ eval_id: "e1", rows: [{ item: "i1", scores: {} }] }]) },
      ["a"],
      new Map([["e1", new Set(["i1"])]]),
    )
    expect(data.percentComplete.get("a")?.get("e1")).toBe(0.4)
    expect(data.keyMetas).toBe(lens.keyMetas)
  })

  it("leaves a key with no matched rows absent rather than zero", () => {
    const lens = lens_of([
      {
        id: "e1",
        name: "E1",
        scores: [{ name: "accuracy", type: "pass_fail" }],
      },
    ])
    const data = build_matched_lens_data(
      lens,
      { a: index([{ eval_id: "e1", rows: [{ item: "i1", scores: {} }] }]) },
      ["a"],
      new Map([["e1", new Set(["i1"])]]),
    )
    expect(
      data.raw.get("a")?.get(score_key_id("e1", "accuracy")),
    ).toBeUndefined()
    expect(data.counts.get("a")?.size).toBe(0)
  })

  it("counts per key, so a key missing from some rows has its own smaller n", () => {
    const indexes: RunIndexes = {
      a: index([
        {
          eval_id: "e1",
          rows: [
            { item: "i1", scores: { accuracy: 1, tone: 1 } },
            { item: "i2", scores: { accuracy: 0 } },
          ],
        },
      ]),
    }
    const lens = lens_of([
      {
        id: "e1",
        name: "E1",
        scores: [
          { name: "accuracy", type: "pass_fail" },
          { name: "tone", type: "pass_fail" },
        ],
      },
    ])
    const data = build_matched_lens_data(
      lens,
      indexes,
      ["a"],
      new Map([["e1", new Set(["i1", "i2"])]]),
    )
    expect(data.counts.get("a")?.get(score_key_id("e1", "accuracy"))).toBe(2)
    expect(data.counts.get("a")?.get(score_key_id("e1", "tone"))).toBe(1)
  })
})

describe("build_matched_usage", () => {
  it("weighs a conversation once however many evals scored it", () => {
    // The same item appears under three evals with the same usage - trace
    // reuse. The server's mean_usage counts it three times; this counts the
    // conversation.
    const rows = (item: string, cost: number) => ({
      item,
      scores: {},
      cost,
      total_tokens: cost * 1000,
      latency: cost * 100,
    })
    const indexes: RunIndexes = {
      a: index([
        { eval_id: "e1", rows: [rows("i1", 1), rows("i2", 3)] },
        { eval_id: "e2", rows: [rows("i1", 1)] },
        { eval_id: "e3", rows: [rows("i1", 1)] },
      ]),
    }
    const matched = new Map([
      ["e1", new Set(["i1", "i2"])],
      ["e2", new Set(["i1"])],
      ["e3", new Set(["i1"])],
    ])
    const usage = build_matched_usage(indexes, ["a"], matched)
    expect(usage.get("a")?.n_conversations).toBe(2)
    // Deduped: (1 + 3) / 2. Weighted by eval it would be (1+3+1+1)/4 = 1.5
    expect(usage.get("a")?.mean_cost).toBeCloseTo(2)
    expect(usage.get("a")?.mean_total_tokens).toBeCloseTo(2000)
    expect(usage.get("a")?.mean_latency_ms).toBeCloseTo(200)
  })

  it("nulls a metric fewer than half the matched conversations recorded", () => {
    const indexes: RunIndexes = {
      a: index([
        {
          eval_id: "e1",
          rows: [
            { item: "i1", cost: 1, total_tokens: 10 },
            { item: "i2", total_tokens: 20 },
            { item: "i3", total_tokens: 30 },
          ],
        },
      ]),
    }
    const usage = build_matched_usage(
      indexes,
      ["a"],
      new Map([["e1", new Set(["i1", "i2", "i3"])]]),
    )
    expect(usage.get("a")?.mean_cost).toBeNull()
    expect(usage.get("a")?.mean_total_tokens).toBeCloseTo(20)
  })

  it("keeps a metric exactly half the conversations recorded", () => {
    const indexes: RunIndexes = {
      a: index([
        {
          eval_id: "e1",
          rows: [{ item: "i1", cost: 2 }, { item: "i2" }],
        },
      ]),
    }
    const usage = build_matched_usage(
      indexes,
      ["a"],
      new Map([["e1", new Set(["i1", "i2"])]]),
    )
    expect(usage.get("a")?.mean_cost).toBeCloseTo(2)
  })

  it("reports zero conversations rather than zero cost when nothing matched", () => {
    const usage = build_matched_usage(
      { a: index([{ eval_id: "e1", rows: [{ item: "i1", cost: 5 }] }]) },
      ["a"],
      new Map([["e1", new Set<string>()]]),
    )
    expect(usage.get("a")?.n_conversations).toBe(0)
    expect(usage.get("a")?.mean_cost).toBeNull()
  })

  it("gives every basis config an entry, including one with no index", () => {
    const usage = build_matched_usage({}, ["a", "b"], new Map())
    expect([...usage.keys()].sort()).toEqual(["a", "b"])
    expect(usage.get("a")?.n_conversations).toBe(0)
  })
})

describe("undetectable_difference_pp", () => {
  it("derives the figure from the Wilson half-width at the actual n", () => {
    for (const n of [7, 10, 25, 140]) {
      const interval = wilson_interval(0.5, n)
      const expected = Math.max(
        5,
        Math.round((interval_half_width_pp(interval!) * 2) / 5) * 5,
      )
      expect(undetectable_difference_pp(n)).toBe(expected)
    }
  })

  it("shrinks as n grows, and is null with no runs", () => {
    const small = undetectable_difference_pp(7) as number
    const large = undetectable_difference_pp(140) as number
    expect(small).toBeGreaterThan(large)
    expect(undetectable_difference_pp(0)).toBeNull()
  })

  it("is well past the warning threshold at the threshold itself", () => {
    // MIN_MATCHED_N is set where the interval stops being informative; the
    // phrase the chip prints has to agree with that choice.
    expect(undetectable_difference_pp(MIN_MATCHED_N)).toBeGreaterThan(40)
  })
})
