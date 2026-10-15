/**
 * How much of a constitution the evals cover, and how much each eval holds.
 *
 * Every principle has an importance share; the shares sum to 1. A principle
 * is covered when at least one eval maps to it. The share of a covered
 * principle is split evenly between the evals that cover it, so the eval
 * weights sum to the covered share and no principle counts twice.
 */

import type { Principle } from "./constitution"

export type CoverageEval = {
  id: string
  /** Principle numbers this eval maps to. */
  principles: number[]
}

export type CoverageModel = {
  /** Share of the constitution held by each eval. Sums to `covered`. */
  evalWeights: Map<string, number>
  /** Eval ids that cover each principle number. */
  coverers: Map<number, string[]>
  /** Importance share of each principle number. Sums to 1. */
  shares: Map<number, number>
  uncovered: Principle[]
  /** Importance-weighted share of principles with at least one eval, 0..1. */
  covered: number
  /** Weight given to an eval that maps to no principle. */
  unmappedWeight: number
}

const TAG_PREFIX = /^principle_(\d+)$/

/** Principle numbers named by tags of the form `principle_<n>`. */
export function principlesFromTags(
  tags: string[] | null | undefined,
): number[] {
  const out = new Set<number>()
  for (const tag of tags ?? []) {
    const m = tag.match(TAG_PREFIX)
    if (m) out.add(Number(m[1]))
  }
  return [...out].sort((a, b) => a - b)
}

export function buildCoverageModel(
  principles: Principle[],
  evals: CoverageEval[],
  importance: Map<number, number> = new Map(),
): CoverageModel {
  const raw = new Map<number, number>()
  for (const p of principles) {
    const v = importance.get(p.n)
    raw.set(p.n, v !== undefined && v > 0 ? v : 1)
  }
  const total = [...raw.values()].reduce((s, v) => s + v, 0)
  const shares = new Map<number, number>()
  for (const [n, v] of raw) shares.set(n, total > 0 ? v / total : 0)

  const coverers = new Map<number, string[]>()
  for (const p of principles) coverers.set(p.n, [])
  for (const e of evals) {
    for (const n of new Set(e.principles)) {
      coverers.get(n)?.push(e.id)
    }
  }

  const smallest =
    shares.size > 0
      ? Math.min(...shares.values())
      : 1 / Math.max(evals.length, 1)
  const unmappedWeight = shares.size > 0 ? smallest / 2 : smallest

  const evalWeights = new Map<string, number>()
  for (const e of evals) {
    let w = 0
    for (const n of new Set(e.principles)) {
      const share = shares.get(n)
      const k = coverers.get(n)?.length ?? 0
      if (share !== undefined && k > 0) w += share / k
    }
    evalWeights.set(e.id, w > 0 ? w : unmappedWeight)
  }

  const uncovered = principles.filter(
    (p) => (coverers.get(p.n)?.length ?? 0) === 0,
  )
  const covered = principles
    .filter((p) => (coverers.get(p.n)?.length ?? 0) > 0)
    .reduce((s, p) => s + (shares.get(p.n) ?? 0), 0)

  return { evalWeights, coverers, shares, uncovered, covered, unmappedWeight }
}
