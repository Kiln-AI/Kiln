import { CHART_PALETTE } from "$lib/utils/chart_palette"
import type { ChangeKind, FilterKey } from "./lineage_graph"

export const CHANGE_KIND_COLORS: Record<ChangeKind, string> = {
  prompt: CHART_PALETTE[0],
  tools: CHART_PALETTE[7],
  skills: CHART_PALETTE[4],
  model: CHART_PALETTE[3],
  settings: CHART_PALETTE[5],
}

export const CHANGE_KIND_LABELS: Record<ChangeKind, string> = {
  prompt: "Prompt",
  tools: "Tools",
  skills: "Skills",
  model: "Model",
  settings: "Settings",
}

export const FILTER_LABELS: Record<FilterKey, string> = {
  ...CHANGE_KIND_LABELS,
  copy: "Copy or re-run",
}

export interface GlyphRect {
  x: number
  y: number
  w: number
  h: number
  kind: ChangeKind
  overlay: boolean
}

/** A glyph's square size, the gap between its segments, and its corner radius, in px. */
export interface GlyphSize {
  size: number
  gap: number
  radius: number
}

export const GLYPH = {
  graph: { size: 14, gap: 1, radius: 2 },
  panel: { size: 40, gap: 2, radius: 4 },
  swatch: { size: 12, gap: 1, radius: 2 },
} as const satisfies Record<string, GlyphSize>

interface UnitRect {
  x: number
  y: number
  w: number
  h: number
  overlay: boolean
}

function unit(x: number, y: number, w: number, h: number): UnitRect {
  return { x, y, w, h, overlay: false }
}

const QUADRANTS = [
  unit(0, 0, 0.5, 0.5),
  unit(0.5, 0, 0.5, 0.5),
  unit(0, 0.5, 0.5, 0.5),
  unit(0.5, 0.5, 0.5, 0.5),
]

// Indexed by the number of kinds minus one.
const UNIT_SHAPES: readonly (readonly UnitRect[])[] = [
  [unit(0, 0, 1, 1)],
  [unit(0, 0, 0.5, 1), unit(0.5, 0, 0.5, 1)],
  [unit(0, 0, 0.5, 1), unit(0.5, 0, 0.5, 0.5), unit(0.5, 0.5, 0.5, 0.5)],
  QUADRANTS,
  [...QUADRANTS, { x: 0.3, y: 0.3, w: 0.4, h: 0.4, overlay: true }],
]

/**
 * The rectangles that draw a node changed in `kinds`, in a `size` square.
 * Segments are split by `gap`: only internal edges are inset, so the outer
 * edges stay flush. The fifth kind is a centered overlay, drawn on top.
 * Kinds take the rectangles in the order given. Returns [] for 0 or more
 * than 5 kinds.
 */
export function glyph_rects(
  kinds: ChangeKind[],
  size: number,
  gap: number,
): GlyphRect[] {
  const shape = UNIT_SHAPES[kinds.length - 1]
  if (!shape) {
    return []
  }
  const inset = gap / 2
  return shape.map((rect, index) => {
    let x1 = rect.x * size
    let x2 = (rect.x + rect.w) * size
    let y1 = rect.y * size
    let y2 = (rect.y + rect.h) * size
    if (!rect.overlay) {
      if (rect.x > 0) x1 += inset
      if (rect.x + rect.w < 1) x2 -= inset
      if (rect.y > 0) y1 += inset
      if (rect.y + rect.h < 1) y2 -= inset
    }
    return {
      x: x1,
      y: y1,
      w: x2 - x1,
      h: y2 - y1,
      kind: kinds[index],
      overlay: rect.overlay,
    }
  })
}
