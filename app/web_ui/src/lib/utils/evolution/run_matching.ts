// Which conversations a comparison is actually made over.
//
// Every number on the compare page is a mean over whatever eval runs happen to
// exist for each run config. Two configs can be drawn side by side on the same
// axis while one was measured on 148 conversations and the other on 11, with
// barely any items in common — and the page says nothing about it. That is not
// noise, it is a different comparison than the one the reader thinks they are
// looking at.
//
// A matching predicate makes the BASIS explicit and selectable:
//
//   all     every run in the split-scoped universe (today's behavior)
//   shared  only items EVERY basis config has a non-skipped run for
//   length  shared, and the configs' total_tokens on that item within 1.5x
//   tools   shared, and the configs' tool_calls on that item within 1.5x
//
// Matching is per EVAL and per ITEM. Never global across evals: different evals
// legitimately hold disjoint item universes by design (a write-correctness eval
// and a tool-error eval score different inputs), so an intersection taken across
// evals would zero out a page that is working perfectly. An eval whose basis
// configs share nothing zeroes out only itself.
//
// ---------------------------------------------------------------------------
// What these predicates are, and what they are NOT
//
// `shared` is a straight honesty upgrade: same items, so the difference between
// two means is a difference between the configs rather than between two sets of
// scenarios. It costs almost nothing in practice.
//
// `length` and `tools` are NOT variance reducers and NOT controls. Measured
// same-item cross-config correlation of tool_calls is r = 0.26 over 10,309
// pairs: conversation shape is mostly config behavior plus stochastic
// wandering, not item difficulty. Conditioning on it selects exactly the
// conversations where neither config wandered — a POST-TREATMENT variable — and
// therefore biases toward the null on precisely the failures that wandering
// causes. They are diagnostic lenses ("among comparably-shaped conversations,
// who scores better?") for separating "worse model" from "took a different
// path". UI copy says "among conversations of similar length", never
// "controlled for length".
//
// One consequence worth stating wherever `length` is offered: matching on total
// tokens and then reading the COST axis compares unit price, not workload. Two
// configs held to within 1.5x on tokens differ on cost mostly by what their
// providers charge per token. Under `all`, the same cost gap also contains
// however differently the two configs wandered.
//
// ---------------------------------------------------------------------------
// Tolerance is fixed at 1.5x with no dial, deliberately. Measured over 420+
// item-pairs, the same item under different configs has a tool_calls ratio of
// p50 1.71x and p90 4.54x, so:
//   - an absolute band (±2 calls) is scale-broken — ±2 means something
//     different at 4 calls than at 40;
//   - 1.5x keeps 51-58% of shared items pairwise, ~36% three-way, and is
//     sayable in one phrase ("within 1.5x of each other");
//   - 2.0x keeps 78-84% but admits pairs where one config did double the work,
//     which is no longer "similar shape".
// A dial would also invite tuning the gate until the preferred config wins,
// which is the same argument the price/latency chart's quality floor makes for
// round numbers instead of a slider.

import type { components } from "$lib/api_schema"
import { score_type_range } from "$lib/utils/formatters"
import { is_metric_eval } from "./metric_axes"
import type { LensData, ScoreKeyMeta } from "./score_lens"
import { score_key_id } from "./score_lens"
import { interval_half_width_pp, wilson_interval } from "./score_intervals"

type EvalRunIndexResponse = components["schemas"]["EvalRunIndexResponse"]
type EvalRunIndexRow = components["schemas"]["EvalRunIndexRow"]

/** Per-run rows for each basis config, keyed by run config id. */
export type RunIndexes = Record<string, EvalRunIndexResponse>

export type MatchPredicate = "all" | "shared" | "length" | "tools"

export const MATCH_PREDICATES: MatchPredicate[] = [
  "all",
  "shared",
  "length",
  "tools",
]

export const MATCH_LABELS: Record<MatchPredicate, string> = {
  all: "All runs",
  shared: "Shared inputs",
  length: "Similar length",
  tools: "Similar tool use",
}

/**
 * How far apart two configs' shape may be on the same item and still count as
 * comparably shaped: max/min of the basis values. See the header for why it is
 * 1.5, and why it is not adjustable.
 */
export const SHAPE_RATIO_LIMIT = 1.5

/**
 * Below this many matched conversations on an eval, the page warns. Chosen
 * where a 95% Wilson half-width at p=0.5 crosses about ±26pp — past there the
 * interval is wider than most differences anyone is arguing about.
 */
export const MIN_MATCHED_N = 10

/** The score key a shape predicate reads, and the eval that carries it. */
export interface ShapeSource {
  evalId: string
  scoreKey: string
}

export interface MatchEvalSummary {
  evalId: string
  /** Rows this eval has per basis config, before matching */
  universe_by_config: Record<string, number>
  /** Items every basis config has a non-skipped run for */
  shared: number
  /** Items that survived the predicate */
  matched: number
  /**
   * Shared items dropped because at least one basis config had no shape value
   * for them. Zero under `all` and `shared`.
   */
  missing_shape: number
}

export interface MatchResult {
  /** What the reader asked for */
  requested: MatchPredicate
  /**
   * What was applied. Differs from `requested` only when matching is not
   * meaningful — a basis of fewer than two configs, where every predicate is
   * the identity — in which case it is "all".
   */
  applied: MatchPredicate
  /** evalId -> the item ids the comparison is over */
  items_by_eval: Map<string, Set<string>>
  evals: MatchEvalSummary[]
  /**
   * Basis configs that carry no shape value at all for the active predicate.
   * Named rather than silently zeroing the page: "this config has no tool-call
   * metrics" is a fact about the data, and it is the only explanation for a
   * chart that has just gone empty.
   */
  configs_missing_shape: string[]
}

export interface MatchedUsage {
  mean_cost: number | null
  mean_total_tokens: number | null
  mean_input_tokens: number | null
  mean_output_tokens: number | null
  mean_latency_ms: number | null
  /** Distinct conversations behind the means */
  n_conversations: number
}

/** URL value -> predicate. Anything unknown is the default, not an error. */
export function parse_match_param(value: string | null): MatchPredicate {
  if (value && (MATCH_PREDICATES as string[]).includes(value)) {
    return value as MatchPredicate
  }
  return "all"
}

/**
 * Predicate -> URL value, or null for the default so it stays out of the URL —
 * the same omitted-default discipline the split control uses.
 */
export function match_param(predicate: MatchPredicate): string | null {
  return predicate === "all" ? null : predicate
}

/**
 * Where a shape predicate reads its per-run number.
 *
 * `length` needs none of this: total_tokens rides on every index row, from the
 * run's own usage, so it works for any config that has ever run.
 *
 * `tools` has no such universal source. Tool calls are only recorded as a
 * per-run score by a metrics eval (all-custom score keys — see is_metric_eval),
 * and only some configs have ever been run against one. That is inherent:
 * nothing else counts tool calls without parsing traces.
 *
 * When several metrics evals carry a `tool_calls` key, the one with the most
 * rows across the basis wins, so the predicate reads from the eval that can
 * actually answer for these configs. With no indexes to count, the tie breaks
 * on eval id so the choice is at least deterministic.
 */
export function tool_call_source(
  keyMetas: ScoreKeyMeta[],
  indexes?: RunIndexes,
): ShapeSource | null {
  const by_eval = new Map<string, ScoreKeyMeta[]>()
  for (const meta of keyMetas) {
    const group = by_eval.get(meta.evalId) ?? []
    group.push(meta)
    by_eval.set(meta.evalId, group)
  }

  const candidates: ShapeSource[] = []
  for (const [evalId, metas] of by_eval) {
    if (!is_metric_eval(metas)) continue
    for (const meta of metas) {
      if (meta.scoreKey === "tool_calls") {
        candidates.push({ evalId, scoreKey: meta.scoreKey })
      }
    }
  }
  if (candidates.length === 0) {
    return null
  }

  let best: ShapeSource | null = null
  let best_coverage = -1
  for (const candidate of [...candidates].sort((a, b) =>
    a.evalId.localeCompare(b.evalId),
  )) {
    let coverage = 0
    for (const index of Object.values(indexes ?? {})) {
      for (const entry of index.evals) {
        if (entry.eval_id !== candidate.evalId) continue
        for (const row of entry.rows) {
          if (typeof row.scores?.[candidate.scoreKey] === "number") coverage++
        }
      }
    }
    if (coverage > best_coverage) {
      best_coverage = coverage
      best = candidate
    }
  }
  return best
}

/** evalId -> itemId -> row, for one config. Rows with no item id are skipped. */
function rows_by_eval(index: EvalRunIndexResponse | undefined) {
  const by_eval = new Map<string, Map<string, EvalRunIndexRow>>()
  if (!index) return by_eval
  for (const entry of index.evals) {
    if (!entry.eval_id) continue
    const rows = by_eval.get(entry.eval_id) ?? new Map()
    for (const row of entry.rows) {
      if (!row.item_id) continue
      // The server already keeps one row per item; this is belt and braces so
      // a hand-made payload cannot double-count an item.
      if (!rows.has(row.item_id)) rows.set(row.item_id, row)
    }
    by_eval.set(entry.eval_id, rows)
  }
  return by_eval
}

/** Whether a set of same-item shape values is within the tolerance. */
function within_ratio(values: number[]): boolean {
  if (values.length === 0) return false
  let lo = Infinity
  let hi = -Infinity
  for (const value of values) {
    if (!Number.isFinite(value)) return false
    lo = Math.min(lo, value)
    hi = Math.max(hi, value)
  }
  // A zero (or negative) floor has no ratio: "0 tool calls vs 3" is an
  // unbounded difference, not a small one, and 0-vs-0 is a pair of
  // conversations neither config did any work in. Both are excluded rather
  // than being quietly treated as a perfect match.
  if (lo <= 0) return false
  return hi / lo <= SHAPE_RATIO_LIMIT
}

/**
 * The items each eval's comparison is over, given a basis and a predicate.
 *
 * The basis is the PINNED set, not the visible one. Legend-hiding on this page
 * is documented as decluttering an image rather than removing a config from the
 * comparison (the tables keep hidden configs' columns), so a legend toggle must
 * not silently change every mean and every N on the page.
 */
export function matched_items_by_eval(
  indexes: RunIndexes,
  basisIds: string[],
  predicate: MatchPredicate,
  toolSource: ShapeSource | null = null,
): MatchResult {
  // One config cannot be matched against anything, so every predicate is the
  // identity on it. Reported as applied="all" rather than hard-disabled: a URL
  // can arrive with a predicate before the pins have restored.
  const applied: MatchPredicate = basisIds.length < 2 ? "all" : predicate

  const indexed = new Map(
    basisIds.map((id) => [id, rows_by_eval(indexes[id])] as const),
  )

  const eval_ids: string[] = []
  const seen_evals = new Set<string>()
  for (const id of basisIds) {
    for (const evalId of indexed.get(id)?.keys() ?? []) {
      if (!seen_evals.has(evalId)) {
        seen_evals.add(evalId)
        eval_ids.push(evalId)
      }
    }
  }

  const items_by_eval = new Map<string, Set<string>>()
  const evals: MatchEvalSummary[] = []
  const configs_missing_shape = new Set<string>()

  for (const evalId of eval_ids) {
    const universe_by_config: Record<string, number> = {}
    for (const id of basisIds) {
      universe_by_config[id] = indexed.get(id)?.get(evalId)?.size ?? 0
    }

    // Union first: it is the universe the "of N" phrasing is against, and it is
    // what `all` keeps.
    const union = new Set<string>()
    for (const id of basisIds) {
      for (const itemId of indexed.get(id)?.get(evalId)?.keys() ?? []) {
        union.add(itemId)
      }
    }

    const shared = new Set<string>()
    for (const itemId of union) {
      if (basisIds.every((id) => indexed.get(id)?.get(evalId)?.has(itemId))) {
        shared.add(itemId)
      }
    }

    let kept: Set<string>
    let missing_shape = 0
    if (applied === "all") {
      kept = union
    } else if (applied === "shared") {
      kept = shared
    } else {
      kept = new Set<string>()
      for (const itemId of shared) {
        const values: number[] = []
        let complete = true
        for (const id of basisIds) {
          const value =
            applied === "length"
              ? shape_length(indexed.get(id), evalId, itemId)
              : shape_tools(indexed.get(id), toolSource, itemId)
          if (value === null) {
            complete = false
            continue
          }
          values.push(value)
        }
        if (!complete) {
          missing_shape++
          continue
        }
        if (within_ratio(values)) kept.add(itemId)
      }
    }

    items_by_eval.set(evalId, kept)
    evals.push({
      evalId,
      universe_by_config,
      shared: shared.size,
      matched: kept.size,
      missing_shape,
    })
  }

  // A config with no shape value ANYWHERE is a different problem from one that
  // lacks a value on some items, and it has a different remedy (run it against
  // a metrics eval), so it is reported separately.
  if (applied === "length" || applied === "tools") {
    for (const id of basisIds) {
      const rows = indexed.get(id)
      let any = false
      if (applied === "length") {
        for (const eval_rows of rows?.values() ?? []) {
          for (const row of eval_rows.values()) {
            if (typeof row.total_tokens === "number") any = true
          }
        }
      } else if (toolSource) {
        for (const row of rows?.get(toolSource.evalId)?.values() ?? []) {
          if (typeof row.scores?.[toolSource.scoreKey] === "number") any = true
        }
      }
      if (!any) configs_missing_shape.add(id)
    }
  }

  return {
    requested: predicate,
    applied,
    items_by_eval,
    evals,
    configs_missing_shape: [...configs_missing_shape],
  }
}

/** total_tokens for one config on one item, from the eval's own row. */
function shape_length(
  rows: Map<string, Map<string, EvalRunIndexRow>> | undefined,
  evalId: string,
  itemId: string,
): number | null {
  const value = rows?.get(evalId)?.get(itemId)?.total_tokens
  return typeof value === "number" ? value : null
}

/**
 * tool_calls for one config on one item, from the METRICS eval that records
 * them — a cross-eval lookup by item id, because the eval being matched
 * (a judge, say) does not count tool calls itself.
 */
function shape_tools(
  rows: Map<string, Map<string, EvalRunIndexRow>> | undefined,
  source: ShapeSource | null,
  itemId: string,
): number | null {
  if (!source) return null
  const value = rows?.get(source.evalId)?.get(itemId)?.scores?.[source.scoreKey]
  return typeof value === "number" ? value : null
}

/**
 * The same shape build_lens_data emits, recomputed over the matched rows only,
 * so every chart on the page picks the filtering up through the getters it
 * already reads.
 *
 * Two deliberate differences from the unfiltered build:
 *  - min-max normalization (custom/unknown score types) runs across the BASIS
 *    configs rather than every config on the task, because those are the only
 *    ones with matched rows. Within one predicate it stays internally
 *    consistent, which is what the radar's geometry needs.
 *  - percentComplete is carried over UNFILTERED. Completion is a claim about
 *    the full expected set — "have we finished running this eval" — and a
 *    predicate must not be able to redefine it into "have we finished the part
 *    I am looking at".
 * keyMetas are reused as-is: they are metadata about the score keys, not
 * aggregates over runs.
 */
export function build_matched_lens_data(
  lens_data: LensData,
  indexes: RunIndexes,
  basisIds: string[],
  matched: Map<string, Set<string>>,
): LensData {
  const raw = new Map<string, Map<string, number>>()
  const normalized = new Map<string, Map<string, number>>()
  const counts = new Map<string, Map<string, number>>()

  for (const runConfigId of basisIds) {
    const raw_scores = new Map<string, number>()
    const sample_sizes = new Map<string, number>()
    const rows = rows_by_eval(indexes[runConfigId])

    for (const [evalId, by_item] of rows) {
      const items = matched.get(evalId)
      if (!items || items.size === 0) continue
      const totals = new Map<string, number>()
      const n = new Map<string, number>()
      for (const itemId of items) {
        const row = by_item.get(itemId)
        if (!row) continue
        for (const [scoreKey, value] of Object.entries(row.scores ?? {})) {
          if (typeof value !== "number" || !Number.isFinite(value)) continue
          totals.set(scoreKey, (totals.get(scoreKey) ?? 0) + value)
          n.set(scoreKey, (n.get(scoreKey) ?? 0) + 1)
        }
      }
      for (const [scoreKey, total] of totals) {
        const count = n.get(scoreKey) ?? 0
        if (count <= 0) continue
        const key = score_key_id(evalId, scoreKey)
        raw_scores.set(key, total / count)
        sample_sizes.set(key, count)
      }
    }

    raw.set(runConfigId, raw_scores)
    normalized.set(runConfigId, new Map())
    counts.set(runConfigId, sample_sizes)
  }

  for (const meta of lens_data.keyMetas) {
    const key = score_key_id(meta.evalId, meta.scoreKey)
    let min = Infinity
    let max = -Infinity
    for (const raw_scores of raw.values()) {
      const value = raw_scores.get(key)
      if (value !== undefined) {
        min = Math.min(min, value)
        max = Math.max(max, value)
      }
    }
    for (const [runConfigId, raw_scores] of raw) {
      const value = raw_scores.get(key)
      if (value === undefined) continue
      const range = score_type_range(meta.type)
      let scaled = range
        ? Math.min(
            1,
            Math.max(0, (value - range.min) / (range.max - range.min)),
          )
        : max > min
          ? (value - min) / (max - min)
          : 0.5
      if (meta.direction === "lower_is_better") {
        scaled = 1 - scaled
      }
      normalized.get(runConfigId)?.set(key, scaled)
    }
  }

  return {
    keyMetas: lens_data.keyMetas,
    raw,
    normalized,
    counts,
    percentComplete: lens_data.percentComplete,
  }
}

/**
 * Cost, tokens and latency over the matched conversations, per config.
 *
 * Deduped BY ITEM across evals, and that is a real difference from the server's
 * mean_usage, which counts a conversation once per eval that scored it — with
 * trace reuse the same conversation weighs three times there if three evals
 * cover it. This rollup weighs it once. So switching a predicate on can move
 * cost or latency even when N barely changes, because the weighting changed
 * too; the banner says so.
 *
 * Coverage rule follows the server's: a metric is null when fewer than half the
 * matched conversations recorded it, so a mean over a handful of rows is never
 * printed as if it were the config's cost.
 */
export function build_matched_usage(
  indexes: RunIndexes,
  basisIds: string[],
  matched: Map<string, Set<string>>,
): Map<string, MatchedUsage> {
  const usage = new Map<string, MatchedUsage>()

  for (const runConfigId of basisIds) {
    const rows = rows_by_eval(indexes[runConfigId])
    // First row wins per item: the same conversation scored by three evals is
    // one conversation, and its usage is the task run's, not the eval's.
    const per_item = new Map<string, EvalRunIndexRow>()
    for (const [evalId, by_item] of rows) {
      const items = matched.get(evalId)
      if (!items) continue
      for (const itemId of items) {
        if (per_item.has(itemId)) continue
        const row = by_item.get(itemId)
        if (row) per_item.set(itemId, row)
      }
    }

    const totals = { cost: 0, total: 0, input: 0, output: 0, latency: 0 }
    const seen = { cost: 0, total: 0, input: 0, output: 0, latency: 0 }
    for (const row of per_item.values()) {
      if (typeof row.cost === "number") {
        totals.cost += row.cost
        seen.cost++
      }
      if (typeof row.total_tokens === "number") {
        totals.total += row.total_tokens
        seen.total++
      }
      if (typeof row.input_tokens === "number") {
        totals.input += row.input_tokens
        seen.input++
      }
      if (typeof row.output_tokens === "number") {
        totals.output += row.output_tokens
        seen.output++
      }
      if (typeof row.total_llm_latency_ms === "number") {
        totals.latency += row.total_llm_latency_ms
        seen.latency++
      }
    }

    const n = per_item.size
    const threshold = n * 0.5
    const mean = (total: number, count: number): number | null =>
      n > 0 && count > 0 && count >= threshold ? total / count : null

    usage.set(runConfigId, {
      mean_cost: mean(totals.cost, seen.cost),
      mean_total_tokens: mean(totals.total, seen.total),
      mean_input_tokens: mean(totals.input, seen.input),
      mean_output_tokens: mean(totals.output, seen.output),
      mean_latency_ms: mean(totals.latency, seen.latency),
      n_conversations: n,
    })
  }

  return usage
}

/**
 * How big a difference this many runs could hide, in percentage points.
 *
 * Derived rather than quoted: a 95% Wilson half-width at p=0.5 (the widest
 * point, so the figure is the honest worst case for a pass/fail rate), doubled
 * because a comparison has an interval on BOTH sides. Rounded to 5pp — it is an
 * order-of-magnitude claim about what the sample can resolve, and printing
 * "59.5pp" would dress it up as a measurement.
 *
 * Null when there is no n to compute one from.
 */
export function undetectable_difference_pp(n: number): number | null {
  const interval = wilson_interval(0.5, n)
  if (!interval) return null
  const pp = interval_half_width_pp(interval) * 2
  return Math.max(5, Math.round(pp / 5) * 5)
}
