// The axis set for the performance-metrics radar.
//
// The eval-score radar plots quality. This module builds the complementary set:
// the numbers about *how* a run config ran rather than how well it answered.
//
// Three things happen here, and they are the whole design:
//
// 1. IDENTITY. An axis is a *quantity*, not a name. The same quantity reaches
//    the page from two places - the native usage rollup (MeanUsage on the run
//    config summary) and an eval score key computed by a code eval reading the
//    trace - so "Cost" and "Cost Usd", or two "Total Tokens", used to land on
//    the ring side by side. Every candidate is resolved to a canonical quantity
//    id and each quantity gets exactly one axis. See `dedupe_by_quantity` for
//    which source wins.
//
// 2. DIRECTION. A radar can only say "further from the centre is better", so
//    every axis has to know which end of its raw scale is the good one. Nearly
//    all of these are lower-is-better; the cache metrics are not, because cache
//    reuse is the thing you want more of. The authored direction wins wherever
//    the author gave one; the catalog supplies a direction only for keys
//    authored `informational`, where nobody declared one. Direction never
//    decides which chart a key is on - see the membership note below.
//
// 3. LABELS. Because the geometry already reads "further is better", the label
//    has to agree with it. An axis called "Skill Reads Repeat" with a point far
//    from the centre reads as "lots of repeats" when it means the opposite. So
//    every axis is named for the *virtue* being measured - "Skill Read
//    Efficiency", "Cost Efficiency", "Speed" - never "Fewer X" or "Avoids X",
//    which are the double negatives that make a glance ambiguous. The plain
//    name of the raw quantity survives as `valueLabel`, for printing values.
//
// Membership is decided by WHICH EVAL a key belongs to, not by its direction.
// Routing on direction is the bug this replaces: it read "lower is better" as
// "this is a metric", which holds right up until a metric is better the larger
// it gets. `cache_hit_rate` is exactly that, and under the old rule a cost
// metric landed on the quality radar between the pass/fail judges.
//
//   - a key from a METRICS eval belongs here, whichever way it points
//   - a key from a CRITERION eval belongs on the eval-score radar
//   - and see `is_metric_eval` for how the two are told apart
//
// Direction then decides only how an axis is drawn, never which chart it is on:
// the authored direction wins where the author gave one, and for a key authored
// `informational` the catalog supplies it. Being a metric is the entire point
// of this chart, so an informational latency belongs on it - while the page's
// aggregate ("overall quality") continues to skip every informational key,
// which is why they were authored that way. An informational metric the catalog
// cannot point has no better end at all and no honest place on a radar, so it
// stays off and is counted in the note under the chart.

import { formatLatency, score_key_label } from "$lib/utils/formatters"
import { family_bands, type FamilyBand } from "./family_bands"
import type { ScoreKeyMeta } from "./score_lens"
import { score_key_id } from "./score_lens"

/** Where an axis gets its numbers from */
export type MetricAxisSource = "usage" | "score"

/** How the raw value behind an axis is written out. Display only. */
export type MetricAxisUnit = "usd" | "ms" | "tokens" | "count" | "ratio"

/** Which end of the raw scale is the good one */
export type MetricDirection = "lower" | "higher"

/**
 * Axis families, in the order they are laid out around the ring. Grouping them
 * is what stops tokens from being scattered across three arcs: the reader can
 * take in "this config is cheap but slow" as two neighbourhoods rather than by
 * hunting matched labels around the circle.
 *
 * The order is a chain: what it cost, what it spent to get there, how many
 * round trips that took, how long they took, and how it felt while waiting.
 * The chart draws the chain CLOCKWISE from the top, which is the direction a
 * ring is read; echarts lays indicators out counterclockwise unless told
 * otherwise, so the radar sets `clockwise` rather than reversing this list.
 */
export const METRIC_FAMILIES = [
  "cost",
  "tokens",
  "calls",
  "speed",
  "responsiveness",
  "other",
] as const

export type MetricFamily = (typeof METRIC_FAMILIES)[number]

/** Family headings for the axis picker */
export const METRIC_FAMILY_LABELS: Record<MetricFamily, string> = {
  cost: "Cost",
  tokens: "Tokens",
  calls: "Calls",
  speed: "Speed",
  responsiveness: "Responsiveness",
  other: "Other",
}

export interface MetricAxis {
  /** `cost::<field>` for the usage rollup, `<evalId>::<scoreKey>` for a score */
  key: string
  /** Axis label: the virtue, phrased so further from the centre reads better */
  label: string
  /** Plain name of the raw quantity, for printing an actual value */
  valueLabel: string
  /** What is measured, independent of which source reports it */
  quantity: string
  family: MetricFamily
  source: MetricAxisSource
  unit: MetricAxisUnit
  /** Which end of the raw scale scores highest */
  better: MetricDirection
  /** The eval this came from; null for the native usage rollup */
  evalName: string | null
}

interface MetricDefinition {
  quantity: string
  /** The virtue */
  label: string
  /** The raw quantity */
  valueLabel: string
  family: MetricFamily
  unit: MetricAxisUnit
  better: MetricDirection
  /**
   * Position around the ring. Families own contiguous blocks, so ordering by
   * this number alone keeps every family in one arc.
   */
  order: number
  /** Preference when trimming to the default axis count; lower is kept first */
  defaultRank: number
  /** Score keys known to report this quantity, exactly as authored */
  aliases: string[]
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

/** Which quantity each field of the usage rollup reports */
const USAGE_QUANTITIES: { key: string; quantity: string }[] = [
  { key: COST_KEY, quantity: "cost" },
  { key: TOTAL_TOKENS_KEY, quantity: "total_tokens" },
  { key: LATENCY_KEY, quantity: "latency" },
  { key: INPUT_TOKENS_KEY, quantity: "input_tokens" },
  { key: OUTPUT_TOKENS_KEY, quantity: "output_tokens" },
]

/**
 * Every quantity this chart knows how to name and point in the right
 * direction. Ordered by `order`, which is also the order around the ring.
 */
const METRIC_CATALOG: MetricDefinition[] = [
  {
    quantity: "cost",
    label: "Cost Efficiency",
    valueLabel: "Cost",
    family: "cost",
    unit: "usd",
    better: "lower",
    order: 100,
    defaultRank: 1,
    aliases: ["cost", "cost_usd"],
  },

  {
    quantity: "total_tokens",
    label: "Token Economy",
    valueLabel: "Total Tokens",
    family: "tokens",
    unit: "tokens",
    better: "lower",
    order: 200,
    defaultRank: 2,
    aliases: ["total_tokens"],
  },
  {
    quantity: "peak_input_tokens",
    // The largest context ever sent. A smaller peak is room left before the
    // model's window binds, which is what the number is actually watched for.
    label: "Context Headroom",
    valueLabel: "Peak Input Tokens",
    family: "tokens",
    unit: "tokens",
    better: "lower",
    order: 210,
    defaultRank: 9,
    aliases: ["peak_input_tokens"],
  },
  // The two metrics here where MORE is better: a cached token is one that was
  // read from the prompt cache instead of being paid for again. Everything else
  // on this chart is better the smaller it gets, which is exactly why the
  // direction is a property of the metric rather than of the chart.
  {
    quantity: "cached_tokens",
    label: "Cache Reuse",
    valueLabel: "Cached Tokens",
    family: "tokens",
    unit: "tokens",
    better: "higher",
    order: 220,
    // Off by default: the hit rate below is the same fact normalized, and two
    // axes for one story spend ring on nothing. Opt in from the Axes menu.
    defaultRank: 12,
    aliases: ["cached_tokens"],
  },
  {
    quantity: "cache_hit_rate",
    // Already a virtue as written - a higher hit rate is plainly the better
    // one - so this is the axis where the naming pass had nothing to do.
    label: "Cache Hit Rate",
    valueLabel: "Cache Hit Rate",
    family: "tokens",
    unit: "ratio",
    better: "higher",
    order: 225,
    defaultRank: 10,
    aliases: ["cache_hit_rate"],
  },
  {
    quantity: "input_tokens",
    label: "Input Token Economy",
    valueLabel: "Input Tokens",
    family: "tokens",
    unit: "tokens",
    better: "lower",
    order: 230,
    // The input/output split restates the total, so it is the first thing
    // dropped when the default set is trimmed.
    defaultRank: 90,
    aliases: ["input_tokens"],
  },
  {
    quantity: "output_tokens",
    label: "Output Token Economy",
    valueLabel: "Output Tokens",
    family: "tokens",
    unit: "tokens",
    better: "lower",
    order: 240,
    defaultRank: 91,
    aliases: ["output_tokens"],
  },

  {
    quantity: "tool_calls",
    label: "Tool Call Economy",
    valueLabel: "Tool Calls",
    family: "calls",
    unit: "count",
    better: "lower",
    order: 300,
    defaultRank: 4,
    aliases: ["tool_calls"],
  },
  {
    quantity: "llm_calls",
    label: "LLM Call Economy",
    valueLabel: "LLM Calls",
    family: "calls",
    unit: "count",
    better: "lower",
    order: 310,
    defaultRank: 5,
    aliases: ["llm_calls"],
  },
  {
    quantity: "skill_reads_repeat",
    label: "Skill Read Efficiency",
    valueLabel: "Repeated Skill Reads",
    family: "calls",
    unit: "count",
    better: "lower",
    order: 320,
    defaultRank: 6,
    aliases: ["skill_reads_repeat"],
  },

  {
    quantity: "latency",
    label: "Speed",
    valueLabel: "Total Latency",
    family: "speed",
    unit: "ms",
    better: "lower",
    order: 400,
    defaultRank: 3,
    aliases: ["latency", "latency_ms", "latency_ms_total"],
  },
  // Per-turn latencies sit between the total and the per-call average; their
  // definitions are generated, see `turn_latency_definition`.
  {
    quantity: "latency_per_call",
    label: "Per-Call Speed",
    valueLabel: "Latency per Call",
    family: "speed",
    unit: "ms",
    better: "lower",
    order: 490,
    defaultRank: 11,
    aliases: ["latency_per_call", "latency_ms_per_call"],
  },

  {
    quantity: "max_silent_run",
    // The longest stretch of calls with nothing said to the user. A short one
    // is a run that keeps narrating instead of going quiet.
    label: "Narration Consistency",
    valueLabel: "Longest Silent Run",
    family: "responsiveness",
    unit: "count",
    better: "lower",
    order: 500,
    defaultRank: 7,
    aliases: ["max_silent_run"],
  },
  {
    quantity: "calls_before_first_text",
    label: "First Reply Speed",
    valueLabel: "Calls Before First Reply",
    family: "responsiveness",
    unit: "count",
    better: "lower",
    order: 510,
    defaultRank: 8,
    aliases: ["calls_before_first_text"],
  },
]

// Turn-numbered latency keys are open-ended - a task can have as many turns as
// it likes - so they are matched by shape rather than listed.
const TURN_LATENCY_PATTERN = /^latency(?:_ms)?_turn(\d+)$/
const TURN_LATENCY_ORDER_BASE = 400
const TURN_LATENCY_RANK_BASE = 11

function turn_latency_definition(turn: number): MetricDefinition {
  return {
    quantity: `latency_turn${turn}`,
    label: `Turn ${turn} Speed`,
    valueLabel: `Turn ${turn} Latency`,
    family: "speed",
    unit: "ms",
    better: "lower",
    // Between the total (400) and the per-call average (490); a task with more
    // than 89 turns loses the ordering, not the axis.
    order: TURN_LATENCY_ORDER_BASE + Math.min(turn, 89),
    defaultRank: TURN_LATENCY_RANK_BASE + turn,
    aliases: [],
  }
}

const DEFINITION_BY_QUANTITY = new Map(
  METRIC_CATALOG.map((definition) => [definition.quantity, definition]),
)

const QUANTITY_BY_ALIAS = new Map<string, string>()
for (const definition of METRIC_CATALOG) {
  for (const alias of definition.aliases) {
    QUANTITY_BY_ALIAS.set(alias, definition.quantity)
  }
}

/** Fallback ordering and preference for a metric the catalog does not know */
const UNKNOWN_ORDER = 900
const UNKNOWN_DEFAULT_RANK = 500

const TURN_QUANTITY_PATTERN = /^latency_turn(\d+)$/

/** The definition behind a quantity id, including the generated turn ones */
function definition_for_quantity(quantity: string): MetricDefinition | null {
  const known = DEFINITION_BY_QUANTITY.get(quantity)
  if (known) return known
  const turn = TURN_QUANTITY_PATTERN.exec(quantity)
  return turn ? turn_latency_definition(Number(turn[1])) : null
}

/**
 * The catalog entry for a score key, or null when the key is not a metric this
 * module can name and point.
 */
function definition_for_score_key(scoreKey: string): MetricDefinition | null {
  const normalized = scoreKey.trim().toLowerCase()
  const quantity = QUANTITY_BY_ALIAS.get(normalized)
  if (quantity) {
    return DEFINITION_BY_QUANTITY.get(quantity) ?? null
  }
  const turn = TURN_LATENCY_PATTERN.exec(normalized)
  if (turn) {
    return turn_latency_definition(Number(turn[1]))
  }
  return null
}

/**
 * A definition for a metric the catalog has never heard of. The direction is
 * known - the author declared it - so the axis is honest; only the name has to
 * be derived. A higher-is-better metric already reads as a virtue, since more
 * of it is the good outcome, so its own name is the label. A lower-is-better
 * one needs one, and "<Thing> Efficiency" is the phrasing that says "less of
 * this is better" without a negation in it.
 */
function derived_definition(
  scoreKey: string,
  better: MetricDirection,
): MetricDefinition {
  const plain = score_key_label(scoreKey)
  return {
    quantity: `key:${scoreKey.trim().toLowerCase()}`,
    label: better === "higher" ? plain : `${plain} Efficiency`,
    valueLabel: plain,
    family: "other",
    unit: infer_metric_unit(scoreKey),
    better,
    order: UNKNOWN_ORDER,
    defaultRank: UNKNOWN_DEFAULT_RANK,
    aliases: [],
  }
}

function axis_from_definition(
  key: string,
  definition: MetricDefinition,
  source: MetricAxisSource,
  evalName: string | null,
): MetricAxis {
  return {
    key,
    label: definition.label,
    valueLabel: definition.valueLabel,
    quantity: definition.quantity,
    family: definition.family,
    source,
    unit: definition.unit,
    better: definition.better,
    evalName,
  }
}

/** The native usage rollup, one axis per field */
export const USAGE_METRIC_AXES: MetricAxis[] = USAGE_QUANTITIES.map(
  ({ key, quantity }) => {
    const definition = definition_for_quantity(quantity)
    if (!definition) {
      // Unreachable: every usage quantity above is in the catalog, and a test
      // holds it that way. Kept total so a future rollup field fails loudly
      // rather than silently landing in "Other".
      throw new Error(`No metric definition for usage key ${key}`)
    }
    return axis_from_definition(key, definition, "usage", null)
  },
)

/** The three headline usage metrics, always offered first */
export const CORE_USAGE_KEYS: string[] = [
  COST_KEY,
  TOTAL_TOKENS_KEY,
  LATENCY_KEY,
]

// A radar with fewer axes than this has no shape to read, matching the
// eval-score radar's own floor.
export const MIN_METRIC_AXES = 3

/**
 * How many axes are shown before the user opts into more.
 *
 * Fourteen fit without clipping, which is what set the previous ceiling, but
 * fitting is not reading. Past roughly a dozen axes a radar stops being a shape
 * and becomes a circle: the vertices are 20-odd degrees apart, every polygon
 * looks alike, and the ring of labels is long enough that finding the one you
 * want is a search. The families make that worse when they are lopsided - five
 * of the sixteen were per-turn latencies, so a third of the ring was Speed
 * saying the same thing five times.
 *
 * Eleven is the top of the ranking, and it lands one axis of Cost, three of
 * Tokens, three of Calls, two of Speed and two of Responsiveness: every family
 * present, none of them dominant, and the second-order breakdowns (the per-turn
 * latencies, the input/output split, cached tokens beside the hit rate) one
 * click away in the Axes menu. Nothing is dropped, only deferred.
 */
export const DEFAULT_METRIC_AXIS_COUNT = 11

/**
 * Unit for a metric score key, guessed from its name. Display only: it decides
 * whether a tooltip writes "1.2s" or "1200", and never affects scoring or
 * layout, so a miss costs a slightly worse-formatted number and nothing else.
 * Only reached for keys the catalog does not know.
 */
export function infer_metric_unit(scoreKey: string): MetricAxisUnit {
  const key = scoreKey.toLowerCase()
  if (key.includes("cost") || key.includes("usd")) return "usd"
  if (key.includes("latency") || key.endsWith("_ms") || key.includes("_ms_")) {
    return "ms"
  }
  if (key.includes("token")) return "tokens"
  if (key.endsWith("_rate") || key.endsWith("_ratio")) return "ratio"
  return "count"
}

/**
 * Whether an eval's score keys are metrics rather than criteria.
 *
 * The test is the score TYPE, because that is the structural difference the two
 * radars are built on rather than a naming convention. A criterion is graded on
 * a bounded scale the type itself defines - pass/fail is 0..1, five star is
 * 1..5 - which is what lets the eval-score radar plot it against an absolute
 * axis and call one end "best". A metric is `custom`: unbounded, no maximum
 * cost or latency to normalize against, so the only scale it has is position
 * among the run configs being compared, which is what this chart does.
 *
 * So: an eval whose scores are ALL custom is a metrics eval. One with any
 * bounded score is a criterion eval, and every key on it - including a custom
 * one sitting beside the graded ones - belongs to the quality radar.
 *
 * Deliberately not the direction. Routing on direction was the bug: it holds
 * only while every metric is better small, and `cache_hit_rate` is not.
 */
export function is_metric_eval(evalKeyMetas: ScoreKeyMeta[]): boolean {
  return (
    evalKeyMetas.length > 0 &&
    evalKeyMetas.every((meta) => meta.type === "custom")
  )
}

function group_by_eval(keyMetas: ScoreKeyMeta[]): Map<string, ScoreKeyMeta[]> {
  const by_eval = new Map<string, ScoreKeyMeta[]>()
  for (const meta of keyMetas) {
    const group = by_eval.get(meta.evalId) ?? []
    group.push(meta)
    by_eval.set(meta.evalId, group)
  }
  return by_eval
}

/** The ids of the evals whose keys this chart owns */
export function metric_eval_ids(keyMetas: ScoreKeyMeta[]): Set<string> {
  const ids = new Set<string>()
  for (const [evalId, metas] of group_by_eval(keyMetas)) {
    if (is_metric_eval(metas)) ids.add(evalId)
  }
  return ids
}

/**
 * The keys the eval-score radar owns: everything from an eval that grades
 * criteria. The complement of what this module plots, so the two charts
 * partition the score space with nothing counted twice and nothing lost.
 */
export function criterion_key_metas(keyMetas: ScoreKeyMeta[]): ScoreKeyMeta[] {
  const metric_evals = metric_eval_ids(keyMetas)
  return keyMetas.filter((meta) => !metric_evals.has(meta.evalId))
}

/** The keys from the metrics evals, with the definition each one resolves to */
function plottable_score_axes(keyMetas: ScoreKeyMeta[]): MetricAxis[] {
  const metric_evals = metric_eval_ids(keyMetas)
  const axes: MetricAxis[] = []
  for (const meta of keyMetas) {
    if (!metric_evals.has(meta.evalId)) continue
    const known = definition_for_score_key(meta.scoreKey)
    let definition: MetricDefinition | null = null
    if (meta.direction === "informational") {
      // Nobody declared a direction, so the catalog has to know the metric to
      // point its axis; one it does not recognise cannot be drawn honestly.
      definition = known
    } else {
      // The author declared the direction, so it wins over the catalog's; the
      // catalog is still where the name and the family come from.
      const better: MetricDirection =
        meta.direction === "higher_is_better" ? "higher" : "lower"
      definition = known
        ? { ...known, better }
        : derived_definition(meta.scoreKey, better)
    }
    if (!definition) continue
    axes.push(
      axis_from_definition(
        score_key_id(meta.evalId, meta.scoreKey),
        definition,
        "score",
        meta.evalName,
      ),
    )
  }
  return axes
}

/**
 * One axis per quantity.
 *
 * The usage rollup wins a collision, for three reasons: it is computed over
 * every run of the config rather than one eval's filtered dataset, so it is the
 * broader population; it exists for any config that has been run at all, so
 * preferring it keeps the axis set steady as evals come and go; and it is the
 * same number the comparison matrix and the eval-score radar already show under
 * that name, so one label means one thing across the page.
 *
 * The exception is data: a rollup field the provider never reported (cost from
 * a local model, say) is an empty axis, and an eval score key measuring the
 * same quantity is a real one. `hasValue` lets the caller say which candidates
 * actually have numbers, and the first candidate that does is used. With no
 * `hasValue` - or when nothing has loaded yet - the preference order stands, so
 * the axis set does not churn while the page is still fetching.
 */
function dedupe_by_quantity(
  candidates: MetricAxis[],
  hasValue?: (key: string) => boolean,
): MetricAxis[] {
  const by_quantity = new Map<string, MetricAxis[]>()
  for (const axis of candidates) {
    const group = by_quantity.get(axis.quantity) ?? []
    group.push(axis)
    by_quantity.set(axis.quantity, group)
  }
  const winners: MetricAxis[] = []
  for (const group of by_quantity.values()) {
    const withValue = hasValue
      ? group.find((axis) => hasValue(axis.key))
      : undefined
    winners.push(withValue ?? group[0])
  }
  return winners
}

/** Where an axis sits around the ring; families own contiguous blocks */
function axis_order(axis: MetricAxis): number {
  return definition_for_quantity(axis.quantity)?.order ?? UNKNOWN_ORDER
}

function compare_axes(a: MetricAxis, b: MetricAxis): number {
  return (
    METRIC_FAMILIES.indexOf(a.family) - METRIC_FAMILIES.indexOf(b.family) ||
    axis_order(a) - axis_order(b) ||
    a.label.localeCompare(b.label)
  )
}

/**
 * Every axis this chart could plot: the usage rollup plus the eval score keys
 * it can name and point, one per quantity, ordered so each family occupies a
 * single arc of the ring. The order is a pure function of the axis set, so it
 * is stable across renders and reloads.
 */
export function build_metric_axes(
  keyMetas: ScoreKeyMeta[],
  hasValue?: (key: string) => boolean,
): MetricAxis[] {
  // Sorted before deduplication so "which score key wins" never depends on the
  // order the summary happened to list them in.
  const score_axes = plottable_score_axes(keyMetas).sort(
    (a, b) =>
      (a.evalName ?? "").localeCompare(b.evalName ?? "") ||
      a.key.localeCompare(b.key),
  )
  return dedupe_by_quantity(
    [...USAGE_METRIC_AXES, ...score_axes],
    hasValue,
  ).sort(compare_axes)
}

/**
 * The axes left once the rows the reader hid are taken out.
 *
 * The x on a comparison-table row means "take this out of the comparison", and
 * it means the same in both tracks: the row leaves its table and its axis
 * leaves the ring. `hiddenKeys` is that set of rows expressed as axis keys - a
 * hidden score row's key IS its axis key, and a hidden usage row contributes
 * the rollup field it prints.
 *
 * Filtering happens HERE, on the built catalog, and not on the score keys going
 * into `build_metric_axes`. Two reasons, and they are the whole reason this is
 * a separate step:
 *
 *   - `build_metric_axes` deduplicates by quantity, so filtering its input can
 *     change which SOURCE wins an axis. Hiding the cost rollup row would then
 *     leave a "Cost Efficiency" axis behind, silently fed by an eval's
 *     `cost_usd` instead - a different number under an unchanged label, which
 *     is worse than the axis leaving.
 *   - the catalog stays whole, and it is what a saved axis selection and the
 *     default axis set are resolved against. So hiding a row cannot rewrite
 *     either: restoring the row brings its axis back exactly if it was on, and
 *     hiding one never promotes some other metric into the default set to
 *     backfill the freed slot.
 *
 * The Axes menu then picks which of THESE are plotted. The two controls
 * compose - one decides what is in the comparison, the other what is on the
 * ring - rather than overlapping.
 */
export function visible_metric_axes(
  axes: MetricAxis[],
  hiddenKeys: Set<string>,
): MetricAxis[] {
  return axes.filter((axis) => !hiddenKeys.has(axis.key))
}

/**
 * The axis selection after switching one axis on or off.
 *
 * Materialized against the UNFILTERED catalog, which is the only subtle part:
 * an axis whose row is currently hidden is not among the visible ones, and
 * dropping it here would quietly edit the selection as a side effect of an
 * unrelated click - so restoring the row would bring the row back without its
 * axis. Filtering rather than mapping the selected set also keeps the result in
 * ring order, so the axis order never depends on the order they were switched
 * on in.
 */
export function toggled_metric_axis_keys(
  axes: MetricAxis[],
  shownKeys: string[],
  key: string,
): string[] {
  const selected = new Set(shownKeys)
  if (selected.has(key)) {
    selected.delete(key)
  } else {
    selected.add(key)
  }
  return axes.filter((axis) => selected.has(axis.key)).map((axis) => axis.key)
}

/**
 * Every key that could become an axis, before deduplication picks between two
 * sources for the same quantity.
 *
 * For validating a URL, which is restored before the lazily fetched usage
 * arrives. Checking a saved selection against the deduplicated set would judge
 * it under "nothing has loaded yet", where the rollup always wins - and would
 * quietly drop a score key the user picked precisely because the rollup has no
 * numbers on their provider.
 */
export function known_metric_axis_keys(keyMetas: ScoreKeyMeta[]): Set<string> {
  return new Set(
    [...USAGE_METRIC_AXES, ...plottable_score_axes(keyMetas)].map(
      (axis) => axis.key,
    ),
  )
}

/**
 * Metrics that reach neither chart: from a metrics eval, so this chart owns
 * them, but authored with no better direction and not a quantity the catalog
 * can point. Counted under the chart so the omission is stated rather than
 * silent. Criterion keys are not counted here - the eval-score radar has its
 * own note for what it leaves out.
 */
export function directionless_key_count(keyMetas: ScoreKeyMeta[]): number {
  const metric_evals = metric_eval_ids(keyMetas)
  return keyMetas.filter(
    (meta) =>
      metric_evals.has(meta.evalId) &&
      meta.direction === "informational" &&
      definition_for_score_key(meta.scoreKey) === null,
  ).length
}

/**
 * The axes shown before the user picks their own: the highest-ranked ones the
 * task has, capped for legibility, returned in ring order.
 *
 * The ranking is what survives the cap. Cost, tokens and speed lead because
 * every task has them; then the counts a code eval had to read the trace to
 * know; then the second-order token and latency breakdowns; and the
 * input/output split last, since it only restates the total.
 */
export function default_metric_axis_keys(
  axes: MetricAxis[],
  max: number = DEFAULT_METRIC_AXIS_COUNT,
): string[] {
  const rank = (axis: MetricAxis): number =>
    definition_for_quantity(axis.quantity)?.defaultRank ?? UNKNOWN_DEFAULT_RANK
  const kept = new Set(
    axes
      .map((axis, index) => ({ axis, index }))
      // Ties fall back to ring order, so the set is a pure function of the axes
      .sort((a, b) => rank(a.axis) - rank(b.axis) || a.index - b.index)
      .slice(0, Math.max(max, 0))
      .map((entry) => entry.axis.key),
  )
  // Returned in ring order, so the selection reads the same way the chart does
  return axes.filter((axis) => kept.has(axis.key)).map((axis) => axis.key)
}

/**
 * An axis label broken onto two lines, on a word boundary.
 *
 * Naming an axis for its virtue costs characters - "Input Token Economy" where
 * the raw key said "Input Tokens" - and the two radars share a page, so each is
 * about 480px wide. echarts centres an axis name on its axis tip, which puts
 * the leftmost and rightmost labels half outside the canvas and clips them.
 * Its own `width`/`overflow` wrapping does not apply to radar axis names, so
 * the break is placed here: at the word boundary that leaves the two lines
 * closest in length, which keeps the block squarest around its tip. Ties go to
 * the later boundary, so "First Reply Speed" breaks after "Reply" rather than
 * stranding "First" on a line of its own.
 */
export function wrap_axis_label(label: string, maxChars: number = 13): string {
  if (label.length <= maxChars) return label
  const words = label.split(" ")
  if (words.length < 2) return label
  let best = 1
  let bestDelta = Infinity
  for (let index = 1; index < words.length; index++) {
    const left = words.slice(0, index).join(" ").length
    const right = words.slice(index).join(" ").length
    const delta = Math.abs(left - right)
    if (delta <= bestDelta) {
      bestDelta = delta
      best = index
    }
  }
  return `${words.slice(0, best).join(" ")}\n${words.slice(best).join(" ")}`
}

/**
 * The runs of same-family axes on the metrics ring, in the order they are drawn.
 *
 * The families were already contiguous - `compare_axes` sees to that - but
 * contiguity is a property of the DATA, and a reader looking at sixteen labels
 * in one weight of grey has no way to see it. These runs are what the chart
 * draws an arc for and what the key under the title names, so both are derived
 * from the same list and cannot disagree about where a family ends.
 *
 * The geometry is shared with the quality radar - see `./family_bands`, which
 * is also where the single-family and empty cases are explained.
 */
export function metric_family_bands(axes: MetricAxis[]): FamilyBand[] {
  return family_bands(
    axes.map((axis) => ({
      family: axis.family,
      label: METRIC_FAMILY_LABELS[axis.family],
    })),
  )
}

/**
 * How a metric is named and grouped in a TABLE of raw values, as opposed to on
 * the ring.
 *
 * The two need different names and this is the whole reason the catalog carries
 * both. A radar can only say "further from the centre is better", so its axes
 * are named for the virtue - "Speed", "Cost Efficiency" - and the geometry then
 * agrees with the label. A table prints the raw number, where higher is very
 * often worse, and "Total Latency 42,423.91 ms" under a heading that says
 * "Speed" would be telling the reader the opposite of what the row says. So the
 * table takes `valueLabel`, the plain name of the quantity, which is the same
 * choice the tooltips already make ("Cost: $0.0123", never "Cost Efficiency").
 *
 * The FAMILY headings are shared between the two, and can be: they are nouns
 * for a subject area ("Tokens", "Speed"), not claims about which end is good.
 *
 * Total, unlike the axis builders: a table shows every row it is given, so a
 * key the catalog has never heard of gets its plain label and lands in "Other"
 * rather than being dropped.
 */
export function metric_row_info(scoreKey: string): {
  family: MetricFamily
  label: string
} {
  const definition = definition_for_score_key(scoreKey)
  return definition
    ? { family: definition.family, label: definition.valueLabel }
    : { family: "other", label: score_key_label(scoreKey) }
}

/**
 * What a score row is called in the track it belongs to.
 *
 * The two tracks name the same kind of thing differently, for the reason
 * `metric_row_info` sets out: a quality row keeps its score key's own name, a
 * performance row takes the plain name of the quantity from the catalog. That
 * is one rule, and it is written here once because three surfaces read it - the
 * two comparison tables and the Hidden menus that offer their rows back. A menu
 * that derived its own label offered "Latency Ms Turn1" back for a row the
 * table had called "Turn 1 Latency", which reads as a different row.
 *
 * The metrics eval ids are passed in rather than recomputed so the caller's
 * reactive statement lists them as a dependency.
 */
export function score_row_label(
  meta: ScoreKeyMeta,
  metricEvalIds: Set<string>,
): string {
  return metricEvalIds.has(meta.evalId)
    ? metric_row_info(meta.scoreKey).label
    : score_key_label(meta.scoreKey)
}

/** The catalog's family for a usage rollup key, so the rollup rows sort into it */
export function usage_row_family(usageKey: string): MetricFamily {
  return (
    USAGE_METRIC_AXES.find((axis) => axis.key === usageKey)?.family ?? "other"
  )
}

/** The box a radar is drawn into, in px */
export interface RadarFitBox {
  width: number
  height: number
}

/** One axis name, where it points and how big it is */
export interface RadarAxisLabel {
  /** The indicator's angle as echarts lays it out: radians, y up, 0 due east */
  angle: number
  width: number
  height: number
}

/** What has to fit around the ring, in px */
export interface RadarFitInsets {
  /** Room reserved at the bottom of the box for the legend */
  legendHeight: number
  /** Ring to the anchor of an axis name, including the family band */
  labelGap: number
  /** Breathing room against the edge of the box */
  pad: number
}

export interface RadarFit {
  cx: number
  cy: number
  radius: number
}

export const MIN_RADAR_RADIUS = 40

/**
 * Where echarts puts an axis name, as a box around its anchor.
 *
 * Not a detail that can be waved at with "half the label hangs past the tip".
 * A radar builds its names at `nameLocation: 'end'`, which anchors the text at
 * the tip and lays it AWAY from the centre - so a name on the east side starts
 * at the tip and runs its FULL width to the right, and it is the whole label,
 * not half of it, that has to fit between the ring and the edge. Only the two
 * axes that are exactly vertical are centred horizontally, and those are the
 * ones that hang their full height above or below instead.
 *
 * Offsets are relative to the anchor, in screen coordinates with y downward.
 */
function axis_label_box(label: RadarAxisLabel): {
  left: number
  right: number
  top: number
  bottom: number
} {
  const cos = Math.cos(label.angle)
  const sin = Math.sin(label.angle)
  // echarts' own test for "this axis is vertical", to the same tolerance
  const vertical = Math.abs(cos) < 1e-4
  if (vertical) {
    return {
      left: -label.width / 2,
      right: label.width / 2,
      // Above the anchor at the top of the ring, below it at the bottom
      top: sin > 0 ? -label.height : 0,
      bottom: sin > 0 ? 0 : label.height,
    }
  }
  return {
    left: cos > 0 ? 0 : -label.width,
    right: cos > 0 ? label.width : 0,
    top: -label.height / 2,
    bottom: label.height / 2,
  }
}

/** How far the ring and its names reach from the centre, at a given radius */
function radar_envelope(
  radius: number,
  labels: RadarAxisLabel[],
  labelGap: number,
): { left: number; right: number; top: number; bottom: number } {
  // The ring itself, before any name is placed
  let left = -radius
  let right = radius
  let top = -radius
  let bottom = radius
  for (const label of labels) {
    const reach = radius + labelGap
    const anchorX = reach * Math.cos(label.angle)
    const anchorY = -reach * Math.sin(label.angle)
    const box = axis_label_box(label)
    left = Math.min(left, anchorX + box.left)
    right = Math.max(right, anchorX + box.right)
    top = Math.min(top, anchorY + box.top)
    bottom = Math.max(bottom, anchorY + box.bottom)
  }
  return { left, right, top, bottom }
}

/**
 * Centre and radius for a radar that fills its box.
 *
 * echarts sizes a radar as a percentage of `min(width, height) / 2`, which is
 * the wrong quantity twice over. This chart's box is far taller than it is wide
 * at every layout the page produces - it shares a grid row with the eval-score
 * radar, whose height it has to match - so the percentage resolved against the
 * width, and then had to be conservative enough that the names still cleared
 * the sides at any axis count. The result was a small ring adrift in a tall
 * card with the height doing nothing.
 *
 * So the radius is solved against where the names will actually land rather
 * than guessed from the widest one. That distinction is most of the gain: the
 * long names on this chart sit on the diagonals, where a name costs little
 * horizontal room, while the axes that do reach the sides carry short ones. A
 * single worst-case number would price every axis as though it were the widest
 * name pointing due east.
 *
 * Solved by bisection because the envelope is a max over per-axis boxes and
 * turns over as the alignment flips - monotone in the radius, but not worth
 * inverting in closed form for a number that is recomputed on resize. `cy`
 * comes back rather than being a fixed percentage: what is left after the
 * legend is what the ring is centred in, and reserving legend room by pushing
 * the centre up would waste the same space again at the top.
 *
 * A box too small for its own labels has no feasible radius, so the result is
 * floored at one that still draws a ring rather than solving negative.
 */
export function fit_radar(
  box: RadarFitBox,
  labels: RadarAxisLabel[],
  insets: RadarFitInsets,
): RadarFit {
  const cx = box.width / 2
  const availableHeight = box.height - insets.legendHeight - insets.pad * 2
  const fits = (radius: number): boolean => {
    const envelope = radar_envelope(radius, labels, insets.labelGap)
    return (
      cx + envelope.left >= insets.pad &&
      cx + envelope.right <= box.width - insets.pad &&
      envelope.bottom - envelope.top <= availableHeight
    )
  }

  let low = MIN_RADAR_RADIUS
  let high = Math.max(box.width, box.height)
  for (let step = 0; step < 40; step++) {
    const mid = (low + high) / 2
    if (fits(mid)) {
      low = mid
    } else {
      high = mid
    }
  }
  const radius = Math.max(low, MIN_RADAR_RADIUS)

  // Centre what the ring and its names occupy in the room that is left, so the
  // slack a circle cannot use is shared between the top and the legend.
  const envelope = radar_envelope(radius, labels, insets.labelGap)
  const used = envelope.bottom - envelope.top
  const slack = Math.max(availableHeight - used, 0)
  return {
    cx,
    cy: insets.pad + slack / 2 - envelope.top,
    radius,
  }
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
    case "ratio":
      // Deliberately not clamped: a hit rate above 100% is a provider
      // accounting bug, and hiding it would be hiding the only sign of one.
      return `${(value * 100).toFixed(1)}%`
    case "count":
      return value.toLocaleString(undefined, { maximumFractionDigits: 2 })
  }
}
