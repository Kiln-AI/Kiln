import { describe, it, expect } from "vitest"
import type { components } from "$lib/api_schema"
import type { Eval } from "$lib/types"
import {
  NO_SCORE_COLOR,
  SCORE_BIN_COLORS,
  STRIP_BETTER_COLOR,
  STRIP_EMPTY_COLOR,
  STRIP_NEUTRAL_COLOR,
  STRIP_WORSE_COLOR,
  build_lens_data,
  delta_vs_parent,
  lens_color,
  lens_key,
  normalized_lens_value,
  normalized_score,
  parse_lens_key,
  percent_complete,
  raw_lens_value,
  raw_score,
  score_key_id,
  strip_cell_color,
  strip_cells,
} from "./score_lens"

type EvalResultsSummaryResponse =
  components["schemas"]["EvalResultsSummaryResponse"]
type ScoreType = components["schemas"]["TaskOutputRatingType"]
type ScoreDirection = components["schemas"]["ScoreDirection"]

type ScoreSpec = {
  name: string
  type: ScoreType
  direction?: ScoreDirection
}

// One eval with the given scores, plus per-run-config mean values keyed by
// the eval's JSON score keys.
function make_summary(
  evals: { id: string; name: string; scores: ScoreSpec[] }[],
  scores_by_run_config: Record<
    string,
    Record<string, { means: Record<string, number>; percent?: number }>
  >,
): { summary: EvalResultsSummaryResponse; evals: Eval[] } {
  const evals_by_id: Record<string, unknown> = {}
  const eval_models: Eval[] = []
  for (const spec of evals) {
    evals_by_id[spec.id] = {
      name: spec.name,
      output_score_keys: spec.scores.map((score) =>
        score.name.toLowerCase().replace(/ /g, "_"),
      ),
      default_judge_config_id: null,
      dataset_size: 10,
    }
    eval_models.push({
      id: spec.id,
      name: spec.name,
      output_scores: spec.scores.map((score) => ({
        name: score.name,
        type: score.type,
        direction: score.direction ?? "higher_is_better",
        instruction: null,
      })),
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any)
  }

  const cells: Record<string, Record<string, unknown>> = {}
  for (const [run_config_id, by_eval] of Object.entries(scores_by_run_config)) {
    cells[run_config_id] = {}
    for (const [eval_id, cell] of Object.entries(by_eval)) {
      cells[run_config_id][eval_id] = {
        mean_scores: cell.means,
        percent_complete: cell.percent ?? 1,
      }
    }
  }

  return {
    summary: {
      evals_by_id,
      run_configs_by_id: {},
      scores_by_run_config_by_eval: cells,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any,
    evals: eval_models,
  }
}

describe("lens keys", () => {
  it("round-trips a single-score lens and defaults to aggregate", () => {
    expect(score_key_id("e1", "pass_fail")).toBe("e1::pass_fail")
    expect(lens_key({ kind: "aggregate" })).toBe("aggregate")
    expect(lens_key({ kind: "single", evalId: "e1", scoreKey: "acc" })).toBe(
      "e1::acc",
    )
    expect(parse_lens_key("e1::acc")).toEqual({
      kind: "single",
      evalId: "e1",
      scoreKey: "acc",
    })
    for (const bad of [null, "", "aggregate", "::acc", "e1::", "nosep"]) {
      expect(parse_lens_key(bad)).toEqual({ kind: "aggregate" })
    }
  })
})

describe("build_lens_data normalization", () => {
  it("scales each known score type against its own full range", () => {
    const { summary, evals } = make_summary(
      [
        {
          id: "e1",
          name: "Eval One",
          scores: [
            { name: "five", type: "five_star" },
            { name: "pass", type: "pass_fail" },
            { name: "critical", type: "pass_fail_critical" },
          ],
        },
      ],
      {
        rc1: { e1: { means: { five: 3, pass: 0.75, critical: 0 } } },
      },
    )
    const data = build_lens_data(summary, evals)

    // five_star spans 1..5, so the midpoint 3 normalizes to 0.5
    expect(normalized_score(data, "rc1", "e1", "five")).toBeCloseTo(0.5, 6)
    // pass_fail spans 0..1, so the raw value passes through
    expect(normalized_score(data, "rc1", "e1", "pass")).toBeCloseTo(0.75, 6)
    // pass_fail_critical spans -1..1, so 0 is the midpoint
    expect(normalized_score(data, "rc1", "e1", "critical")).toBeCloseTo(0.5, 6)
    // Raw values are preserved untouched alongside the normalized ones
    expect(raw_score(data, "rc1", "e1", "five")).toBe(3)
  })

  it("clamps out-of-range values into 0..1", () => {
    const { summary, evals } = make_summary(
      [
        {
          id: "e1",
          name: "Eval One",
          scores: [
            { name: "low", type: "five_star" },
            { name: "high", type: "pass_fail" },
          ],
        },
      ],
      { rc1: { e1: { means: { low: -4, high: 12 } } } },
    )
    const data = build_lens_data(summary, evals)
    expect(normalized_score(data, "rc1", "e1", "low")).toBe(0)
    expect(normalized_score(data, "rc1", "e1", "high")).toBe(1)
  })

  it("min-max scales custom scores across the run configs that have them", () => {
    const { summary, evals } = make_summary(
      [
        {
          id: "e1",
          name: "Eval One",
          scores: [{ name: "cost", type: "custom" }],
        },
      ],
      {
        rc1: { e1: { means: { cost: 100 } } },
        rc2: { e1: { means: { cost: 200 } } },
        rc3: { e1: { means: { cost: 150 } } },
      },
    )
    const data = build_lens_data(summary, evals)
    expect(normalized_score(data, "rc1", "e1", "cost")).toBe(0)
    expect(normalized_score(data, "rc2", "e1", "cost")).toBe(1)
    expect(normalized_score(data, "rc3", "e1", "cost")).toBeCloseTo(0.5, 6)
  })

  it("puts every run config at 0.5 when a custom score has no spread", () => {
    const { summary, evals } = make_summary(
      [
        {
          id: "e1",
          name: "Eval One",
          scores: [{ name: "cost", type: "custom" }],
        },
      ],
      {
        rc1: { e1: { means: { cost: 42 } } },
        rc2: { e1: { means: { cost: 42 } } },
      },
    )
    const data = build_lens_data(summary, evals)
    expect(normalized_score(data, "rc1", "e1", "cost")).toBe(0.5)
    expect(normalized_score(data, "rc2", "e1", "cost")).toBe(0.5)
  })

  it("inverts lower_is_better scores so higher normalized is always better", () => {
    const { summary, evals } = make_summary(
      [
        {
          id: "e1",
          name: "Eval One",
          scores: [
            { name: "errors", type: "custom", direction: "lower_is_better" },
          ],
        },
      ],
      {
        rc1: { e1: { means: { errors: 0 } } },
        rc2: { e1: { means: { errors: 10 } } },
      },
    )
    const data = build_lens_data(summary, evals)
    expect(normalized_score(data, "rc1", "e1", "errors")).toBe(1)
    expect(normalized_score(data, "rc2", "e1", "errors")).toBe(0)
  })

  it("defaults an unmatched score key to higher_is_better with no type", () => {
    // The eval list is empty, so no output_score meta backs the summary's keys
    const { summary } = make_summary(
      [
        {
          id: "e1",
          name: "Eval One",
          scores: [{ name: "mystery", type: "custom" }],
        },
      ],
      { rc1: { e1: { means: { mystery: 1 } } } },
    )
    const data = build_lens_data(summary, [])
    const meta = data.keyMetas.find((m) => m.scoreKey === "mystery")!
    expect(meta.type).toBeNull()
    expect(meta.direction).toBe("higher_is_better")
    expect(meta.evalName).toBe("Eval One")
  })

  it("returns empty data for a missing summary and skips non-finite means", () => {
    const empty = build_lens_data(null, [])
    expect(empty.keyMetas).toEqual([])
    expect(empty.raw.size).toBe(0)

    const { summary, evals } = make_summary(
      [
        {
          id: "e1",
          name: "Eval One",
          scores: [{ name: "pass", type: "pass_fail" }],
        },
      ],
      { rc1: { e1: { means: { pass: NaN } } } },
    )
    const data = build_lens_data(summary, evals)
    expect(raw_score(data, "rc1", "e1", "pass")).toBeNull()
    expect(normalized_score(data, "rc1", "e1", "pass")).toBeNull()
  })

  it("records per-eval completion", () => {
    const { summary, evals } = make_summary(
      [
        {
          id: "e1",
          name: "Eval One",
          scores: [{ name: "pass", type: "pass_fail" }],
        },
      ],
      { rc1: { e1: { means: { pass: 1 }, percent: 0.4 } } },
    )
    const data = build_lens_data(summary, evals)
    expect(percent_complete(data, "rc1", "e1")).toBe(0.4)
    expect(percent_complete(data, "rc1", "missing")).toBeNull()
    expect(percent_complete(data, "missing", "e1")).toBeNull()
  })
})

describe("lens values", () => {
  const { summary, evals } = make_summary(
    [
      {
        id: "e1",
        name: "Eval One",
        scores: [
          { name: "pass", type: "pass_fail" },
          { name: "five", type: "five_star" },
          { name: "notes", type: "custom", direction: "informational" },
        ],
      },
    ],
    {
      rc1: { e1: { means: { pass: 1, five: 3, notes: 999 } } },
      rc2: { e1: { means: { pass: 0, five: 1, notes: 0 } } },
      rc3: { e1: { means: {} } },
    },
  )
  const data = build_lens_data(summary, evals)

  it("averages the non-informational normalized scores for the aggregate lens", () => {
    // rc1: pass 1.0, five 0.5 -> 0.75 (the informational key is skipped)
    expect(
      normalized_lens_value(data, "rc1", { kind: "aggregate" }),
    ).toBeCloseTo(0.75, 6)
    expect(normalized_lens_value(data, "rc2", { kind: "aggregate" })).toBe(0)
  })

  it("returns null for the aggregate when a run config has no scores", () => {
    expect(normalized_lens_value(data, "rc3", { kind: "aggregate" })).toBeNull()
  })

  it("reads a single-score lens straight through", () => {
    const lens = { kind: "single" as const, evalId: "e1", scoreKey: "five" }
    expect(normalized_lens_value(data, "rc1", lens)).toBeCloseTo(0.5, 6)
    // The raw lens value is the score's own value, not the normalized one
    expect(raw_lens_value(data, "rc1", lens)).toBe(3)
  })

  it("uses the normalized mean as the aggregate's displayed raw value", () => {
    expect(raw_lens_value(data, "rc1", { kind: "aggregate" })).toBeCloseTo(
      0.75,
      6,
    )
  })

  it("computes the delta against a parent, and null when either side is missing", () => {
    const lens = { kind: "aggregate" as const }
    expect(delta_vs_parent(data, "rc1", "rc2", lens)).toBeCloseTo(0.75, 6)
    expect(delta_vs_parent(data, "rc2", "rc1", lens)).toBeCloseTo(-0.75, 6)
    expect(delta_vs_parent(data, "rc1", null, lens)).toBeNull()
    expect(delta_vs_parent(data, "rc1", "rc3", lens)).toBeNull()
  })
})

describe("lens_color", () => {
  it("bins normalized values darkest-is-best and grays out no score", () => {
    expect(lens_color(null)).toBe(NO_SCORE_COLOR)
    expect(lens_color(NaN)).toBe(NO_SCORE_COLOR)
    expect(lens_color(0)).toBe(SCORE_BIN_COLORS[0])
    expect(lens_color(0.39)).toBe(SCORE_BIN_COLORS[0])
    expect(lens_color(0.4)).toBe(SCORE_BIN_COLORS[1])
    expect(lens_color(0.59)).toBe(SCORE_BIN_COLORS[1])
    expect(lens_color(0.6)).toBe(SCORE_BIN_COLORS[2])
    expect(lens_color(0.75)).toBe(SCORE_BIN_COLORS[3])
    expect(lens_color(0.9)).toBe(SCORE_BIN_COLORS[4])
    expect(lens_color(1)).toBe(SCORE_BIN_COLORS[4])
  })
})

describe("strip_cells", () => {
  const { summary, evals } = make_summary(
    [
      {
        id: "e1",
        name: "Eval One",
        scores: [
          { name: "pass", type: "pass_fail" },
          { name: "tiny", type: "pass_fail" },
          { name: "gone", type: "pass_fail" },
          { name: "notes", type: "custom", direction: "informational" },
        ],
      },
    ],
    {
      child: { e1: { means: { pass: 1, tiny: 0.5, notes: 7 } } },
      parent: { e1: { means: { pass: 0.2, tiny: 0.5, gone: 1, notes: 3 } } },
    },
  )
  const data = build_lens_data(summary, evals)
  const by_key = (cells: ReturnType<typeof strip_cells>, key: string) =>
    cells.find((cell) => cell.scoreKey === key)!

  it("emits one cell per score key, always in the same order", () => {
    const with_parent = strip_cells(data, "child", "parent")
    const without = strip_cells(data, "child", null)
    expect(with_parent.map((c) => c.scoreKey)).toEqual(
      data.keyMetas.map((m) => m.scoreKey),
    )
    expect(without.map((c) => c.scoreKey)).toEqual(
      with_parent.map((c) => c.scoreKey),
    )
  })

  it("colors a real improvement as a better delta", () => {
    const cell = by_key(strip_cells(data, "child", "parent"), "pass")
    expect(cell.mode).toBe("delta")
    expect(cell.sign).toBe(1)
    expect(cell.color).toBe(STRIP_BETTER_COLOR)
    expect(cell.title).toContain("+0.80 vs parent")
    expect(cell.title).toContain("Eval One · Pass")
  })

  it("colors a regression as a worse delta", () => {
    const cell = by_key(strip_cells(data, "parent", "child"), "pass")
    expect(cell.sign).toBe(-1)
    expect(cell.color).toBe(STRIP_WORSE_COLOR)
    expect(cell.title).toContain("−0.80 vs parent")
  })

  it("treats a move inside the epsilon dead zone as neutral", () => {
    const cell = by_key(strip_cells(data, "child", "parent"), "tiny")
    expect(cell.mode).toBe("delta")
    expect(cell.sign).toBe(0)
    expect(cell.color).toBe(STRIP_NEUTRAL_COLOR)
    expect(cell.title).toContain("±0.00")
  })

  it("falls back to the absolute lens color when there is no parent at all", () => {
    const cell = by_key(strip_cells(data, "child", null), "pass")
    expect(cell.mode).toBe("absolute")
    expect(cell.sign).toBeNull()
    expect(cell.color).toBe(lens_color(1))
    expect(cell.title).toContain("no parent baseline")
  })

  it("falls back to absolute when the parent has no score for that key", () => {
    // "tiny" exists on both, but the parent has no "pass" if we flip who's who:
    // here the child has no "gone", so scoring the parent against the child
    // leaves that key without a baseline.
    const cell = by_key(strip_cells(data, "parent", "child"), "gone")
    expect(cell.mode).toBe("absolute")
    expect(cell.title).toContain("no parent baseline")
  })

  it("always shows informational keys absolutely, never as a delta", () => {
    const cell = by_key(strip_cells(data, "child", "parent"), "notes")
    expect(cell.mode).toBe("absolute")
    expect(cell.sign).toBeNull()
    expect(cell.title).toContain("informational")
  })

  it("leaves an unscored key blank", () => {
    const cell = by_key(strip_cells(data, "child", "parent"), "gone")
    expect(cell.mode).toBe("empty")
    expect(cell.sign).toBeNull()
    expect(cell.color).toBe(STRIP_EMPTY_COLOR)
    expect(cell.title).toContain("not scored")
  })
})

describe("strip_cell_color", () => {
  it("maps a delta sign to its fill", () => {
    expect(strip_cell_color(1)).toBe(STRIP_BETTER_COLOR)
    expect(strip_cell_color(-1)).toBe(STRIP_WORSE_COLOR)
    expect(strip_cell_color(0)).toBe(STRIP_NEUTRAL_COLOR)
    expect(strip_cell_color(null)).toBe(STRIP_NEUTRAL_COLOR)
  })
})
