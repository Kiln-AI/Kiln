import { describe, it, expect } from "vitest"
import { correlatable_scores, sort_task_run_configs } from "./run_config_sort"
import type {
  Eval,
  EvalOutputScore,
  EvalResultSummary,
  TaskOutputRatingType,
  TaskRunConfig,
} from "$lib/types"

function score(name: string, type: TaskOutputRatingType): EvalOutputScore {
  return { name, type, instruction: null } as EvalOutputScore
}

function evaluator(output_scores: EvalOutputScore[]): Eval {
  return { output_scores } as Eval
}

function run_config(id: string | null, name: string): TaskRunConfig {
  return { id, name } as TaskRunConfig
}

function summary(
  results: Record<string, Record<string, { mean_score: number }>>,
): EvalResultSummary {
  return { results } as unknown as EvalResultSummary
}

describe("correlatable_scores", () => {
  it("drops custom-typed scores", () => {
    const scores = [
      score("Accuracy", "pass_fail"),
      score("Cost", "custom"),
      score("Tone", "five_star"),
    ]
    expect(correlatable_scores(scores).map((s) => s.name)).toEqual([
      "Accuracy",
      "Tone",
    ])
  })

  it("returns an empty list for missing input", () => {
    expect(correlatable_scores(undefined)).toEqual([])
    expect(correlatable_scores(null)).toEqual([])
  })
})

describe("sort_task_run_configs", () => {
  // Names are chosen so alphabetical order is [cheap, good], the opposite of
  // the score order in most cases below. Each case therefore fails if the
  // rule it targets is removed, rather than passing on the name fallback.
  const configs = [
    run_config("cheap", "Alpha Cheap"),
    run_config("good", "Zebra Good"),
  ]

  it("ranks by the last correlatable score, highest first", () => {
    const sorted = sort_task_run_configs(
      configs,
      evaluator([score("Accuracy", "pass_fail")]),
      summary({
        cheap: { accuracy: { mean_score: 0.2 } },
        good: { accuracy: { mean_score: 0.9 } },
      }),
      null,
    )
    expect(sorted.map((c) => c.id)).toEqual(["good", "cheap"])
  })

  it("ranks by the last correlatable score, not the first", () => {
    // The two scores disagree, so ranking by either end gives a different
    // order — and both differ from the alphabetical fallback.
    const sorted = sort_task_run_configs(
      configs,
      evaluator([score("Accuracy", "pass_fail"), score("Tone", "five_star")]),
      summary({
        cheap: { accuracy: { mean_score: 0.9 }, tone: { mean_score: 0.2 } },
        good: { accuracy: { mean_score: 0.2 }, tone: { mean_score: 0.9 } },
      }),
      null,
    )
    expect(sorted.map((c) => c.id)).toEqual(["good", "cheap"])
  })

  it("ignores a trailing custom metric so cost does not rank run configs", () => {
    // Ranking by the trailing cost metric would put the expensive config
    // first, since higher wins.
    const sorted = sort_task_run_configs(
      configs,
      evaluator([score("Accuracy", "pass_fail"), score("Cost", "custom")]),
      summary({
        cheap: { accuracy: { mean_score: 0.2 }, cost: { mean_score: 99 } },
        good: { accuracy: { mean_score: 0.9 }, cost: { mean_score: 1 } },
      }),
      null,
    )
    expect(sorted.map((c) => c.id)).toEqual(["good", "cheap"])
  })

  it("falls back to name order when every score is custom-typed", () => {
    // Ranking by cost here would give [good, cheap], so name order proves the
    // custom score was never used as a sort key.
    const sorted = sort_task_run_configs(
      configs,
      evaluator([score("Cost", "custom")]),
      summary({
        cheap: { cost: { mean_score: 1 } },
        good: { cost: { mean_score: 99 } },
      }),
      null,
    )
    expect(sorted.map((c) => c.id)).toEqual(["cheap", "good"])
  })

  it("puts the task default run config first regardless of score", () => {
    // The default has the lower score, so only the default rule can lift it.
    const sorted = sort_task_run_configs(
      configs,
      evaluator([score("Accuracy", "pass_fail")]),
      summary({
        cheap: { accuracy: { mean_score: 0.9 } },
        good: { accuracy: { mean_score: 0.2 } },
      }),
      "good",
    )
    expect(sorted.map((c) => c.id)).toEqual(["good", "cheap"])
  })

  it("sorts run configs missing a score after those that have one", () => {
    const sorted = sort_task_run_configs(
      configs,
      evaluator([score("Accuracy", "pass_fail")]),
      summary({ good: { accuracy: { mean_score: 0.2 } } }),
      null,
    )
    expect(sorted.map((c) => c.id)).toEqual(["good", "cheap"])
  })

  it("returns an empty list for missing or empty configs", () => {
    expect(sort_task_run_configs(null, null, null, null)).toEqual([])
    expect(sort_task_run_configs([], null, null, null)).toEqual([])
  })

  it("falls back to name order with no evaluator or summary", () => {
    // Input order is reversed so a comparator that never sorts would fail.
    const sorted = sort_task_run_configs(
      [...configs].reverse(),
      null,
      null,
      null,
    )
    expect(sorted.map((c) => c.id)).toEqual(["cheap", "good"])
  })

  it("does not treat an id-less config as the default when none is set", () => {
    // Run config ids are nullable, so a null === null match would float an
    // unsaved config above a scored one.
    const sorted = sort_task_run_configs(
      [run_config("good", "Zebra Good"), run_config(null, "Alpha Unsaved")],
      evaluator([score("Accuracy", "pass_fail")]),
      summary({ good: { accuracy: { mean_score: 0.9 } } }),
      null,
    )
    expect(sorted.map((c) => c.name)).toEqual(["Zebra Good", "Alpha Unsaved"])
  })
})
