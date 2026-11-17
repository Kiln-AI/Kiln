import { describe, expect, it } from "vitest"
import { CHART_PALETTE } from "$lib/utils/chart_palette"
import { CHANGE_KINDS, type ChangeKind } from "./lineage_graph"
import {
  CHANGE_KIND_COLORS,
  CHANGE_KIND_LABELS,
  FILTER_LABELS,
  GLYPH,
  glyph_rects,
  type GlyphRect,
} from "./lineage_glyph"

type Box = [x: number, y: number, w: number, h: number, overlay: boolean]

function boxes(rects: GlyphRect[]): Box[] {
  return rects.map((r) => [r.x, r.y, r.w, r.h, r.overlay])
}

function expect_boxes(actual: GlyphRect[], expected: Box[]): void {
  expect(actual).toHaveLength(expected.length)
  actual.forEach((rect, i) => {
    const [x, y, w, h, overlay] = expected[i]
    expect(rect.x).toBeCloseTo(x, 6)
    expect(rect.y).toBeCloseTo(y, 6)
    expect(rect.w).toBeCloseTo(w, 6)
    expect(rect.h).toBeCloseTo(h, 6)
    expect(rect.overlay).toBe(overlay)
  })
}

const first_kinds = (n: number): ChangeKind[] => CHANGE_KINDS.slice(0, n)

const EXPECTED_14_1: Box[][] = [
  [[0, 0, 14, 14, false]],
  [
    [0, 0, 6.5, 14, false],
    [7.5, 0, 6.5, 14, false],
  ],
  [
    [0, 0, 6.5, 14, false],
    [7.5, 0, 6.5, 6.5, false],
    [7.5, 7.5, 6.5, 6.5, false],
  ],
  [
    [0, 0, 6.5, 6.5, false],
    [7.5, 0, 6.5, 6.5, false],
    [0, 7.5, 6.5, 6.5, false],
    [7.5, 7.5, 6.5, 6.5, false],
  ],
  [
    [0, 0, 6.5, 6.5, false],
    [7.5, 0, 6.5, 6.5, false],
    [0, 7.5, 6.5, 6.5, false],
    [7.5, 7.5, 6.5, 6.5, false],
    [4.2, 4.2, 5.6, 5.6, true],
  ],
]

const EXPECTED_40_2: Box[][] = [
  [[0, 0, 40, 40, false]],
  [
    [0, 0, 19, 40, false],
    [21, 0, 19, 40, false],
  ],
  [
    [0, 0, 19, 40, false],
    [21, 0, 19, 19, false],
    [21, 21, 19, 19, false],
  ],
  [
    [0, 0, 19, 19, false],
    [21, 0, 19, 19, false],
    [0, 21, 19, 19, false],
    [21, 21, 19, 19, false],
  ],
  [
    [0, 0, 19, 19, false],
    [21, 0, 19, 19, false],
    [0, 21, 19, 19, false],
    [21, 21, 19, 19, false],
    [12, 12, 16, 16, true],
  ],
]

describe("glyph_rects", () => {
  it.each([1, 2, 3, 4, 5])("draws %i kinds at 14px with a 1px gap", (n) => {
    expect_boxes(glyph_rects(first_kinds(n), 14, 1), EXPECTED_14_1[n - 1])
  })

  it.each([1, 2, 3, 4, 5])("draws %i kinds at 40px with a 2px gap", (n) => {
    expect_boxes(glyph_rects(first_kinds(n), 40, 2), EXPECTED_40_2[n - 1])
  })

  it("assigns kinds to rectangles in the order given", () => {
    const rects = glyph_rects(["tools", "model", "settings"], 14, 1)
    expect(rects.map((r) => r.kind)).toEqual(["tools", "model", "settings"])
  })

  it("puts the fifth kind in the overlay", () => {
    const rects = glyph_rects(first_kinds(5), 14, 1)
    expect(rects.filter((r) => r.overlay).map((r) => r.kind)).toEqual([
      "settings",
    ])
  })

  it("keeps outer edges flush with the square", () => {
    for (let n = 1; n <= 4; n++) {
      const rects = glyph_rects(first_kinds(n), 14, 1)
      expect(Math.min(...rects.map((r) => r.x))).toBe(0)
      expect(Math.min(...rects.map((r) => r.y))).toBe(0)
      expect(Math.max(...rects.map((r) => r.x + r.w))).toBe(14)
      expect(Math.max(...rects.map((r) => r.y + r.h))).toBe(14)
    }
  })

  it("doesn't inset the overlay", () => {
    const overlay = glyph_rects(first_kinds(5), 20, 4).find((r) => r.overlay)
    expect(overlay && boxes([overlay])[0]).toEqual([6, 6, 8, 8, true])
  })

  it("returns no rectangles for 0 or 6 kinds", () => {
    expect(glyph_rects([], 14, 1)).toEqual([])
    expect(glyph_rects([...CHANGE_KINDS, "prompt"], 14, 1)).toEqual([])
  })

  it("defines the three glyph sizes", () => {
    expect(GLYPH).toEqual({
      graph: { size: 14, gap: 1, radius: 2 },
      panel: { size: 40, gap: 2, radius: 4 },
      swatch: { size: 12, gap: 1, radius: 2 },
    })
  })
})

describe("change kind colors and labels", () => {
  it("takes each kind's color from the chart palette", () => {
    expect(CHANGE_KIND_COLORS).toEqual({
      prompt: CHART_PALETTE[0],
      tools: CHART_PALETTE[7],
      skills: CHART_PALETTE[4],
      model: CHART_PALETTE[3],
      settings: CHART_PALETTE[5],
    })
  })

  it("labels each kind and filter", () => {
    expect(CHANGE_KINDS.map((k) => CHANGE_KIND_LABELS[k])).toEqual([
      "Prompt",
      "Tools",
      "Skills",
      "Model",
      "Settings",
    ])
    expect(FILTER_LABELS.copy).toBe("Copy or re-run")
    expect(FILTER_LABELS.model).toBe("Model")
  })
})
