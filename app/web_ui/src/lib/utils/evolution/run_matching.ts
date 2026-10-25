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
//   all     every run in the split-scoped universe — the DEFAULT, see
//           DEFAULT_MATCH_PREDICATE
//   shared  only items EVERY basis config has a non-skipped run for
//   length  shared, and the configs' total_tokens on that item within 1.5x
//   tools   shared, and the configs' tool_calls on that item within 1.5x
//
// Matching is per ITEM but keyed on the EXECUTION wherever two evals are read
// together: one item under one run config can hold two different driven
// conversations (trace reuse makes them one, a resample or a job race makes
// them two), and the item id is identical in both cases. Every join here -
// the tools shape source, the usage rollup - goes through execution identity
// for that reason. See same_execution.
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
// The shape predicates are built for TWO OR THREE configs and say so. Mutual
// matching decays with the size of the basis and it decays because of the
// configs rather than the items: 1.5x survival on one task's six-config basis
// runs 55% (k=2) -> 32% (3) -> 20% (4) -> 13% (5) -> 8.8% (6), and the
// configs' MEDIAN token counts already span 1.75x, more than the gate itself.
// Past the point where a majority of the readable evals are left under
// MIN_MATCHED_N the lens reports itself unavailable rather than drawing a mean
// over eight coincidences (shape_basis_usable), and the page falls back to
// `shared` and says why. Widening the tolerance is not the fix - at 2.5x four
// of that task's evals were still under n=10, and a dial only moves the
// question to "which tolerance makes my config win".
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
 * What the page compares on when nobody has said.
 *
 * `shared` rather than `all`, and this is the one line that decides it. The
 * default view is the one almost everybody reads, and at `all` it pools
 * whatever runs each config happens to have and calls the result a comparison -
 * measured on a real task, two configs on one axis over 11 runs and 148 runs
 * with barely any items in common. `shared` is the same comparison made
 * honestly, and it costs almost nothing where it matters: on healthy evals it
 * keeps 76-100% of the conversations. The shape predicates are drill-downs and
 * are not defaults for the reason in the header - they condition on a
 * post-treatment variable.
 *
 * A basis of fewer than two configs has nothing to intersect, so matching is
 * the identity there and the applied predicate reports as "all" (see
 * matched_items_by_eval). Reverting the whole change is this constant.
 */
export const DEFAULT_MATCH_PREDICATE: MatchPredicate = "all"

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
  /** Items at least one basis config has a run for — the honest denominator */
  universe: number
  /** Items every basis config has a non-skipped run for */
  shared: number
  /** Items that survived the predicate */
  matched: number
  /**
   * What the REQUESTED shape predicate would have kept, even when it was not
   * applied. Null unless a shape predicate was asked for. This is the number
   * behind "6 configs keep about 9% of the conversations".
   */
  shape_matched: number | null
  /**
   * Shared items dropped because at least one basis config had no shape value
   * for them, or had one from a different conversation. Zero under `all` and
   * `shared`.
   */
  missing_shape: number
  /**
   * Whether this eval measures metrics rather than criteria (all-custom score
   * keys — see is_metric_eval). Carried here because a metrics eval typically
   * runs over a different, much larger item universe than the graded evals, so
   * pooling the two into one retention figure states a denominator that
   * belongs to neither.
   */
  is_metric: boolean
}

/** Why the applied predicate is not the requested one. */
export type MatchFallback =
  /** Fewer than two basis configs: every predicate is the identity */
  | "single_config"
  /** A shape predicate left too little on too many evals to be read */
  | "shape_too_thin"

export interface MatchResult {
  /** What the reader asked for */
  requested: MatchPredicate
  /**
   * What was applied. See `fallback` for why it can differ from `requested`.
   */
  applied: MatchPredicate
  /** Null when `applied` is `requested` */
  fallback: MatchFallback | null
  /** evalId -> the item ids the comparison is over */
  items_by_eval: Map<string, Set<string>>
  evals: MatchEvalSummary[]
  /**
   * Basis configs that carry no shape value at all for the requested
   * predicate. Named rather than silently zeroing the page: "this config has
   * no tool-call metrics" is a fact about the data, and it is the only
   * explanation for a chart that has just gone empty.
   */
  configs_missing_shape: string[]
}

/**
 * Whether a shape predicate has left enough behind to be worth reading.
 *
 * Mutual matching across k configs decays fast, and it decays because of the
 * configs rather than the items: measured over one task's six-config basis,
 * 1.5x survival on the same items falls 55% (k=2) -> 32% (3) -> 20% (4) ->
 * 13% (5) -> 8.8% (6), and the configs' MEDIAN token counts already span 1.75x
 * — more than the gate itself. At six configs the predicate is not selecting
 * comparably-shaped conversations, it is selecting the handful where six
 * different models happened to converge, and a mean over eight of them is not
 * a measurement of anything.
 *
 * The answer is to say so, not to widen the gate: at a tolerance of 2.5x four
 * of that task's evals were still under n=10, and a dial would only move the
 * question to "which tolerance makes my config win". So the lens reports
 * itself unavailable at this basis, the page falls back to `shared` and says
 * why, and the exits it offers are measurable ones — drop the config that
 * costs the most, or compare two or three.
 *
 * Only evals the predicate actually COST something get a vote: those whose
 * shared set was readable (>= MIN_MATCHED_N) and whose shape-matched set is
 * not. An eval already too thin at `shared` is unreadable either way, so
 * falling back on its account would take away a drill-down the reader asked
 * for and give nothing back - the small-set chip is what covers that case. A
 * basis where no eval was readable to begin with is left alone for the same
 * reason.
 *
 * Graded evals only. A metrics eval runs over its own much larger universe and
 * would carry the vote on a question about the criteria.
 */
export function shape_basis_usable(evals: MatchEvalSummary[]): boolean {
  const voters = evals.filter(
    (entry) => !entry.is_metric && entry.shared >= MIN_MATCHED_N,
  )
  if (voters.length === 0) {
    return true
  }
  const thin = voters.filter(
    (entry) => (entry.shape_matched ?? entry.matched) < MIN_MATCHED_N,
  ).length
  return thin * 2 <= voters.length
}

/** One eval's cheapest way out of a matched set too small to read. */
export interface RecoveryHint {
  evalId: string
  /** The basis config whose absence recovers the most on this eval */
  configId: string
  /** Matched now */
  from: number
  /** Matched with that config out of the basis */
  to: number
}

/**
 * What dropping one config from the basis would buy, per eval.
 *
 * "Too few matched conversations" is only actionable if the reader is told
 * WHICH config is costing them and how much - "dropping DeepSeek V4 Pro takes
 * Skill read from 5 to 12" is a decision; "n is small" is a shrug. Computed by
 * re-running the matcher over each basis-minus-one, so the number quoted is
 * exactly the number the reader gets if they act on it, rather than an
 * estimate from the universe counts that would be wrong whenever the item sets
 * overlap unevenly.
 *
 * Only evals that are actually thin, and only where dropping somebody helps.
 * Worst eval first.
 */
export function recovery_hints(
  indexes: RunIndexes,
  basisIds: string[],
  predicate: MatchPredicate,
  toolSource: ShapeSource | null = null,
  isMetricEval: (evalId: string) => boolean = () => false,
): RecoveryHint[] {
  if (basisIds.length < 3) {
    // Dropping one of two leaves a basis of one, where every predicate is the
    // identity: true, and no use to anybody.
    return []
  }
  const current = matched_items_by_eval(
    indexes,
    basisIds,
    predicate,
    toolSource,
    isMetricEval,
  )
  const thin = current.evals.filter(
    (entry) =>
      !entry.is_metric && entry.universe > 0 && entry.matched < MIN_MATCHED_N,
  )
  if (thin.length === 0) {
    return []
  }

  const without = new Map<string, Map<string, number>>()
  for (const dropped of basisIds) {
    const result = matched_items_by_eval(
      indexes,
      basisIds.filter((id) => id !== dropped),
      predicate,
      toolSource,
      isMetricEval,
    )
    without.set(
      dropped,
      new Map(result.evals.map((entry) => [entry.evalId, entry.matched])),
    )
  }

  const hints: RecoveryHint[] = []
  for (const entry of thin) {
    let best: RecoveryHint | null = null
    for (const dropped of basisIds) {
      const to = without.get(dropped)?.get(entry.evalId) ?? 0
      if (to > entry.matched && (best === null || to > best.to)) {
        best = {
          evalId: entry.evalId,
          configId: dropped,
          from: entry.matched,
          to,
        }
      }
    }
    if (best) hints.push(best)
  }
  return hints.sort((a, b) => a.from - b.from || b.to - a.to)
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

/**
 * URL value -> predicate. Anything unknown is the default, not an error.
 *
 * An absent parameter is `all` (DEFAULT_MATCH_PREDICATE): a link that never
 * touched the control opens on the full, unfiltered basis, and a matched
 * basis is always an explicit choice carried in the URL.
 */
export function parse_match_param(value: string | null): MatchPredicate {
  if (value && (MATCH_PREDICATES as string[]).includes(value)) {
    return value as MatchPredicate
  }
  return DEFAULT_MATCH_PREDICATE
}

/**
 * Predicate -> URL value, or null for the default so it stays out of the URL —
 * the same omitted-default discipline the split control uses. `all` is the
 * default and stays implicit; every matched predicate serializes, so a shared
 * link always states the basis it was read under.
 */
export function match_param(predicate: MatchPredicate): string | null {
  return predicate === DEFAULT_MATCH_PREDICATE ? null : predicate
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
  isMetricEval: (evalId: string) => boolean = () => false,
): MatchResult {
  // One config cannot be matched against anything, so every predicate is the
  // identity on it. Reported as applied="all" rather than hard-disabled: a URL
  // can arrive with a predicate before the pins have restored.
  let applied: MatchPredicate = basisIds.length < 2 ? "all" : predicate
  let fallback: MatchFallback | null =
    applied === predicate ? null : "single_config"
  const shape_requested = applied === "length" || applied === "tools"

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

  const configs_missing_shape = new Set<string>()

  // Every candidate set is computed before anything is chosen, because the
  // choice is made ACROSS evals: a shape predicate that leaves most of them
  // unreadable is not applied at all (shape_basis_usable), and that verdict
  // cannot be reached one eval at a time.
  const per_eval = eval_ids.map((evalId) => {
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

    let shaped: Set<string> | null = null
    let missing_shape = 0
    if (shape_requested) {
      shaped = new Set<string>()
      for (const itemId of shared) {
        const values: number[] = []
        let complete = true
        for (const id of basisIds) {
          const value =
            applied === "length"
              ? shape_length(indexed.get(id), evalId, itemId)
              : shape_tools(indexed.get(id), toolSource, evalId, itemId)
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
        if (within_ratio(values)) shaped.add(itemId)
      }
    }

    return { evalId, universe_by_config, union, shared, shaped, missing_shape }
  })

  const draft: MatchEvalSummary[] = per_eval.map((entry) => ({
    evalId: entry.evalId,
    universe_by_config: entry.universe_by_config,
    universe: entry.union.size,
    shared: entry.shared.size,
    matched: (entry.shaped ?? entry.shared).size,
    shape_matched: entry.shaped?.size ?? null,
    missing_shape: entry.missing_shape,
    is_metric: isMetricEval(entry.evalId),
  }))

  // The one cross-eval decision: a shape predicate that has left a majority of
  // the graded evals under MIN_MATCHED_N is not a lens, it is a coincidence
  // filter. Fall back to `shared` - never to `all`, which would be a quiet
  // widening - and let the banner say so.
  if (shape_requested && !shape_basis_usable(draft)) {
    applied = "shared"
    fallback = "shape_too_thin"
  }

  const items_by_eval = new Map<string, Set<string>>()
  const evals: MatchEvalSummary[] = []
  for (const [i, entry] of per_eval.entries()) {
    const kept =
      applied === "all"
        ? entry.union
        : applied === "shared"
          ? entry.shared
          : entry.shaped ?? entry.shared
    items_by_eval.set(entry.evalId, kept)
    evals.push({ ...draft[i], matched: kept.size })
  }

  // A config with no shape value ANYWHERE is a different problem from one that
  // lacks a value on some items, and it has a different remedy (run it against
  // a metrics eval), so it is reported separately. Against the REQUESTED
  // predicate, since it is part of why the requested one could not be given.
  if (shape_requested) {
    for (const id of basisIds) {
      const rows = indexed.get(id)
      let any = false
      if (predicate === "length") {
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
    fallback,
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
 * them — a cross-eval lookup, because the eval being matched (a judge, say)
 * does not count tool calls itself.
 *
 * Keyed on the EXECUTION and not on the item, which is the whole difference
 * between this shape being a fact and being a coincidence. One item under one
 * run config can hold two different driven conversations: trace reuse makes
 * the metrics row and the judged row the same run, a resample or a job race
 * makes them two, and the item id is identical either way. Measured on one
 * task's six-config basis, 27 of 150 lookups on a single eval (18%) resolved
 * to a conversation the judged eval never scored, and another eval had 37
 * lookups land on no metrics row at all.
 *
 * So a value counts only when the metrics row and the row being matched name
 * the same execution. Anything else is a MISSING shape rather than a
 * substitute one: it drops the item and is counted in missing_shape, where
 * "these conversations have no tool-call record of their own" is something the
 * banner can say. Reading the other conversation's number would silently pass
 * or fail the ratio on evidence from a run nobody is looking at.
 */
function shape_tools(
  rows: Map<string, Map<string, EvalRunIndexRow>> | undefined,
  source: ShapeSource | null,
  evalId: string,
  itemId: string,
): number | null {
  if (!source) return null
  const target = rows?.get(evalId)?.get(itemId)
  const metrics = rows?.get(source.evalId)?.get(itemId)
  if (!target || !metrics) return null
  if (!same_execution(target, metrics)) return null
  const value = metrics.scores?.[source.scoreKey]
  return typeof value === "number" ? value : null
}

/**
 * Whether two rows scored the same run of the task.
 *
 * `execution_id` is the server's identity for the conversation itself (a hash
 * of the stored trace, or the record's own id when there is none). A payload
 * without the field predates it; treating that as "same item, same execution"
 * is what this code did before the field existed, so it is what an old payload
 * keeps getting rather than a page that matches nothing.
 */
function same_execution(a: EvalRunIndexRow, b: EvalRunIndexRow): boolean {
  if (a.execution_id === undefined || b.execution_id === undefined) return true
  return a.execution_id === b.execution_id
}

/**
 * The key a conversation is counted under. See same_execution for the
 * fallback: an old payload collapses per item, which is what this did before
 * executions were identifiable.
 */
function execution_key(row: EvalRunIndexRow): string {
  return row.execution_id ?? `item:${row.item_id}`
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
 * Deduped by EXECUTION across evals, and that is a real difference from the
 * server's mean_usage, which counts a conversation once per eval that scored
 * it — with trace reuse the same conversation weighs three times there if
 * three evals cover it. This rollup weighs it once. So switching a predicate
 * on can move cost or latency even when N barely changes, because the
 * weighting changed too; the banner says so.
 *
 * By execution rather than by item, which is not the same rule. Deduping by
 * item assumes an item is a conversation, and on a real task 85 of 756
 * cross-eval (config, item) pairs — 11% — held two genuinely different driven
 * conversations; collapsing those to one threw away half the recorded spend on
 * them ($28.87 discarded against $27.45 kept, on one basis). Both are counted
 * here, because both happened: the reader's config really did run that item
 * twice, and a cost mean that hides one of the two runs is not the cost of
 * this comparison.
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
    // One entry per conversation: the same run of the task scored by three
    // evals is one conversation, and its usage is the task run's, not the
    // eval's. Two different runs of one item are two.
    const per_execution = new Map<string, EvalRunIndexRow>()
    for (const [evalId, by_item] of rows) {
      const items = matched.get(evalId)
      if (!items) continue
      for (const itemId of items) {
        const row = by_item.get(itemId)
        if (!row) continue
        const key = execution_key(row)
        if (per_execution.has(key)) continue
        per_execution.set(key, row)
      }
    }

    const totals = { cost: 0, total: 0, input: 0, output: 0, latency: 0 }
    const seen = { cost: 0, total: 0, input: 0, output: 0, latency: 0 }
    for (const row of per_execution.values()) {
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

    const n = per_execution.size
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
