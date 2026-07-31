import { describe, it, expect } from "vitest"
import type { components } from "$lib/api_schema"
import type { ScoreKeyMeta } from "./score_lens"
import {
  COST_KEY,
  CORE_USAGE_KEYS,
  DEFAULT_METRIC_AXIS_COUNT,
  INPUT_TOKENS_KEY,
  LATENCY_KEY,
  OUTPUT_TOKENS_KEY,
  TOTAL_TOKENS_KEY,
  USAGE_METRIC_AXES,
  build_metric_axes,
  default_metric_axis_keys,
  format_metric_value,
  infer_metric_unit,
  informational_key_count,
} from "./metric_axes"

type ScoreDirection = components["schemas"]["ScoreDirection"]

function meta(
  evalId: string,
  evalName: string,
  scoreKey: string,
  direction: ScoreDirection,
): ScoreKeyMeta {
  return { evalId, evalName, scoreKey, type: "custom", direction }
}

// A task shaped like a real one: a quality eval, a metrics eval with
// lower-is-better keys, and a latency eval whose keys are informational.
const KEY_METAS: ScoreKeyMeta[] = [
  meta("q1", "Quality", "false_done_claim", "higher_is_better"),
  meta("q1", "Quality", "refetched_schema", "higher_is_better"),
  meta("e1", "Efficiency", "tool_calls", "lower_is_better"),
  meta("e1", "Efficiency", "cost_usd", "lower_is_better"),
  meta("e1", "Efficiency", "input_tokens", "lower_is_better"),
  meta("l1", "Latency", "latency_ms_total", "informational"),
  meta("l1", "Latency", "latency_ms_turn1", "informational"),
]

describe("build_metric_axes", () => {
  it("always offers the native usage rollup, even with no evals at all", () => {
    const axes = build_metric_axes([])
    expect(axes.map((axis) => axis.key)).toEqual(
      USAGE_METRIC_AXES.map((axis) => axis.key),
    )
    expect(axes.every((axis) => axis.source === "usage")).toBe(true)
  })

  it("adds one axis per lower-is-better score key", () => {
    const axes = build_metric_axes(KEY_METAS)
    const score_axes = axes.filter((axis) => axis.source === "score")
    expect(score_axes.map((axis) => axis.key)).toEqual([
      "e1::cost_usd",
      "e1::input_tokens",
      "e1::tool_calls",
    ])
    expect(score_axes[2].label).toBe("Tool Calls")
    expect(score_axes[2].evalName).toBe("Efficiency")
  })

  it("leaves out higher-is-better keys - the eval-score radar already has them", () => {
    const keys = build_metric_axes(KEY_METAS).map((axis) => axis.key)
    expect(keys).not.toContain("q1::false_done_claim")
    expect(keys).not.toContain("q1::refetched_schema")
  })

  it("leaves out informational keys - a radar cannot express 'no direction'", () => {
    const keys = build_metric_axes(KEY_METAS).map((axis) => axis.key)
    expect(keys).not.toContain("l1::latency_ms_total")
    expect(keys).not.toContain("l1::latency_ms_turn1")
  })

  it("orders score axes by eval then key, so the set is stable across reloads", () => {
    const shuffled = [KEY_METAS[4], KEY_METAS[2], KEY_METAS[3]]
    expect(build_metric_axes(shuffled).map((axis) => axis.key)).toEqual(
      build_metric_axes(KEY_METAS).map((axis) => axis.key),
    )
  })

  it("does not mutate the input", () => {
    const input = [...KEY_METAS]
    build_metric_axes(input)
    expect(input).toEqual(KEY_METAS)
  })
})

describe("informational_key_count", () => {
  it("counts the keys neither radar can plot", () => {
    expect(informational_key_count(KEY_METAS)).toBe(2)
    expect(informational_key_count([])).toBe(0)
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
    expect(keys.slice(0, 3)).toEqual(CORE_USAGE_KEYS)
    expect(CORE_USAGE_KEYS).toEqual([COST_KEY, TOTAL_TOKENS_KEY, LATENCY_KEY])
  })

  it("prefers the task's own metrics over the input/output token split", () => {
    const keys = default_metric_axis_keys(build_metric_axes(KEY_METAS))
    expect(keys).toContain("e1::tool_calls")
    expect(keys.indexOf("e1::tool_calls")).toBeLessThan(
      keys.indexOf(INPUT_TOKENS_KEY),
    )
  })

  it("prefers event counts over score keys that restate the usage rollup", () => {
    const keys = default_metric_axis_keys(build_metric_axes(KEY_METAS))
    // tool_calls is a number the rollup cannot know; cost_usd and input_tokens
    // are ones it already reports, so they must not outrank it
    expect(keys.indexOf("e1::tool_calls")).toBeLessThan(
      keys.indexOf("e1::cost_usd"),
    )
    expect(keys.indexOf("e1::tool_calls")).toBeLessThan(
      keys.indexOf("e1::input_tokens"),
    )
  })

  it("does not spend a default axis on a duplicate of a headline metric", () => {
    // Five event-count metrics is enough to fill the budget on its own, so a
    // cost_usd score never lands next to the rollup's own Cost axis
    const metas = [
      ...[
        "tool_calls",
        "llm_calls",
        "max_silent_run",
        "skill_reads_repeat",
      ].map((key) => meta("e1", "Efficiency", key, "lower_is_better")),
      meta("e1", "Efficiency", "calls_before_first_text", "lower_is_better"),
      meta("e1", "Efficiency", "cost_usd", "lower_is_better"),
      meta("e1", "Efficiency", "total_tokens", "lower_is_better"),
    ]
    const keys = default_metric_axis_keys(build_metric_axes(metas))
    expect(keys).toHaveLength(DEFAULT_METRIC_AXIS_COUNT)
    expect(keys).toContain(COST_KEY)
    expect(keys).not.toContain("e1::cost_usd")
    expect(keys).not.toContain("e1::total_tokens")
    expect(keys).toContain("e1::tool_calls")
  })

  it("falls back to the full usage rollup when the task has no metric evals", () => {
    expect(default_metric_axis_keys(build_metric_axes([]))).toEqual([
      COST_KEY,
      TOTAL_TOKENS_KEY,
      LATENCY_KEY,
      INPUT_TOKENS_KEY,
      OUTPUT_TOKENS_KEY,
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
  })

  it("says N/A rather than printing a non-number", () => {
    expect(format_metric_value("usd", null)).toBe("N/A")
    expect(format_metric_value("count", NaN)).toBe("N/A")
    expect(format_metric_value("ms", Infinity)).toBe("N/A")
  })
})
