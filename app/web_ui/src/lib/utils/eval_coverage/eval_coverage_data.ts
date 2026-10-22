/**
 * Builds the nodes of the eval coverage chart from the page's data.
 *
 * Three kinds of node share one circle packing:
 * - "eval": an active eval. Its area is the share of the constitution it
 *   holds; its fill is its pass rate on the chosen run config.
 * - "planned": a spec with status "future". It claims the principles it is
 *   tagged with and is drawn as a dashed outline.
 * - "gap": a principle with no active or planned eval. Drawn as a dotted
 *   outline, so the hole in coverage is visible and named.
 *
 * Each principle's share is its weight from the constitution ("Weight: n",
 * 1 when absent) over the sum of weights. When the task description holds
 * no principles, areas come from priority (P0 largest) and there are no gaps.
 */

import type { Eval, Priority, Spec, SpecStatus } from "$lib/types"
import type { components } from "$lib/api_schema"
import {
  constitutionVersion,
  parseAmendments,
  parsePrinciples,
  parseRulings,
  principleWeights,
  rulingsByPrinciple,
  type Amendment,
  type Principle,
  type Ruling,
} from "./constitution"
import { buildCoverageModel, principlesFromTags } from "./coverage_model"

export type RunConfigEvalScoresSummary =
  components["schemas"]["RunConfigEvalScoresSummary"]

export type CoverageNodeKind = "eval" | "planned" | "gap"

export type CoverageNode = {
  id: string
  name: string
  kind: CoverageNodeKind
  href: string | null
  /** Share of the whole, 0..1. All nodes sum to 1. */
  weight: number
  pass_rate: number | null
  dataset_size: number | null
  principles: number[]
  priority: Priority | null
  status: SpecStatus | null
}

export type CoverageData = {
  nodes: CoverageNode[]
  principles: Principle[]
  /** Importance-weighted share of principles with an active eval. Null without a constitution. */
  covered: number | null
  /** Eval node ids that cover each principle. */
  coverers: Map<number, string[]>
  /** Planned node ids that claim each principle. */
  planned_for: Map<number, string[]>
  /** Importance share of each principle, 0..1; sums to 1. */
  shares: Map<number, number>
  /** Mean pass rate of the active evals covering each principle; null when none has a result. */
  health: Map<number, number | null>
  /** The active eval with the lowest pass rate, when any has one. */
  floor: CoverageNode | null
  active_count: number
  /** The court's rulings in the task description, in date order; empty when it has none. */
  rulings: Ruling[]
  amendments: Amendment[]
  /** Ruling ids per principle number, in date order. */
  rulings_for: Map<number, string[]>
  /** The version in the constitution's title, when it has one. */
  constitution_version: { version: string; date?: string } | null
}

export type CoverageInput = {
  specs: Spec[]
  evals: Eval[]
  task_description: string | null | undefined
  eval_scores: RunConfigEvalScoresSummary | null
  project_id: string
  task_id: string
}

function resolved_priority(spec: Spec, by_id: Map<string, Eval>): Priority {
  return (
    (spec.eval_id ? by_id.get(spec.eval_id)?.priority : null) ?? spec.priority
  )
}

function resolved_status(spec: Spec, by_id: Map<string, Eval>): SpecStatus {
  return (spec.eval_id ? by_id.get(spec.eval_id)?.status : null) ?? spec.status
}

/** Pass rate 0..1 from a run config's results for one eval, or null. */
export function pass_rate_for(
  eval_id: string,
  eval_data: Eval | undefined,
  scores: RunConfigEvalScoresSummary | null,
): { pass_rate: number | null; dataset_size: number | null } {
  const result = scores?.eval_results.find((r) => r.eval_id === eval_id)
  if (!result) return { pass_rate: null, dataset_size: null }
  const dataset_size = result.dataset_size ?? null
  const config = result.eval_config_result
  if (!config) return { pass_rate: null, dataset_size }
  const output_scores = eval_data?.output_scores ?? []
  const score_id = (name: string) =>
    name.toLowerCase().replace(/[^a-z0-9]+/g, "_")
  const pick =
    output_scores.find(
      (s) => s.type === "pass_fail" || s.type === "pass_fail_critical",
    ) ?? output_scores[0]
  const entries = Object.entries(config.results)
  const chosen = pick
    ? entries.find(([k]) => k === score_id(pick.name)) ?? entries[0]
    : entries[0]
  const mean = chosen?.[1]?.mean_score
  if (mean === null || mean === undefined)
    return { pass_rate: null, dataset_size }
  if (pick?.type === "five_star") {
    return {
      pass_rate: Math.max(0, Math.min(1, (mean - 1) / 4)),
      dataset_size,
    }
  }
  return { pass_rate: Math.max(0, Math.min(1, mean)), dataset_size }
}

/** The eval builder, with the principle handed over as the goal. */
export function builder_href(
  project_id: string,
  task_id: string,
  principle: Principle,
): string {
  const goal = `Principle ${principle.n}: ${principle.text}`
  return `/specs/${project_id}/${task_id}/builder?description=${encodeURIComponent(goal)}`
}

/** Area ratio by priority when there is no constitution: P0 is 8x a P3. */
function priority_weight(priority: Priority | null): number {
  const p = priority ?? 1
  return Math.pow(2, 3 - p)
}

function lowest(nodes: CoverageNode[]): CoverageNode | null {
  let out: CoverageNode | null = null
  for (const n of nodes) {
    if (n.kind !== "eval" || n.pass_rate === null) continue
    if (out === null || n.pass_rate < (out.pass_rate ?? 1)) out = n
  }
  return out
}

export function buildCoverageData(input: CoverageInput): CoverageData {
  const { specs, evals, project_id, task_id } = input
  const by_id = new Map(evals.map((e) => [e.id ?? "", e]))
  const principles = parsePrinciples(input.task_description)
  const rulings = parseRulings(input.task_description)
  const ledger = {
    rulings,
    amendments: parseAmendments(input.task_description),
    rulings_for: rulingsByPrinciple(rulings),
    constitution_version: constitutionVersion(input.task_description),
  }

  type Draft = Omit<CoverageNode, "weight">
  const active: Draft[] = []
  const planned: Draft[] = []
  const spec_eval_ids = new Set<string>()

  for (const spec of specs) {
    if (!spec.id) continue
    if (spec.eval_id) spec_eval_ids.add(spec.eval_id)
    const status = resolved_status(spec, by_id)
    if (status !== "active" && status !== "future") continue
    const eval_data = spec.eval_id ? by_id.get(spec.eval_id) : undefined
    const scores = spec.eval_id
      ? pass_rate_for(spec.eval_id, eval_data, input.eval_scores)
      : { pass_rate: null, dataset_size: null }
    const node: Draft = {
      id: spec.id,
      name: spec.name,
      kind: status === "active" ? "eval" : "planned",
      href: `/specs/${project_id}/${task_id}/${spec.id}`,
      pass_rate: scores.pass_rate,
      dataset_size: scores.dataset_size,
      principles: principlesFromTags(spec.tags),
      priority: resolved_priority(spec, by_id),
      status,
    }
    if (status === "active") active.push(node)
    else planned.push(node)
  }

  // Evals with no spec behind them (legacy evals).
  for (const eval_data of evals) {
    if (!eval_data.id || spec_eval_ids.has(eval_data.id)) continue
    const status = eval_data.status ?? "active"
    if (status !== "active" && status !== "future") continue
    const scores = pass_rate_for(eval_data.id, eval_data, input.eval_scores)
    const node: Draft = {
      id: eval_data.id,
      name: eval_data.name,
      kind: status === "active" ? "eval" : "planned",
      href: `/specs/${project_id}/${task_id}/legacy/${eval_data.id}`,
      pass_rate: scores.pass_rate,
      dataset_size: scores.dataset_size,
      principles: [],
      priority: eval_data.priority ?? null,
      status,
    }
    if (status === "active") active.push(node)
    else planned.push(node)
  }

  const nodes: CoverageNode[] = []
  const planned_for = new Map<number, string[]>()

  if (principles.length === 0) {
    const all = [...active, ...planned]
    const total = all.reduce((s, n) => s + priority_weight(n.priority), 0)
    for (const n of all) {
      nodes.push({
        ...n,
        weight: total > 0 ? priority_weight(n.priority) / total : 0,
      })
    }
    return {
      nodes,
      principles,
      covered: null,
      coverers: new Map(),
      planned_for,
      shares: new Map(),
      health: new Map(),
      floor: lowest(nodes),
      active_count: active.length,
      ...ledger,
    }
  }

  const model = buildCoverageModel(
    principles,
    active.map((n) => ({ id: n.id, principles: n.principles })),
    principleWeights(principles),
  )
  for (const n of active) {
    nodes.push({
      ...n,
      weight: model.evalWeights.get(n.id) ?? model.unmappedWeight,
    })
  }

  // Planned evals claim the holes they are tagged for; gaps take the rest.
  const open = new Set(model.uncovered.map((p) => p.n))
  for (const p of model.uncovered) planned_for.set(p.n, [])
  for (const n of planned) {
    for (const k of n.principles) {
      if (open.has(k)) planned_for.get(k)?.push(n.id)
    }
  }
  for (const n of planned) {
    let w = 0
    for (const k of new Set(n.principles)) {
      const claimers = planned_for.get(k)?.length ?? 0
      if (open.has(k) && claimers > 0)
        w += (model.shares.get(k) ?? 0) / claimers
    }
    nodes.push({ ...n, weight: w > 0 ? w : model.unmappedWeight })
  }
  for (const p of model.uncovered) {
    if ((planned_for.get(p.n)?.length ?? 0) > 0) continue
    nodes.push({
      id: `gap-${p.n}`,
      name: p.text,
      kind: "gap",
      href: builder_href(project_id, task_id, p),
      weight: model.shares.get(p.n) ?? 0,
      pass_rate: null,
      dataset_size: null,
      principles: [p.n],
      priority: null,
      status: null,
    })
  }

  // Health per principle: the mean pass rate of the active evals that cover it.
  const health = new Map<number, number | null>()
  const active_by_id = new Map(
    nodes.filter((n) => n.kind === "eval").map((n) => [n.id, n]),
  )
  for (const p of principles) {
    const rates = (model.coverers.get(p.n) ?? [])
      .map((id) => active_by_id.get(id)?.pass_rate)
      .filter((r): r is number => r !== null && r !== undefined)
    health.set(
      p.n,
      rates.length > 0 ? rates.reduce((s, r) => s + r, 0) / rates.length : null,
    )
  }

  return {
    nodes,
    principles,
    covered: model.covered,
    coverers: model.coverers,
    planned_for,
    shares: model.shares,
    health,
    floor: lowest(nodes),
    active_count: active.length,
    ...ledger,
  }
}
