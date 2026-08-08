import type { components } from "$lib/api_schema"
import type { Eval } from "$lib/types"
import { score_key_label, score_type_range } from "$lib/utils/formatters"
import { string_to_json_key } from "$lib/utils/json_schema_editor/json_schema_templates"

type EvalResultsSummaryResponse =
  components["schemas"]["EvalResultsSummaryResponse"]
type ScoreType = components["schemas"]["TaskOutputRatingType"]
type ScoreDirection = components["schemas"]["ScoreDirection"]

export type Lens =
  | { kind: "aggregate" }
  | { kind: "single"; evalId: string; scoreKey: string }

export type StripCellSign = -1 | 0 | 1 | null

// How a strip cell is painted:
// - "delta":    the node and its parent both have a score, so the cell carries
//               the better/worse/neutral color of the delta.
// - "absolute": the node has a score but there is no parent baseline to compare
//               against, so the cell shows the node's own lens bin color,
//               muted. A completed eval always leaves a tick this way.
// - "empty":    no score for this key at all.
export type StripCellMode = "delta" | "absolute" | "empty"

export interface StripCell {
  evalId: string
  scoreKey: string
  /** Sign of the delta vs the parent baseline; null unless mode is "delta" */
  sign: StripCellSign
  mode: StripCellMode
  /** Resolved fill color for the cell */
  color: string
  /** Hover text for the cell */
  title: string
}

export interface ScoreKeyMeta {
  evalId: string
  evalName: string
  scoreKey: string
  type: ScoreType | null
  direction: ScoreDirection
}

export interface LensData {
  keyMetas: ScoreKeyMeta[]
  /** Raw mean score per run config id, keyed `${evalId}::${scoreKey}` */
  raw: Map<string, Map<string, number>>
  /** Direction-corrected normalized (0..1) score, same keying as `raw` */
  normalized: Map<string, Map<string, number>>
  /**
   * Runs behind each mean, same keying as `raw`. What separates a score from an
   * estimate of one: without it nothing downstream can put an interval on a
   * mean. Absent for older payloads that predate the field.
   */
  counts: Map<string, Map<string, number>>
  /** percent_complete per run config id, keyed by eval id */
  percentComplete: Map<string, Map<string, number>>
}

// What the node card renders under the current lens; computed once per node
// by the page and shared by the canvas and the unlinked grid.
export interface NodeDisplay {
  lens_color: string
  lens_value: string | null
  strip: StripCell[]
  subtitle: string
  best: boolean
  dimmed: boolean
}

export const NO_SCORE_COLOR = "#d1d5db"
export const SCORE_BIN_COLORS = [
  "#9dabfa",
  "#7d8ff8",
  "#5a72f6",
  "#3a50d9",
  "#2438b8",
]

export const STRIP_EPSILON = 0.02
export const STRIP_BETTER_COLOR = "#3a50d9"
export const STRIP_WORSE_COLOR = "#d03b3b"
export const STRIP_NEUTRAL_COLOR = "#e5e7eb"
// Cells with no score at all: present (so the strip stays aligned) but almost
// invisible, so they never read as a result.
export const STRIP_EMPTY_COLOR = "#f3f4f6"

export function score_key_id(evalId: string, scoreKey: string): string {
  return `${evalId}::${scoreKey}`
}

export function lens_key(lens: Lens): string {
  return lens.kind === "aggregate"
    ? "aggregate"
    : score_key_id(lens.evalId, lens.scoreKey)
}

export function parse_lens_key(key: string | null): Lens {
  if (!key || key === "aggregate") {
    return { kind: "aggregate" }
  }
  const separator = key.indexOf("::")
  if (separator <= 0 || separator + 2 >= key.length) {
    return { kind: "aggregate" }
  }
  return {
    kind: "single",
    evalId: key.slice(0, separator),
    scoreKey: key.slice(separator + 2),
  }
}

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value))
}

export function build_lens_data(
  summary: EvalResultsSummaryResponse | null,
  evals: Eval[] | null,
): LensData {
  const keyMetas: ScoreKeyMeta[] = []
  const raw = new Map<string, Map<string, number>>()
  const normalized = new Map<string, Map<string, number>>()
  const counts = new Map<string, Map<string, number>>()
  const percentComplete = new Map<string, Map<string, number>>()
  if (!summary) {
    return { keyMetas, raw, normalized, counts, percentComplete }
  }

  // Score key metadata: eval_results_summary reports JSON score keys; match
  // them back to the eval's output_scores via the same name -> JSON key
  // mapping the server uses.
  const evals_by_id = new Map<string, Eval>()
  for (const evaluator of evals ?? []) {
    if (evaluator.id) {
      evals_by_id.set(evaluator.id, evaluator)
    }
  }
  for (const [eval_id, eval_info] of Object.entries(summary.evals_by_id)) {
    const evaluator = evals_by_id.get(eval_id)
    for (const score_key of eval_info.output_score_keys) {
      const output_score = evaluator?.output_scores.find(
        (score) => string_to_json_key(score.name) === score_key,
      )
      keyMetas.push({
        evalId: eval_id,
        evalName: eval_info.name,
        scoreKey: score_key,
        type: output_score?.type ?? null,
        direction: output_score?.direction ?? "higher_is_better",
      })
    }
  }

  // Raw mean scores and per-eval completion
  for (const [run_config_id, cells] of Object.entries(
    summary.scores_by_run_config_by_eval,
  )) {
    const raw_scores = new Map<string, number>()
    const sample_sizes = new Map<string, number>()
    const completion = new Map<string, number>()
    for (const [eval_id, cell] of Object.entries(cells)) {
      completion.set(eval_id, cell.percent_complete)
      for (const [score_key, value] of Object.entries(cell.mean_scores)) {
        if (typeof value === "number" && Number.isFinite(value)) {
          raw_scores.set(score_key_id(eval_id, score_key), value)
        }
      }
      for (const [score_key, n] of Object.entries(
        cell.n_used_by_score_key ?? {},
      )) {
        if (typeof n === "number" && Number.isFinite(n) && n > 0) {
          sample_sizes.set(score_key_id(eval_id, score_key), n)
        }
      }
    }
    raw.set(run_config_id, raw_scores)
    normalized.set(run_config_id, new Map())
    counts.set(run_config_id, sample_sizes)
    percentComplete.set(run_config_id, completion)
  }

  // Normalize per key (direction-corrected 0..1). Custom/unknown types are
  // min-max scaled across the run configs that have the key.
  for (const meta of keyMetas) {
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
    for (const [run_config_id, raw_scores] of raw) {
      const value = raw_scores.get(key)
      if (value === undefined) {
        continue
      }
      // Known score types scale against their own full range; custom or
      // unknown ones are min-max scaled across the run configs that have the
      // key (all equal -> 0.5).
      const range = score_type_range(meta.type)
      let scaled = range
        ? clamp01((value - range.min) / (range.max - range.min))
        : max > min
          ? (value - min) / (max - min)
          : 0.5
      if (meta.direction === "lower_is_better") {
        scaled = 1 - scaled
      }
      normalized.get(run_config_id)?.set(key, scaled)
    }
  }

  return { keyMetas, raw, normalized, counts, percentComplete }
}

/** Runs behind one config's mean for one score key; null when unknown. */
export function sample_size(
  lens_data: LensData,
  runConfigId: string,
  evalId: string,
  scoreKey: string,
): number | null {
  return (
    lens_data.counts.get(runConfigId)?.get(score_key_id(evalId, scoreKey)) ??
    null
  )
}

export function raw_score(
  data: LensData,
  runConfigId: string,
  evalId: string,
  scoreKey: string,
): number | null {
  return data.raw.get(runConfigId)?.get(score_key_id(evalId, scoreKey)) ?? null
}

export function normalized_score(
  data: LensData,
  runConfigId: string,
  evalId: string,
  scoreKey: string,
): number | null {
  return (
    data.normalized.get(runConfigId)?.get(score_key_id(evalId, scoreKey)) ??
    null
  )
}

export function percent_complete(
  data: LensData,
  runConfigId: string,
  evalId: string,
): number | null {
  return data.percentComplete.get(runConfigId)?.get(evalId) ?? null
}

// Normalized value under a lens. Aggregate = unweighted mean of the run
// config's normalized, non-informational score keys.
export function normalized_lens_value(
  data: LensData,
  runConfigId: string,
  lens: Lens,
): number | null {
  if (lens.kind === "single") {
    return normalized_score(data, runConfigId, lens.evalId, lens.scoreKey)
  }
  let total = 0
  let count = 0
  for (const meta of data.keyMetas) {
    if (meta.direction === "informational") {
      continue
    }
    const value = normalized_score(
      data,
      runConfigId,
      meta.evalId,
      meta.scoreKey,
    )
    if (value !== null) {
      total += value
      count++
    }
  }
  return count > 0 ? total / count : null
}

// Raw display value under a lens. For the aggregate lens there is no raw
// scale, so the normalized mean is the displayed value.
export function raw_lens_value(
  data: LensData,
  runConfigId: string,
  lens: Lens,
): number | null {
  if (lens.kind === "single") {
    return raw_score(data, runConfigId, lens.evalId, lens.scoreKey)
  }
  return normalized_lens_value(data, runConfigId, lens)
}

// Bins on normalized [0,1]; darkest = best. No score -> gray.
export function lens_color(normalized_value: number | null): string {
  if (normalized_value === null || Number.isNaN(normalized_value)) {
    return NO_SCORE_COLOR
  }
  if (normalized_value < 0.4) {
    return SCORE_BIN_COLORS[0]
  }
  if (normalized_value < 0.6) {
    return SCORE_BIN_COLORS[1]
  }
  if (normalized_value < 0.75) {
    return SCORE_BIN_COLORS[2]
  }
  if (normalized_value < 0.9) {
    return SCORE_BIN_COLORS[3]
  }
  return SCORE_BIN_COLORS[4]
}

// Delta in normalized units vs the (primary) parent under a lens.
export function delta_vs_parent(
  data: LensData,
  runConfigId: string,
  parentId: string | null,
  lens: Lens,
): number | null {
  if (!parentId) {
    return null
  }
  const child = normalized_lens_value(data, runConfigId, lens)
  const parent = normalized_lens_value(data, parentId, lens)
  if (child === null || parent === null) {
    return null
  }
  return child - parent
}

function format_delta(delta: number): string {
  if (Math.abs(delta) <= STRIP_EPSILON) {
    return "±0.00"
  }
  return `${delta > 0 ? "+" : "−"}${Math.abs(delta).toFixed(2)}`
}

// One strip cell per (eval, scoreKey), always the same set in the same order so
// every card's strip lines up.
//
// A cell is a delta vs the primary parent when both sides have a score: sign of
// the direction-corrected normalized delta, with a +/-0.02 dead zone. When the
// node is scored but there is no baseline to compare against (no parent, a
// parent with no results for that key, or an informational key, which carries
// no better/worse direction) the cell falls back to the node's own absolute
// lens color so a finished eval still shows a tick. Unscored keys stay blank.
export function strip_cells(
  data: LensData,
  runConfigId: string,
  parentId: string | null,
): StripCell[] {
  return data.keyMetas.map((meta) => {
    const label = `${meta.evalName} · ${score_key_label(meta.scoreKey)}`
    const child = normalized_score(
      data,
      runConfigId,
      meta.evalId,
      meta.scoreKey,
    )
    if (child === null) {
      return {
        evalId: meta.evalId,
        scoreKey: meta.scoreKey,
        sign: null,
        mode: "empty" as const,
        color: STRIP_EMPTY_COLOR,
        title: `${label}: not scored`,
      }
    }

    const raw = raw_score(data, runConfigId, meta.evalId, meta.scoreKey)
    const value_text = (raw ?? child).toFixed(2)
    const parent =
      parentId && meta.direction !== "informational"
        ? normalized_score(data, parentId, meta.evalId, meta.scoreKey)
        : null

    if (parent !== null) {
      const delta = child - parent
      const sign: StripCellSign =
        delta > STRIP_EPSILON ? 1 : delta < -STRIP_EPSILON ? -1 : 0
      return {
        evalId: meta.evalId,
        scoreKey: meta.scoreKey,
        sign,
        mode: "delta" as const,
        color: strip_cell_color(sign),
        title: `${label}: ${value_text} · ${format_delta(delta)} vs parent`,
      }
    }

    return {
      evalId: meta.evalId,
      scoreKey: meta.scoreKey,
      sign: null,
      mode: "absolute" as const,
      color: lens_color(child),
      title: `${label}: ${value_text}${
        meta.direction === "informational"
          ? " · informational"
          : " · no parent baseline"
      }`,
    }
  })
}

export function strip_cell_color(sign: StripCellSign): string {
  if (sign === 1) {
    return STRIP_BETTER_COLOR
  }
  if (sign === -1) {
    return STRIP_WORSE_COLOR
  }
  return STRIP_NEUTRAL_COLOR
}
