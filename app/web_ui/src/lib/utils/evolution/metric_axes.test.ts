import { describe, it, expect } from "vitest"
import type { components } from "$lib/api_schema"
import type { ScoreKeyMeta } from "./score_lens"
import {
  COST_KEY,
  CORE_USAGE_KEYS,
  DEFAULT_METRIC_AXIS_COUNT,
  INPUT_TOKENS_KEY,
  LATENCY_KEY,
  METRIC_FAMILIES,
  METRIC_FAMILY_LABELS,
  OUTPUT_TOKENS_KEY,
  TOTAL_TOKENS_KEY,
  USAGE_METRIC_AXES,
  build_metric_axes,
  default_metric_axis_keys,
  directionless_key_count,
  format_metric_value,
  criterion_key_metas,
  infer_metric_unit,
  is_metric_eval,
  known_metric_axis_keys,
  metric_eval_ids,
  wrap_axis_label,
  metric_family_bands,
  metric_row_info,
  usage_row_family,
  fit_radar,
  MIN_RADAR_RADIUS,
  type MetricAxis,
  type RadarAxisLabel,
  type MetricFamily,
} from "./metric_axes"

type ScoreDirection = components["schemas"]["ScoreDirection"]
type ScoreType = components["schemas"]["TaskOutputRatingType"]

// A metric: unbounded, so its eval is a metrics eval
function meta(
  evalId: string,
  evalName: string,
  scoreKey: string,
  direction: ScoreDirection,
): ScoreKeyMeta {
  return { evalId, evalName, scoreKey, type: "custom", direction }
}

// A graded criterion: a bounded score type, so its eval is a criterion eval
function criterion(
  evalId: string,
  evalName: string,
  scoreKey: string,
  direction: ScoreDirection = "higher_is_better",
  type: ScoreType = "pass_fail",
): ScoreKeyMeta {
  return { evalId, evalName, scoreKey, type, direction }
}

// A task shaped like the real one: pass/fail criterion evals, an efficiency
// eval of unbounded metrics pointing both ways, and a latency eval whose keys
// are all authored informational.
const KEY_METAS: ScoreKeyMeta[] = [
  criterion("q1", "Quality", "false_done_claim"),
  criterion("q2", "Schema", "refetched_schema"),
  meta("e1", "Efficiency", "tool_calls", "lower_is_better"),
  meta("e1", "Efficiency", "llm_calls", "lower_is_better"),
  meta("e1", "Efficiency", "skill_reads_repeat", "lower_is_better"),
  meta("e1", "Efficiency", "cost_usd", "lower_is_better"),
  meta("e1", "Efficiency", "input_tokens", "lower_is_better"),
  meta("e1", "Efficiency", "total_tokens", "lower_is_better"),
  meta("e1", "Efficiency", "cache_hit_rate", "higher_is_better"),
  meta("e1", "Efficiency", "cached_tokens", "informational"),
  meta("e1", "Efficiency", "user_turns", "informational"),
  meta("l1", "Latency", "latency_ms_total", "informational"),
  meta("l1", "Latency", "latency_ms_turn1", "informational"),
  meta("l1", "Latency", "latency_ms_turn2", "informational"),
  meta("l1", "Latency", "latency_ms_per_call", "informational"),
]

function labels(axes: MetricAxis[]): string[] {
  return axes.map((axis) => axis.label)
}

describe("build_metric_axes", () => {
  it("always offers the native usage rollup, even with no evals at all", () => {
    const axes = build_metric_axes([])
    expect(axes.map((axis) => axis.key).sort()).toEqual(
      USAGE_METRIC_AXES.map((axis) => axis.key).sort(),
    )
    expect(axes.every((axis) => axis.source === "usage")).toBe(true)
  })

  it("does not mutate the input", () => {
    const input = [...KEY_METAS]
    build_metric_axes(input)
    expect(input).toEqual(KEY_METAS)
  })

  it("is stable across renders no matter what order the keys arrive in", () => {
    const shuffled = [...KEY_METAS].reverse()
    expect(build_metric_axes(shuffled)).toEqual(build_metric_axes(KEY_METAS))
  })
})

// The regression: the two radars used to be partitioned by DIRECTION, which
// reads "lower is better" as "this is a metric". That holds only while every
// metric is better small. cache_hit_rate is not, and under the old rule a cost
// metric was drawn on the quality ring between the pass/fail judges.
describe("the two radars partition by eval, not by direction", () => {
  it("sends a higher-is-better metric to the performance radar", () => {
    const keys = build_metric_axes(KEY_METAS).map((axis) => axis.key)
    expect(keys).toContain("e1::cache_hit_rate")
    // ...and keeps it off the quality radar's key set
    expect(
      criterion_key_metas(KEY_METAS).map((meta) => meta.scoreKey),
    ).not.toContain("cache_hit_rate")
  })

  it("keeps every criterion key off the performance radar", () => {
    const keys = build_metric_axes(KEY_METAS).map((axis) => axis.key)
    expect(keys).not.toContain("q1::false_done_claim")
    expect(keys).not.toContain("q2::refetched_schema")
  })

  it("gives the quality radar exactly the criterion keys", () => {
    expect(
      criterion_key_metas(KEY_METAS).map(
        (meta) => `${meta.evalId}::${meta.scoreKey}`,
      ),
    ).toEqual(["q1::false_done_claim", "q2::refetched_schema"])
  })

  it("routes a whole eval at a time, whichever way its keys point", () => {
    const ids = metric_eval_ids(KEY_METAS)
    expect([...ids].sort()).toEqual(["e1", "l1"])
    // e1 holds lower-is-better, higher-is-better and informational keys alike
    expect(is_metric_eval(KEY_METAS.filter((m) => m.evalId === "e1"))).toBe(
      true,
    )
    expect(is_metric_eval(KEY_METAS.filter((m) => m.evalId === "q1"))).toBe(
      false,
    )
  })

  it("tells the two apart by whether the score type has a range", () => {
    // A bounded type is a grade with a best value of its own; custom is an
    // open-ended quantity that can only be compared across run configs
    expect(
      is_metric_eval([meta("e", "E", "tool_calls", "lower_is_better")]),
    ).toBe(true)
    for (const type of ["pass_fail", "pass_fail_critical", "five_star"]) {
      expect(
        is_metric_eval([
          criterion("c", "C", "graded", "higher_is_better", type as ScoreType),
        ]),
      ).toBe(false)
    }
    // An unmatched key has a null type, which is not a positive metric signal
    expect(
      is_metric_eval([
        {
          evalId: "u",
          evalName: "U",
          scoreKey: "x",
          type: null,
          direction: "higher_is_better",
        },
      ]),
    ).toBe(false)
    expect(is_metric_eval([])).toBe(false)
  })

  it("treats a custom score beside graded ones as part of that criterion eval", () => {
    // One eval, mixed: the graded score makes it a criterion eval, so its
    // custom key goes with it rather than defecting to the metrics chart
    const mixed: ScoreKeyMeta[] = [
      criterion("m1", "Mixed", "passes"),
      meta("m1", "Mixed", "tool_calls", "lower_is_better"),
    ]
    expect(is_metric_eval(mixed)).toBe(false)
    expect(build_metric_axes(mixed).map((axis) => axis.key)).not.toContain(
      "m1::tool_calls",
    )
    expect(criterion_key_metas(mixed)).toEqual(mixed)
  })
})

// Feedback 2: the usage rollup and the eval score keys measure the same
// quantities, and the chart used to plot both - "Cost" next to "Cost Usd",
// "Total Tokens" twice.
describe("build_metric_axes: one axis per quantity", () => {
  it("never plots the same quantity twice", () => {
    const axes = build_metric_axes(KEY_METAS)
    const quantities = axes.map((axis) => axis.quantity)
    expect(new Set(quantities).size).toBe(quantities.length)
  })

  it("never repeats an axis label", () => {
    const axes = build_metric_axes(KEY_METAS)
    expect(new Set(labels(axes)).size).toBe(axes.length)
  })

  it("keeps the usage rollup and drops the score key restating it", () => {
    const keys = build_metric_axes(KEY_METAS).map((axis) => axis.key)
    // Cost, total tokens, input tokens and total latency all arrive twice
    expect(keys).toContain(COST_KEY)
    expect(keys).not.toContain("e1::cost_usd")
    expect(keys).toContain(TOTAL_TOKENS_KEY)
    expect(keys).not.toContain("e1::total_tokens")
    expect(keys).toContain(INPUT_TOKENS_KEY)
    expect(keys).not.toContain("e1::input_tokens")
    expect(keys).toContain(LATENCY_KEY)
    expect(keys).not.toContain("l1::latency_ms_total")
  })

  it("matches by what is measured, not by label string", () => {
    // cost_usd and mean_cost share no characters; they are the same quantity
    const axes = build_metric_axes([
      meta("e1", "Efficiency", "cost_usd", "lower_is_better"),
    ])
    expect(axes.filter((axis) => axis.quantity === "cost").length).toBe(1)
  })

  it("keeps a metric the rollup does not report", () => {
    const keys = build_metric_axes(KEY_METAS).map((axis) => axis.key)
    expect(keys).toContain("e1::tool_calls")
    expect(keys).toContain("e1::llm_calls")
    expect(keys).toContain("e1::skill_reads_repeat")
    expect(keys).toContain("l1::latency_ms_turn1")
  })

  it("falls back to the score key when the rollup has no numbers for it", () => {
    // A provider that never reports cost leaves the rollup's Cost axis empty,
    // and a code eval computing cost_usd is then the only real cost data there
    // is. Deduplicating must not hide it behind an axis that cannot be drawn.
    const has_value = (key: string) => key !== COST_KEY
    const axes = build_metric_axes(KEY_METAS, has_value)
    const keys = axes.map((axis) => axis.key)
    expect(keys).toContain("e1::cost_usd")
    expect(keys).not.toContain(COST_KEY)
    // and it is still the Cost axis, in the cost family, named the same way
    const cost = axes.find((axis) => axis.quantity === "cost")
    expect(cost?.label).toBe("Cost Efficiency")
    expect(cost?.family).toBe("cost")
  })

  it("prefers the rollup while nothing has loaded, so the axes do not churn", () => {
    const nothing_loaded = () => false
    expect(
      build_metric_axes(KEY_METAS, nothing_loaded).map((axis) => axis.key),
    ).toEqual(build_metric_axes(KEY_METAS).map((axis) => axis.key))
  })
})

describe("known_metric_axis_keys", () => {
  it("keeps both sources for a quantity, so a saved URL survives dedup", () => {
    const known = known_metric_axis_keys(KEY_METAS)
    // Restored before the usage rollup has been fetched, a selection of
    // e1::cost_usd must not be judged against "the rollup always wins"
    expect(known.has("e1::cost_usd")).toBe(true)
    expect(known.has(COST_KEY)).toBe(true)
    expect(known.has("l1::latency_ms_total")).toBe(true)
    expect(known.has(LATENCY_KEY)).toBe(true)
  })

  it("still rejects a key that is not an axis at all", () => {
    const known = known_metric_axis_keys(KEY_METAS)
    // A quality score, an unpointable informational key, and a stale id
    expect(known.has("q1::false_done_claim")).toBe(false)
    expect(known.has("e1::user_turns")).toBe(false)
    expect(known.has("gone::vanished")).toBe(false)
  })

  it("is a superset of whatever the chart ends up plotting", () => {
    const known = known_metric_axis_keys(KEY_METAS)
    for (const axis of build_metric_axes(KEY_METAS)) {
      expect(known.has(axis.key)).toBe(true)
    }
    for (const axis of build_metric_axes(KEY_METAS, () => false)) {
      expect(known.has(axis.key)).toBe(true)
    }
  })
})

// Feedback 3: tokens used to be scattered across three arcs of the circle.
describe("build_metric_axes: families are contiguous", () => {
  it("gives each family a single unbroken arc", () => {
    const families = build_metric_axes(KEY_METAS).map((axis) => axis.family)
    const seen = new Set<string>()
    let previous: string | null = null
    for (const family of families) {
      if (family !== previous) {
        expect(seen.has(family)).toBe(false)
        seen.add(family)
        previous = family
      }
    }
    expect(seen.size).toBeGreaterThan(1)
  })

  it("orders the families the same way every time", () => {
    const families = build_metric_axes(KEY_METAS).map((axis) => axis.family)
    const order = [...new Set(families)]
    expect(order).toEqual(["cost", "tokens", "calls", "speed"])
  })

  it("puts every token metric next to every other one", () => {
    const axes = build_metric_axes(KEY_METAS)
    const indexes = axes
      .map((axis, index) => ({ axis, index }))
      .filter((entry) => entry.axis.family === "tokens")
      .map((entry) => entry.index)
    expect(indexes.length).toBeGreaterThan(2)
    expect(Math.max(...indexes) - Math.min(...indexes)).toBe(indexes.length - 1)
  })

  it("names every family it can produce", () => {
    for (const family of METRIC_FAMILIES) {
      expect(METRIC_FAMILY_LABELS[family]).toBeTruthy()
    }
  })

  it("files an unrecognised metric under Other, at the end", () => {
    const axes = build_metric_axes([
      ...KEY_METAS,
      meta("e1", "Efficiency", "wasted_retries", "lower_is_better"),
    ])
    expect(axes[axes.length - 1].family).toBe("other")
  })
})

// Feedback 5: an axis called "Skill Reads Repeat" with a point far from the
// centre reads as "lots of repeats" when it means the opposite.
describe("build_metric_axes: every label is a virtue", () => {
  const axes = build_metric_axes(KEY_METAS)

  it("names the quality being measured, not the cost being counted", () => {
    expect(labels(axes)).toEqual([
      "Cost Efficiency",
      "Token Economy",
      "Cache Reuse",
      "Cache Hit Rate",
      "Input Token Economy",
      "Output Token Economy",
      "Tool Call Economy",
      "LLM Call Economy",
      "Skill Read Efficiency",
      "Speed",
      "Turn 1 Speed",
      "Turn 2 Speed",
      "Per-Call Speed",
    ])
  })

  it("never phrases an axis as a negation", () => {
    for (const label of labels(axes)) {
      expect(label).not.toMatch(/\b(no|not|fewer|less|avoids?|without)\b/i)
    }
  })

  it("writes acronyms as acronyms", () => {
    expect(labels(axes)).toContain("LLM Call Economy")
    expect(labels(axes)).not.toContain("Llm Call Economy")
  })

  it("keeps the plain quantity name for printing values", () => {
    const by_quantity = new Map(axes.map((axis) => [axis.quantity, axis]))
    expect(by_quantity.get("cost")?.valueLabel).toBe("Cost")
    expect(by_quantity.get("llm_calls")?.valueLabel).toBe("LLM Calls")
    expect(by_quantity.get("skill_reads_repeat")?.valueLabel).toBe(
      "Repeated Skill Reads",
    )
    expect(by_quantity.get("latency")?.valueLabel).toBe("Total Latency")
  })

  it("derives a virtue for a metric it has never heard of", () => {
    const derived = build_metric_axes([
      meta("e1", "Efficiency", "wasted_retries", "lower_is_better"),
    ]).find((axis) => axis.key === "e1::wasted_retries")
    expect(derived?.label).toBe("Wasted Retries Efficiency")
    expect(derived?.valueLabel).toBe("Wasted Retries")
    expect(derived?.better).toBe("lower")
  })
})

// Feedback: check each metric's true direction rather than assuming they are
// all lower-is-better.
describe("build_metric_axes: direction", () => {
  it("scores both cache metrics the other way round - more is better", () => {
    const rate = build_metric_axes([
      meta("e1", "Efficiency", "cache_hit_rate", "informational"),
    ]).find((axis) => axis.quantity === "cache_hit_rate")
    expect(rate?.better).toBe("higher")
    expect(rate?.label).toBe("Cache Hit Rate")

    const cached = build_metric_axes(KEY_METAS).find(
      (axis) => axis.quantity === "cached_tokens",
    )
    expect(cached?.better).toBe("higher")
    expect(cached?.label).toBe("Cache Reuse")
  })

  it("has every other metric better at the low end", () => {
    const higher = ["cached_tokens", "cache_hit_rate"]
    for (const axis of build_metric_axes(KEY_METAS)) {
      if (higher.includes(axis.quantity)) continue
      expect(axis.better).toBe("lower")
    }
  })

  it("names an unrecognised higher-is-better metric as itself", () => {
    // More of it is already the good outcome, so "Efficiency" would be noise
    const axis = build_metric_axes([
      meta("e1", "Efficiency", "cache_warm_hits", "higher_is_better"),
    ]).find((candidate) => candidate.key === "e1::cache_warm_hits")
    expect(axis?.label).toBe("Cache Warm Hits")
    expect(axis?.better).toBe("higher")
  })

  it("lets an author's declared direction win over the catalog's", () => {
    const authored = build_metric_axes([
      meta("e1", "Efficiency", "cached_tokens", "lower_is_better"),
    ]).find((axis) => axis.quantity === "cached_tokens")
    expect(authored?.better).toBe("lower")
  })
})

// Feedback 6: the Latency eval's five keys are authored informational, which
// kept them off this chart entirely. Being a metric is the point of the chart.
describe("build_metric_axes: informational keys", () => {
  it("plots an informational metric whose direction it knows", () => {
    const keys = build_metric_axes(KEY_METAS).map((axis) => axis.key)
    expect(keys).toContain("l1::latency_ms_turn1")
    expect(keys).toContain("l1::latency_ms_turn2")
    expect(keys).toContain("l1::latency_ms_per_call")
    expect(keys).toContain("e1::cached_tokens")
  })

  it("reads a turn latency out of the key, however many turns there are", () => {
    const axes = build_metric_axes([
      meta("l1", "Latency", "latency_ms_turn7", "informational"),
      meta("l1", "Latency", "latency_turn12", "informational"),
    ])
    const speed = axes.filter((axis) => axis.family === "speed")
    // The rollup's total latency leads, then the turns in numeric order
    expect(speed.map((axis) => axis.label)).toEqual([
      "Speed",
      "Turn 7 Speed",
      "Turn 12 Speed",
    ])
  })

  it("still refuses one it cannot point", () => {
    const keys = build_metric_axes(KEY_METAS).map((axis) => axis.key)
    expect(keys).not.toContain("e1::user_turns")
  })
})

describe("directionless_key_count", () => {
  it("counts only the informational keys neither chart can plot", () => {
    // user_turns; the five latency keys and cached_tokens are all plottable
    expect(directionless_key_count(KEY_METAS)).toBe(1)
    expect(directionless_key_count([])).toBe(0)
  })

  it("does not count a scored key", () => {
    expect(
      directionless_key_count([
        meta("e1", "Efficiency", "tool_calls", "lower_is_better"),
        meta("q1", "Quality", "made_up_fact", "higher_is_better"),
      ]),
    ).toBe(0)
  })
})

describe("default_metric_axis_keys", () => {
  it("caps the axis count so the labels stay legible", () => {
    const many = [
      ...KEY_METAS,
      ...Array.from({ length: 20 }, (_, index) =>
        meta("e1", "Efficiency", `metric_${index}`, "lower_is_better"),
      ),
    ]
    const keys = default_metric_axis_keys(build_metric_axes(many))
    expect(keys).toHaveLength(DEFAULT_METRIC_AXIS_COUNT)
  })

  it("leads with the three headline usage metrics", () => {
    const keys = default_metric_axis_keys(build_metric_axes(KEY_METAS))
    for (const key of CORE_USAGE_KEYS) {
      expect(keys).toContain(key)
    }
    expect(CORE_USAGE_KEYS).toEqual([COST_KEY, TOTAL_TOKENS_KEY, LATENCY_KEY])
  })

  it("returns the keys in ring order, so the chart still groups by family", () => {
    const axes = build_metric_axes(KEY_METAS)
    const keys = default_metric_axis_keys(axes)
    const ring = axes
      .map((axis) => axis.key)
      .filter((key) => keys.includes(key))
    expect(keys).toEqual(ring)
  })

  it("drops the input/output split before anything else - it restates the total", () => {
    const trimmed = default_metric_axis_keys(build_metric_axes(KEY_METAS), 10)
    expect(trimmed).toContain(TOTAL_TOKENS_KEY)
    expect(trimmed).not.toContain(INPUT_TOKENS_KEY)
    expect(trimmed).not.toContain(OUTPUT_TOKENS_KEY)
  })

  it("keeps the per-turn latencies a metrics eval was written to report", () => {
    const keys = default_metric_axis_keys(build_metric_axes(KEY_METAS))
    expect(keys).toContain("l1::latency_ms_turn1")
    expect(keys).toContain("l1::latency_ms_turn2")
  })

  it("prefers a task's own metrics over an unrecognised one", () => {
    const keys = default_metric_axis_keys(
      build_metric_axes([
        ...KEY_METAS,
        meta("e1", "Efficiency", "wasted_retries", "lower_is_better"),
      ]),
      4,
    )
    expect(keys).not.toContain("e1::wasted_retries")
  })

  it("falls back to the full usage rollup when the task has no metric evals", () => {
    expect(default_metric_axis_keys(build_metric_axes([]))).toEqual([
      COST_KEY,
      TOTAL_TOKENS_KEY,
      INPUT_TOKENS_KEY,
      OUTPUT_TOKENS_KEY,
      LATENCY_KEY,
    ])
  })

  it("returns only keys that exist on the axis list", () => {
    const axes = build_metric_axes(KEY_METAS)
    const known = new Set(axes.map((axis) => axis.key))
    for (const key of default_metric_axis_keys(axes)) {
      expect(known.has(key)).toBe(true)
    }
  })
})

describe("infer_metric_unit", () => {
  it("recognises the common metric shapes", () => {
    expect(infer_metric_unit("cost_usd")).toBe("usd")
    expect(infer_metric_unit("latency_ms_total")).toBe("ms")
    expect(infer_metric_unit("peak_input_tokens")).toBe("tokens")
    expect(infer_metric_unit("tool_calls")).toBe("count")
  })

  it("falls back to a plain count for anything unrecognised", () => {
    expect(infer_metric_unit("max_silent_run")).toBe("count")
    expect(infer_metric_unit("")).toBe("count")
  })
})

describe("format_metric_value", () => {
  it("writes each unit in its own terms", () => {
    expect(format_metric_value("usd", 0.1234)).toBe("$0.1234")
    expect(format_metric_value("ms", 1500)).toBe("1.5s")
    expect(format_metric_value("ms", 250)).toBe("250ms")
    expect(format_metric_value("tokens", 12345.6)).toBe("12,346 tokens")
    expect(format_metric_value("count", 7)).toBe("7")
    expect(format_metric_value("count", 7.123)).toBe("7.12")
    expect(format_metric_value("ratio", 0.4237)).toBe("42.4%")
  })

  it("shows a ratio over 1 rather than clamping it", () => {
    // A cache hit rate above 100% is a provider accounting bug; hiding it
    // would hide the only evidence of one
    expect(format_metric_value("ratio", 1.12)).toBe("112.0%")
    expect(format_metric_value("ratio", 0)).toBe("0.0%")
  })

  it("reads a rate as a ratio when it has to guess", () => {
    expect(infer_metric_unit("cache_hit_rate")).toBe("ratio")
    expect(infer_metric_unit("retry_ratio")).toBe("ratio")
  })

  it("says N/A rather than printing a non-number", () => {
    expect(format_metric_value("usd", null)).toBe("N/A")
    expect(format_metric_value("count", NaN)).toBe("N/A")
    expect(format_metric_value("ms", Infinity)).toBe("N/A")
  })
})

describe("wrap_axis_label", () => {
  it("leaves a short label alone", () => {
    expect(wrap_axis_label("Speed")).toBe("Speed")
    expect(wrap_axis_label("Token Economy")).toBe("Token Economy")
    expect(wrap_axis_label("Turn 1 Speed")).toBe("Turn 1 Speed")
  })

  it("breaks a long one where the two lines come out closest in length", () => {
    expect(wrap_axis_label("Input Token Economy")).toBe("Input Token\nEconomy")
    expect(wrap_axis_label("Skill Read Efficiency")).toBe(
      "Skill Read\nEfficiency",
    )
    expect(wrap_axis_label("Narration Consistency")).toBe(
      "Narration\nConsistency",
    )
    expect(wrap_axis_label("Cost Efficiency")).toBe("Cost\nEfficiency")
  })

  it("breaks a tie towards the later boundary", () => {
    // "First" alone on a line reads worse than "Speed" alone
    expect(wrap_axis_label("First Reply Speed")).toBe("First Reply\nSpeed")
  })

  it("never breaks what it cannot break", () => {
    expect(wrap_axis_label("Supercalifragilistic")).toBe("Supercalifragilistic")
    expect(wrap_axis_label("")).toBe("")
  })

  it("wraps every axis label the chart can produce onto short lines", () => {
    for (const axis of build_metric_axes(KEY_METAS)) {
      for (const line of wrap_axis_label(axis.label).split("\n")) {
        expect(line.length).toBeLessThanOrEqual(13)
      }
    }
  })
})

// Every quantity the catalog knows, so the default set can be judged on a task
// that has all of them rather than on whatever a fixture happens to carry.
const FULL_KEY_METAS: ScoreKeyMeta[] = [
  ...KEY_METAS,
  meta("e1", "Efficiency", "peak_input_tokens", "lower_is_better"),
  meta("e1", "Efficiency", "max_silent_run", "lower_is_better"),
  meta("e1", "Efficiency", "calls_before_first_text", "lower_is_better"),
  meta("l1", "Latency", "latency_ms_turn3", "informational"),
]

function families(axes: MetricAxis[]): MetricFamily[] {
  return axes.map((axis) => axis.family)
}

function axis(family: MetricFamily, label: string): MetricAxis {
  return {
    key: `k::${label}`,
    label,
    valueLabel: label,
    quantity: label,
    family,
    source: "score",
    unit: "count",
    better: "lower",
    evalName: "e",
  }
}

describe("the default axis set", () => {
  const shown = (keys: string[]) =>
    build_metric_axes(FULL_KEY_METAS).filter((a) => keys.includes(a.key))

  it("is eleven axes - a radar past a dozen is a circle, not a shape", () => {
    expect(DEFAULT_METRIC_AXIS_COUNT).toBe(11)
    const keys = default_metric_axis_keys(build_metric_axes(FULL_KEY_METAS))
    expect(keys).toHaveLength(11)
  })

  it("gives every family a place and lets none of them take over", () => {
    const keys = default_metric_axis_keys(build_metric_axes(FULL_KEY_METAS))
    const counts = new Map<MetricFamily, number>()
    for (const family of families(shown(keys))) {
      counts.set(family, (counts.get(family) ?? 0) + 1)
    }
    expect(Object.fromEntries(counts)).toEqual({
      cost: 1,
      tokens: 3,
      calls: 3,
      speed: 2,
      responsiveness: 2,
    })
  })

  it("defers the per-turn latencies - five Speed axes swamped the ring", () => {
    const keys = default_metric_axis_keys(build_metric_axes(FULL_KEY_METAS))
    expect(keys).not.toContain("l1::latency_ms_turn1")
    expect(keys).not.toContain("l1::latency_ms_turn3")
    // Deferred, never dropped: still an axis the Axes menu can switch on
    expect(known_metric_axis_keys(FULL_KEY_METAS)).toContain(
      "l1::latency_ms_turn1",
    )
  })

  it("defers cached tokens, which the hit rate already says normalized", () => {
    const keys = default_metric_axis_keys(build_metric_axes(FULL_KEY_METAS))
    const labelled = labels(shown(keys))
    expect(labelled).toContain("Cache Hit Rate")
    expect(labelled).not.toContain("Cache Reuse")
  })
})

describe("metric_family_bands", () => {
  it("returns one run per family, in ring order, with its span", () => {
    const bands = metric_family_bands([
      axis("cost", "Cost Efficiency"),
      axis("tokens", "Token Economy"),
      axis("tokens", "Context Headroom"),
      axis("calls", "Tool Call Economy"),
    ])
    expect(bands).toEqual([
      {
        family: "cost",
        label: METRIC_FAMILY_LABELS.cost,
        startIndex: 0,
        endIndex: 0,
        count: 1,
      },
      {
        family: "tokens",
        label: METRIC_FAMILY_LABELS.tokens,
        startIndex: 1,
        endIndex: 2,
        count: 2,
      },
      {
        family: "calls",
        label: METRIC_FAMILY_LABELS.calls,
        startIndex: 3,
        endIndex: 3,
        count: 1,
      },
    ])
  })

  it("covers every axis exactly once, so no label sits outside a band", () => {
    const axes = build_metric_axes(FULL_KEY_METAS)
    const bands = metric_family_bands(axes)
    const covered = bands.flatMap((band) =>
      Array.from(
        { length: band.count },
        (_, offset) => band.startIndex + offset,
      ),
    )
    expect(covered).toEqual(axes.map((_, index) => index))
    expect(bands[bands.length - 1].endIndex).toBe(axes.length - 1)
  })

  it("draws nothing when there is only one family - or none", () => {
    // The case the Axes menu reaches when it is narrowed to a single family: a
    // full circle of arc divides nothing, and a key to it would be worse.
    expect(
      metric_family_bands([
        axis("tokens", "Token Economy"),
        axis("tokens", "Context Headroom"),
      ]),
    ).toEqual([])
    expect(metric_family_bands([axis("cost", "Cost Efficiency")])).toEqual([])
    expect(metric_family_bands([])).toEqual([])
  })

  it("loses a family entirely when its last axis is switched off", () => {
    const all = [
      axis("cost", "Cost Efficiency"),
      axis("tokens", "Token Economy"),
      axis("calls", "Tool Call Economy"),
    ]
    const withoutTokens = all.filter((entry) => entry.family !== "tokens")
    const bands = metric_family_bands(withoutTokens)
    expect(bands.map((band) => band.family)).toEqual(["cost", "calls"])
    expect(bands.map((band) => band.label)).not.toContain(
      METRIC_FAMILY_LABELS.tokens,
    )
  })

  it("shows a split family as the two arcs it would actually be drawn as", () => {
    const bands = metric_family_bands([
      axis("tokens", "Token Economy"),
      axis("calls", "Tool Call Economy"),
      axis("tokens", "Context Headroom"),
    ])
    expect(bands.map((band) => [band.family, band.count])).toEqual([
      ["tokens", 1],
      ["calls", 1],
      ["tokens", 1],
    ])
  })
})

describe("fit_radar", () => {
  const insets = { legendHeight: 54, labelGap: 21, pad: 4 }
  // The card as the page actually lays it out: much taller than it is wide
  const BOX = { width: 539, height: 656 }

  // Axis names at the angles a radar puts them, clockwise from the top
  function ring(labels: { width: number; height: number }[]): RadarAxisLabel[] {
    const step = (Math.PI * 2) / labels.length
    return labels.map((label, index) => ({
      angle: Math.PI / 2 - index * step,
      ...label,
    }))
  }

  const four = ring([
    { width: 60, height: 28 }, // due north
    { width: 60, height: 28 }, // due east
    { width: 60, height: 28 }, // due south
    { width: 60, height: 28 }, // due west
  ])

  it("keeps a whole name inside the box, not half of it", () => {
    // echarts anchors a name at the tip and lays it outward, so the eastern
    // label runs its full 60px to the right of the ring
    const fit = fit_radar(BOX, four, insets)
    expect(fit.cx + fit.radius + insets.labelGap + 60).toBeLessThanOrEqual(
      BOX.width - insets.pad + 0.01,
    )
    // ...and it uses that budget rather than leaving room spare
    expect(fit.cx + fit.radius + insets.labelGap + 60).toBeGreaterThan(
      BOX.width - insets.pad - 1,
    )
  })

  it("spends the room a short label leaves on a bigger ring", () => {
    const short = fit_radar(
      BOX,
      ring([
        { width: 60, height: 28 },
        { width: 20, height: 28 },
        { width: 60, height: 28 },
        { width: 20, height: 28 },
      ]),
      insets,
    )
    expect(short.radius).toBeGreaterThan(fit_radar(BOX, four, insets).radius)
  })

  it("prices each axis where it actually points", () => {
    // A wide name on the diagonal costs far less than the same name due east
    const east = fit_radar(
      BOX,
      ring([
        { width: 20, height: 28 },
        { width: 120, height: 28 },
        { width: 20, height: 28 },
        { width: 20, height: 28 },
      ]),
      insets,
    )
    const diagonal = fit_radar(
      BOX,
      [
        { angle: Math.PI / 4, width: 120, height: 28 },
        { angle: (Math.PI * 3) / 4, width: 20, height: 28 },
        { angle: (-Math.PI * 3) / 4, width: 20, height: 28 },
        { angle: -Math.PI / 4, width: 20, height: 28 },
      ],
      insets,
    )
    expect(diagonal.radius).toBeGreaterThan(east.radius)
  })

  it("beats the flat percentage it replaces on this card", () => {
    // The real default set: the axes that reach the sides carry short names
    const eleven = ring(
      [
        "Cost/Efficiency",
        "Token Economy",
        "Context/Headroom",
        "Cache/Hit Rate",
        "Tool Call/Economy",
        "LLM Call/Economy",
        "Skill Read/Efficiency",
        "Speed",
        "Per-Call/Speed",
        "Narration/Consistency",
        "First Reply/Speed",
      ].map((label) => {
        const lines = label.split("/")
        return {
          width: Math.max(...lines.map((line) => line.length * 6.3)),
          height: lines.length * 14,
        }
      }),
    )
    const fit = fit_radar(BOX, eleven, insets)
    expect(fit.radius).toBeGreaterThan(0.58 * (BOX.width / 2))
  })

  it("centres the ring in what is left after the legend", () => {
    const fit = fit_radar(BOX, four, insets)
    const top = fit.cy - fit.radius - insets.labelGap - 28
    const bottom = fit.cy + fit.radius + insets.labelGap + 28
    expect(top).toBeGreaterThanOrEqual(insets.pad - 0.01)
    expect(bottom).toBeLessThanOrEqual(
      BOX.height - insets.legendHeight - insets.pad + 0.01,
    )
    // Equal room above and below: reserving legend space by pushing the centre
    // up would waste the same space again at the top
    const below = BOX.height - insets.legendHeight - insets.pad - bottom
    expect(top - insets.pad).toBeCloseTo(below, 6)
  })

  it("is bound by the height when the box is wide", () => {
    const fit = fit_radar({ width: 1600, height: 500 }, four, insets)
    const used = 2 * (fit.radius + insets.labelGap + 28)
    expect(used).toBeCloseTo(500 - insets.legendHeight - insets.pad * 2, 0)
  })

  it("floors rather than inverting when the box cannot hold its labels", () => {
    const fit = fit_radar({ width: 40, height: 40 }, four, insets)
    expect(fit.radius).toBe(MIN_RADAR_RADIUS)
    expect(Number.isFinite(fit.cy)).toBe(true)
  })

  it("draws something when there are no labels to fit at all", () => {
    const fit = fit_radar(BOX, [], insets)
    expect(fit.radius).toBeGreaterThan(MIN_RADAR_RADIUS)
    expect(fit.cx).toBe(BOX.width / 2)
  })
})

describe("metric_row_info", () => {
  // A table prints the raw number, so it takes the plain name of the quantity
  // rather than the radar's virtue - "Total Latency 42,423.91" under a heading
  // reading "Speed" would say the opposite of what the row says.
  it("names the quantity, not the virtue", () => {
    expect(metric_row_info("latency_ms_total")).toEqual({
      family: "speed",
      label: "Total Latency",
    })
    expect(metric_row_info("cost_usd").label).toBe("Cost")
    expect(metric_row_info("skill_reads_repeat").label).toBe(
      "Repeated Skill Reads",
    )
  })

  it("keeps the raw-key names the table used to show readable", () => {
    expect(metric_row_info("latency_ms_turn1")).toEqual({
      family: "speed",
      label: "Turn 1 Latency",
    })
    expect(metric_row_info("latency_ms_per_call").label).toBe(
      "Latency per Call",
    )
  })

  it("is total - a key the catalog never heard of still gets a row", () => {
    expect(metric_row_info("some_new_metric")).toEqual({
      family: "other",
      label: "Some New Metric",
    })
  })

  it("agrees with the radar about which family a metric is in", () => {
    for (const axis of build_metric_axes([])) {
      expect(metric_row_info(axis.quantity).family).toBe(axis.family)
    }
  })
})

describe("usage_row_family", () => {
  it("sorts the rollup rows into the families they measure", () => {
    expect(usage_row_family(COST_KEY)).toBe("cost")
    expect(usage_row_family(TOTAL_TOKENS_KEY)).toBe("tokens")
    expect(usage_row_family(LATENCY_KEY)).toBe("speed")
  })

  it("files an unknown rollup field under Other rather than throwing", () => {
    expect(usage_row_family("cost::mean_nonsense")).toBe("other")
  })
})
