// The axis set for the performance-metrics radar.
//
// The eval-score radar plots quality: it reads "further from the centre is
// better", so it drops every score that doesn't share that grammar - a
// lower-is-better score would put its best result nearest the centre, and an
// informational score has no better end at all (see compare_radar_chart.svelte).
// This module builds the complementary set: the numbers about *how* the config
// ran rather than how well it answered.
//
// Two sources, and both are needed:
//
//   - the native usage rollup (MeanUsage on the run-config score summary):
//     cost, tokens and latency, present for any config that has been run at
//     all, with no eval authored. It is what makes this chart work on a task
//     that has never defined a metric eval.
//   - every `lower_is_better` eval score key. That is exactly the set the
//     eval-score radar refuses to plot, so nothing is duplicated across the two
//     charts and nothing is lost between them. It is also where the numbers the
//     rollup cannot know live - tool calls, skill reads, LLM calls - because
//     those come from a code eval reading the trace.
//
// `informational` keys are deliberately left out of both charts. A radar can
// only express "further is better", and informational means the author declared
// there is no better end; plotting one would invent a direction the data does
// not have. They stay in the comparison matrix, and are counted in the note
// under the chart so the omission is visible rather than silent.

import { formatLatency, score_key_label } from "$lib/utils/formatters"
import type { ScoreKeyMeta } from "./score_lens"
import { score_key_id } from "./score_lens"

/** Where an axis gets its numbers from */
export type MetricAxisSource = "usage" | "score"

/** How the raw value behind an axis is written out. Display only. */
export type MetricAxisUnit = "usd" | "ms" | "tokens" | "count"

export interface MetricAxis {
  /** `cost::<field>` for the usage rollup, `<evalId>::<scoreKey>` for a score */
  key: string
  /** Axis label on the chart */
  label: string
  source: MetricAxisSource
  unit: MetricAxisUnit
  /** The eval this came from; null for the native usage rollup */
  evalName: string | null
}

// The usage rollup shares the `cost::` key prefix the compare page and the
// eval-score radar already use for these exact five fields, so a key means the
// same thing everywhere in the UI.
export const USAGE_KEY_PREFIX = "cost::"

export const COST_KEY = "cost::mean_cost"
export const TOTAL_TOKENS_KEY = "cost::mean_total_tokens"
export const LATENCY_KEY = "cost::mean_total_llm_latency_ms"
export const INPUT_TOKENS_KEY = "cost::mean_input_tokens"
export const OUTPUT_TOKENS_KEY = "cost::mean_output_tokens"

// Ordered best-first: the three headline metrics, then the token split, which
// is mostly redundant with the total.
export const USAGE_METRIC_AXES: MetricAxis[] = [
  {
    key: COST_KEY,
    label: "Cost",
    source: "usage",
    unit: "usd",
    evalName: null,
  },
  {
    key: TOTAL_TOKENS_KEY,
    label: "Total Tokens",
    source: "usage",
    unit: "tokens",
    evalName: null,
  },
  {
    key: LATENCY_KEY,
    label: "Latency",
    source: "usage",
    unit: "ms",
    evalName: null,
  },
  {
    key: INPUT_TOKENS_KEY,
    label: "Input Tokens",
    source: "usage",
    unit: "tokens",
    evalName: null,
  },
  {
    key: OUTPUT_TOKENS_KEY,
    label: "Output Tokens",
    source: "usage",
    unit: "tokens",
    evalName: null,
  },
]

/** The three headline usage metrics, always offered first */
export const CORE_USAGE_KEYS: string[] = [
  COST_KEY,
  TOTAL_TOKENS_KEY,
  LATENCY_KEY,
]

// A radar with fewer axes than this has no shape to read, matching the
// eval-score radar's own floor.
export const MIN_METRIC_AXES = 3

// How many axes are shown before the user opts into more. The radar component
// has no label de-cluttering: names are centred on their axis tips, and the
// vertical gap between neighbours goes to zero towards the poles, so past about
// twenty they collide. A metrics chart with every key switched on would be
// well into that (the eval-score radar already runs to 29 axes on a real task),
// so the default is a set that stays comfortably legible and the rest are one
// click away.
export const DEFAULT_METRIC_AXIS_COUNT = 8

/**
 * Unit for a metric score key, guessed from its name. Display only: it decides
 * whether a tooltip writes "1.2s" or "1200", and never affects scoring or
 * layout, so a miss costs a slightly worse-formatted number and nothing else.
 */
export function infer_metric_unit(scoreKey: string): MetricAxisUnit {
  const key = scoreKey.toLowerCase()
  if (key.includes("cost") || key.includes("usd")) return "usd"
  if (key.includes("latency") || key.endsWith("_ms") || key.includes("_ms_")) {
    return "ms"
  }
  if (key.includes("token")) return "tokens"
  return "count"
}

/**
 * Every axis this chart could plot: the usage rollup, then one per
 * lower-is-better score key, sorted by eval then key so the order is stable
 * across reloads (and so the default set below is deterministic).
 */
export function build_metric_axes(keyMetas: ScoreKeyMeta[]): MetricAxis[] {
  const score_axes: MetricAxis[] = keyMetas
    .filter((meta) => meta.direction === "lower_is_better")
    .slice()
    .sort(
      (a, b) =>
        a.evalName.localeCompare(b.evalName) ||
        a.scoreKey.localeCompare(b.scoreKey),
    )
    .map((meta) => ({
      key: score_key_id(meta.evalId, meta.scoreKey),
      label: score_key_label(meta.scoreKey),
      source: "score" as const,
      unit: infer_metric_unit(meta.scoreKey),
      evalName: meta.evalName,
    }))
  return [...USAGE_METRIC_AXES, ...score_axes]
}

/** Score keys left off both radars because they carry no better direction */
export function informational_key_count(keyMetas: ScoreKeyMeta[]): number {
  return keyMetas.filter((meta) => meta.direction === "informational").length
}

/**
 * The axes shown before the user picks their own.
 *
 * Order of preference:
 *   1. the three headline usage metrics - cost, tokens, latency - which every
 *      task has, whether or not it has authored a single eval.
 *   2. the task's own metric scores that count *events*: tool calls, LLM calls,
 *      skill reads. These are the reason to author a metrics eval at all, since
 *      they are the only numbers here the usage rollup cannot know.
 *   3. its metric scores measuring cost, tokens or time. These come last
 *      because (1) already reports those quantities, so spending a default axis
 *      on one puts near-duplicate information on the ring - a task with a
 *      `cost_usd` score would otherwise get "Cost" and "Cost Usd" side by side.
 *   4. the input/output token split, mostly redundant with the total.
 *
 * Everything is still one click away in the axis picker; this only decides what
 * is on before anyone touches it.
 */
export function default_metric_axis_keys(
  axes: MetricAxis[],
  max: number = DEFAULT_METRIC_AXIS_COUNT,
): string[] {
  const core = axes.filter((axis) => CORE_USAGE_KEYS.includes(axis.key))
  const event_scores = axes.filter(
    (axis) => axis.source === "score" && axis.unit === "count",
  )
  const quantity_scores = axes.filter(
    (axis) => axis.source === "score" && axis.unit !== "count",
  )
  const extra_usage = axes.filter(
    (axis) => axis.source === "usage" && !CORE_USAGE_KEYS.includes(axis.key),
  )
  return [...core, ...event_scores, ...quantity_scores, ...extra_usage]
    .slice(0, Math.max(max, 0))
    .map((axis) => axis.key)
}

/** A metric's raw value in its own units, for tooltips */
export function format_metric_value(
  unit: MetricAxisUnit,
  value: number | null,
): string {
  if (value === null || !Number.isFinite(value)) return "N/A"
  switch (unit) {
    case "usd":
      // Four decimals, matching the comparison matrix on this page
      return `$${value.toFixed(4)}`
    case "ms":
      return formatLatency(value)
    case "tokens":
      return `${Math.round(value).toLocaleString()} tokens`
    case "count":
      return value.toLocaleString(undefined, { maximumFractionDigits: 2 })
  }
}
