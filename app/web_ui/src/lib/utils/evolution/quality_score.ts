// The one number a shipping decision is gated on.
//
// The price/latency chart holds quality fixed and then compares the two costs
// that are left. That needs quality as a scalar, and the scalar it used was the
// unweighted mean of every criterion on the task. A mean is COMPENSATORY: it
// lets a config buy back a failure on the criterion the customer cares most
// about with a pass on one nobody was worried about. Measured on a real task,
// the leading config cleared a 70% gate on a mean of 0.811 while its write
// correctness - the axis that engagement exists for - was 48%, a coin flip with
// a 95% interval of [0.28, 0.68]. A badge reading "quality ≥ 70%" over that is
// the failure this module exists to fix.
//
// So the number is the WEAKEST AREA: group the criteria into families, average
// within each, and take the minimum. "Quality 74%" then means "no concern area
// is below 74%", which is what a gate phrased as "good enough to ship" is
// actually claiming, and the tooltip can say WHICH area is the binding one -
// one hover instead of a table.
//
// ---------------------------------------------------------------------------
// Where the families come from: the task's own specs, via score_families. Not
// from a taxonomy invented here, and not from per-eval weights in the UI. A
// weight nobody wrote down in the data would be a second invisible aggregate,
// tunable until the preferred config wins. A task that declares no grouping
// falls back to the flat mean, which is exactly the old behavior.
//
// Why families and not per-axis floors: a floor per axis is the same idea at
// finer grain, and at the sample sizes evals run at it is a coin flip. On that
// task the leading config missed a 0.5 write-correctness floor by 0.024 on a
// cell whose interval is ±0.20 wide. Families pool their axes (n = 46-69
// against 10-25), which roughly halves the interval, and they cost no plumbing:
// the gate stays a scalar, so the floor menu, the URL parameter and the
// quantile cuts all compose unchanged.
//
// Why min and not the mean of the family means: the mean of families is still
// compensatory, just at a coarser grain - it re-admits the same "74% overall
// with a 48% coin flip inside" reading it was meant to remove.
//
// ---------------------------------------------------------------------------
// Uncertainty is shown, never folded in. The point estimate stays the mean;
// intervals go in the tooltip, and a config sitting within its weakest family's
// interval of the floor is ANNOTATED as borderline rather than being moved
// across the gate. Folding a Wilson lower bound into the value de-calibrates
// every floor (on the same task nothing at all cleared 70%) and punishes a thin
// cell twice - once for being uncertain, once for the uncertainty pulling the
// estimate down.

import {
  family_for_eval,
  order_families,
  type ScoreFamily,
} from "./score_families"
import { score_interval, wilson_interval } from "./score_intervals"
import {
  metric_eval_ids,
  normalized_score,
  raw_score,
  sample_size,
  type LensData,
  type ScoreKeyMeta,
} from "./score_lens"

/** One criterion inside a family, as the tooltip prints it. */
export interface QualityAxis {
  evalId: string
  evalName: string
  scoreKey: string
  /** Direction-corrected 0..1 - what the family mean is over */
  value: number
  /** The score in its own units, for display; equal to value for a pass rate */
  raw: number | null
  /** Runs behind it, when the payload carries counts */
  n: number | null
  /** 95% interval, for the score types that have an honest one */
  interval: { lower: number; upper: number } | null
}

export interface QualityFamily {
  id: string
  label: string
  /** Mean of the scored member axes, direction-corrected 0..1 */
  value: number
  /** Axes with a value for this config */
  axes: QualityAxis[]
  /** Member keys this config has no score for */
  unscored: number
  /** Sum of the member axes' run counts; null when no axis reports one */
  pooled_n: number | null
}

export interface QualityBreakdown {
  /** The gated number: the weakest family's mean, or the flat mean */
  quality: number
  /** The family that bound it; null in the ungrouped fallback */
  weakest: QualityFamily | null
  /** Every family with a value, in the ring's own order */
  families: QualityFamily[]
  /**
   * "families" when the task declared a grouping and it was used, "flat" when
   * it declared none and this is the plain mean over every criterion.
   */
  mode: "families" | "flat"
}

/**
 * The keys quality is made of: criteria that declare a better direction.
 *
 * Informational keys are out because they have no better end - that is what
 * authoring one informational means. Metric evals are out because a `custom`
 * key has no scale of its own and is min-max scaled across the configs in the
 * summary, so including one turns "cheapest of the thirteen run here" into
 * something that looks like a pass rate. Same partition the radars use.
 */
export function quality_key_metas(keyMetas: ScoreKeyMeta[]): ScoreKeyMeta[] {
  const metric_evals = metric_eval_ids(keyMetas)
  return keyMetas.filter(
    (meta) =>
      meta.direction !== "informational" && !metric_evals.has(meta.evalId),
  )
}

/**
 * Each declared family's mean for one run config, with the axes behind it.
 *
 * DECLARED, not scored: a family with member keys this config has no value for
 * is still returned, with `unscored` counting them, because "this config was
 * never measured on the data-integrity criteria" is the fact the strict-null
 * rule below turns into a ghost rather than into a flattering mean over what
 * happens to be there.
 *
 * A family with NO scored axis at all has no mean and is omitted here; the
 * caller compares the count it got back against the count of declared families
 * to notice.
 */
export function family_quality_breakdown(
  data: LensData,
  families: Map<string, ScoreFamily>,
  runConfigId: string,
): QualityFamily[] {
  const metas = quality_key_metas(data.keyMetas)
  const by_family = new Map<
    string,
    { family: ScoreFamily; metas: ScoreKeyMeta[] }
  >()
  for (const meta of metas) {
    const family = family_for_eval(families, meta.evalId)
    const group = by_family.get(family.id) ?? { family, metas: [] }
    group.metas.push(meta)
    by_family.set(family.id, group)
  }

  const ordered = order_families([...by_family.values()].map((g) => g.family))
  const result: QualityFamily[] = []
  for (const family of ordered) {
    const group = by_family.get(family.id)
    if (!group) continue
    const axes: QualityAxis[] = []
    let unscored = 0
    for (const meta of group.metas) {
      const value = normalized_score(
        data,
        runConfigId,
        meta.evalId,
        meta.scoreKey,
      )
      if (value === null || !Number.isFinite(value)) {
        unscored++
        continue
      }
      const raw = raw_score(data, runConfigId, meta.evalId, meta.scoreKey)
      const n = sample_size(data, runConfigId, meta.evalId, meta.scoreKey)
      const interval = score_interval(raw, n, meta.type)
      axes.push({
        evalId: meta.evalId,
        evalName: meta.evalName,
        scoreKey: meta.scoreKey,
        value,
        raw,
        n,
        interval: interval
          ? { lower: interval.lower, upper: interval.upper }
          : null,
      })
    }
    if (axes.length === 0) continue
    const counted = axes.filter((axis) => axis.n !== null)
    result.push({
      id: family.id,
      label: family.label,
      value: axes.reduce((total, axis) => total + axis.value, 0) / axes.length,
      axes,
      unscored,
      pooled_n:
        counted.length > 0
          ? counted.reduce((total, axis) => total + (axis.n ?? 0), 0)
          : null,
    })
  }
  return result
}

/** How many families the task's grouping declares over these quality keys */
function declared_family_count(
  keyMetas: ScoreKeyMeta[],
  families: Map<string, ScoreFamily>,
): number {
  const ids = new Set<string>()
  for (const meta of quality_key_metas(keyMetas)) {
    ids.add(family_for_eval(families, meta.evalId).id)
  }
  return ids.size
}

/**
 * The gated quality for one run config, and what it is made of.
 *
 * Null in two cases, and they are different facts that happen to render the
 * same way (a ghosted point with its own wording):
 *  - the config has no criterion scores at all - it was never measured;
 *  - the task declares families and this config has no score in one of them.
 *    STRICT, deliberately: a best-effort mean over the families that happen to
 *    be present would let a config that skipped the hardest area outrank one
 *    that ran everything, and the "skipped" is invisible in the number. It
 *    happened on the task this was designed against, where one config had zero
 *    runs on a write-safety judge every other config had 15-25 of.
 *
 * The ungrouped fallback (`mode: "flat"`) is the plain mean over every quality
 * key, which is exactly what the aggregate lens gives - so a task that never
 * adopted family tags sees no change at all.
 */
export function weakest_family_quality(
  data: LensData,
  families: Map<string, ScoreFamily>,
  runConfigId: string,
): QualityBreakdown | null {
  const metas = quality_key_metas(data.keyMetas)
  if (metas.length === 0) return null

  // One family divides nothing, and the OTHER bucket alone means the task's
  // scheme never reached these evals. Either way there is no grouping to read,
  // so the honest number is the flat mean.
  const declared = declared_family_count(data.keyMetas, families)
  const grouped = families.size > 0 && declared > 1

  const breakdown = family_quality_breakdown(data, families, runConfigId)
  if (breakdown.length === 0) return null

  if (!grouped) {
    const axes = breakdown.flatMap((family) => family.axes)
    if (axes.length === 0) return null
    return {
      quality:
        axes.reduce((total, axis) => total + axis.value, 0) / axes.length,
      weakest: null,
      families: breakdown,
      mode: "flat",
    }
  }

  if (breakdown.length < declared) return null

  const weakest = breakdown.reduce((a, b) => (a.value <= b.value ? a : b))
  return {
    quality: weakest.value,
    weakest,
    families: breakdown,
    mode: "families",
  }
}

/**
 * Whether a config sits close enough to the floor that this sample cannot say
 * which side of it the config really is on.
 *
 * The test is the binding family's own 95% interval, computed on its pooled n:
 * inside it, the verdict is arithmetic rather than evidence. Nothing moves -
 * the gate stays exactly where the arithmetic put it, because a deterministic
 * gate is worth more than a softened one and a reader who is told "borderline"
 * can decide what to do about it.
 *
 * Wilson on a mean of pass rates is an approximation (it is a proportion of
 * proportions), which is fine for an annotation and would not be for a value.
 */
export function is_borderline(
  breakdown: QualityBreakdown | null,
  floor: number | null,
): boolean {
  if (!breakdown || floor === null || !Number.isFinite(floor)) return false
  const family = breakdown.weakest
  if (!family || family.pooled_n === null) return false
  const interval = wilson_interval(
    Math.min(1, Math.max(0, family.value)),
    family.pooled_n,
  )
  if (!interval) return false
  return floor >= interval.lower && floor <= interval.upper
}

function percent(value: number): string {
  return `${Math.round(value * 100)}%`
}

/** `write_correctness 48% [28–68%] (n=21)` */
export function axis_phrase(axis: QualityAxis): string {
  const parts = [`${axis.scoreKey} ${percent(axis.value)}`]
  if (axis.interval) {
    // One % on the range, not two: "[28–68%]" reads as one span where
    // "[28%–68%]" reads as two numbers that happen to be adjacent.
    parts.push(
      `[${Math.round(axis.interval.lower * 100)}–${percent(axis.interval.upper)}]`,
    )
  }
  if (axis.n !== null) {
    parts.push(`(n=${axis.n})`)
  }
  return parts.join(" ")
}

/**
 * The tooltip, as lines: what the number is, which area bound it, every area's
 * value, and the binding area's axes with their intervals.
 *
 * Four lines rather than a table because the question a hover answers is "why
 * is this config where it is", and the answer is one area's name plus the
 * evidence under it.
 */
export function quality_tooltip_lines(
  breakdown: QualityBreakdown | null,
  floor: number | null = null,
): string[] {
  if (!breakdown) return []
  if (breakdown.mode === "flat") {
    const lines = [
      `Quality ${percent(breakdown.quality)} — mean of every criterion`,
    ]
    const axes = breakdown.families.flatMap((family) => family.axes)
    if (axes.length > 0) {
      lines.push(axes.map(axis_phrase).join(" · "))
    }
    return lines
  }

  const weakest = breakdown.weakest as QualityFamily
  const lines = [
    `Quality ${percent(breakdown.quality)} — weakest area: ${weakest.label}`,
    breakdown.families
      .map((family) => `${family.label} ${percent(family.value)}`)
      .join(" · "),
    `${weakest.label}: ${weakest.axes.map(axis_phrase).join(" · ")}`,
  ]
  if (is_borderline(breakdown, floor)) {
    lines.push("Borderline at this sample size")
  }
  return lines
}

/** Why a config is ghosted, naming the area that failed and its axes. */
export function below_gate_reason(
  breakdown: QualityBreakdown | null,
  floor: number | null,
): string | null {
  if (!breakdown || floor === null || breakdown.mode === "flat") return null
  const weakest = breakdown.weakest
  if (!weakest || weakest.value >= floor) return null
  return (
    `Below the gate: ${weakest.label} ${percent(weakest.value)} < ` +
    `${percent(floor)} (${weakest.axes
      .map((axis) => `${axis.scoreKey} ${percent(axis.value)}`)
      .join(" · ")})`
  )
}
