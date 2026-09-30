import { describe, it, expect } from "vitest"
import { readFileSync } from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"
import type { Eval } from "$lib/types"
import {
  build_eval_generation_splits,
  build_eval_generation_splits_param,
  build_synth_generation_splits,
} from "./eval_generation_splits"

function make_eval(fields: Partial<Eval>): Eval {
  return {
    id: "eval1",
    name: "Eval",
    output_scores: [],
    eval_set_filter_id: null,
    eval_configs_filter_id: null,
    ...fields,
  } as Eval
}

function task_run(filter_id: string) {
  return { source: "task_run" as const, filter_id }
}

function eval_input(filter_id: string) {
  return { source: "eval_input" as const, filter_id }
}

describe("build_eval_generation_splits", () => {
  it("allocates 40/25/25/10 when all four splits are configured", () => {
    const splits = build_eval_generation_splits(
      make_eval({
        splits: {
          train: task_run("tag::train_tag"),
          val: task_run("tag::val_tag"),
          test: task_run("tag::test_tag"),
        },
        eval_configs_filter_id: "tag::golden_tag",
      }),
    )

    expect(splits).toEqual({
      train_tag: 0.4,
      val_tag: 0.25,
      test_tag: 0.25,
      golden_tag: 0.1,
    })
  })

  it("allocates 71/29 for the test + golden shape every pre-existing eval has", () => {
    const splits = build_eval_generation_splits(
      make_eval({
        eval_set_filter_id: "tag::test_tag",
        eval_configs_filter_id: "tag::golden_tag",
        splits: {},
      }),
    )

    expect(splits).toEqual({ test_tag: 0.71, golden_tag: 0.29 })
  })

  it("allocates 44/28/28 for train + val + test with no golden", () => {
    const splits = build_eval_generation_splits(
      make_eval({
        splits: {
          train: task_run("tag::train_tag"),
          val: task_run("tag::val_tag"),
          test: task_run("tag::test_tag"),
        },
      }),
    )

    expect(splits).toEqual({ train_tag: 0.44, val_tag: 0.28, test_tag: 0.28 })
  })

  it("gives everything to test when it is the only configured split", () => {
    const splits = build_eval_generation_splits(
      make_eval({ splits: { test: task_run("tag::test_tag") } }),
    )

    expect(splits).toEqual({ test_tag: 1 })
  })

  it("reads splits the server wrote to the legacy flat fields", () => {
    const splits = build_eval_generation_splits(
      make_eval({
        eval_set_filter_id: "tag::test_tag",
        train_set_filter_id: "tag::train_tag",
        splits: { val: task_run("tag::val_tag") },
      }),
    )

    expect(splits).toEqual({ train_tag: 0.44, val_tag: 0.28, test_tag: 0.28 })
  })

  it("does not invent a train or val split that the eval doesn't have", () => {
    const splits = build_eval_generation_splits(
      make_eval({
        eval_set_filter_id: "tag::test_tag",
        train_set_filter_id: null,
        splits: {},
      }),
    )

    expect(splits).toEqual({ test_tag: 1 })
  })

  it("drops an EvalInput-backed train split and rescales the rest", () => {
    // Generation adds task runs to the dataset, so data tagged for an EvalInput-backed split
    // would never show up in it.
    const splits = build_eval_generation_splits(
      make_eval({
        splits: {
          train: { source: "eval_input", filter_id: "tag::train_tag" },
          val: task_run("tag::val_tag"),
          test: task_run("tag::test_tag"),
        },
      }),
    )

    expect(splits).toEqual({ val_tag: 0.5, test_tag: 0.5 })
  })

  it("drops a train or val split whose filter isn't a tag filter", () => {
    const splits = build_eval_generation_splits(
      make_eval({
        splits: {
          train: task_run("all"),
          val: task_run("tag::"),
          test: task_run("tag::test_tag"),
        },
        eval_configs_filter_id: "tag::golden_tag",
      }),
    )

    expect(splits).toEqual({ test_tag: 0.71, golden_tag: 0.29 })
  })

  it("drops a golden filter that isn't a tag filter rather than refusing", () => {
    const splits = build_eval_generation_splits(
      make_eval({
        splits: {
          train: task_run("tag::train_tag"),
          test: task_run("tag::test_tag"),
        },
        eval_configs_filter_id: "high_rating::overall_rating::4",
      }),
    )

    expect(splits).toEqual({ train_tag: 0.62, test_tag: 0.38 })
  })

  it("refuses when the eval has no test split", () => {
    expect(
      build_eval_generation_splits(
        make_eval({
          splits: { train: task_run("tag::train_tag") },
          eval_configs_filter_id: "tag::golden_tag",
        }),
      ),
    ).toBeUndefined()
  })

  it("refuses when the test split isn't a tag filter", () => {
    expect(
      build_eval_generation_splits(
        make_eval({ splits: { test: task_run("all") } }),
      ),
    ).toBeUndefined()
  })

  it("refuses when the test split is EvalInput-backed", () => {
    expect(
      build_eval_generation_splits(
        make_eval({
          splits: {
            test: { source: "eval_input", filter_id: "tag::test_tag" },
          },
        }),
      ),
    ).toBeUndefined()
  })

  it("always produces splits that sum to 1", () => {
    const evals = [
      make_eval({
        splits: {
          train: task_run("tag::a"),
          val: task_run("tag::b"),
          test: task_run("tag::c"),
        },
        eval_configs_filter_id: "tag::d",
      }),
      make_eval({
        splits: { val: task_run("tag::b"), test: task_run("tag::c") },
      }),
      make_eval({
        splits: { train: task_run("tag::a"), test: task_run("tag::c") },
        eval_configs_filter_id: "tag::d",
      }),
      make_eval({ eval_set_filter_id: "tag::c", eval_configs_filter_id: null }),
    ]

    for (const evaluator of evals) {
      const splits = build_eval_generation_splits(evaluator) ?? {}
      const total = Object.values(splits).reduce((sum, v) => sum + v, 0)
      expect(total).toBeCloseTo(1, 10)
    }
  })
})

describe("build_eval_generation_splits_param", () => {
  it("encodes the allocation as the `splits` URL param", () => {
    const param = build_eval_generation_splits_param(
      make_eval({
        splits: {
          train: task_run("tag::train_tag"),
          val: task_run("tag::val_tag"),
          test: task_run("tag::test_tag"),
        },
        eval_configs_filter_id: "tag::golden_tag",
      }),
    )

    expect(param).toBe(
      "train_tag:0.4,val_tag:0.25,test_tag:0.25,golden_tag:0.1",
    )
  })

  it("gives a rag eval no golden share, even though it has a golden tag", () => {
    // Every eval is minted with a golden tag, rag included, but the rag flow has no
    // human-ratings step and never reads it. Allocating to it would drop the user's data
    // into a tag nothing consumes, so the whole allocation goes to the test split.
    const rag_eval = make_eval({
      template: "rag",
      eval_set_filter_id: "tag::test_tag",
      eval_configs_filter_id: "tag::golden_tag",
      splits: {},
    })

    expect(build_eval_generation_splits_param(rag_eval)).toBe("test_tag:1")
  })

  it("gives a non-rag eval with the same shape a golden share", () => {
    // The pair that pins the rag branch above to the template, not to the eval's shape.
    const eval_with_golden = make_eval({
      template: "kiln_requirements",
      eval_set_filter_id: "tag::test_tag",
      eval_configs_filter_id: "tag::golden_tag",
      splits: {},
    })

    expect(build_eval_generation_splits_param(eval_with_golden)).toBe(
      "test_tag:0.71,golden_tag:0.29",
    )
  })

  it("refuses when the eval has no targetable test split", () => {
    expect(
      build_eval_generation_splits_param(
        make_eval({ splits: { train: task_run("tag::train_tag") } }),
      ),
    ).toBeUndefined()
  })
})

describe("build_synth_generation_splits", () => {
  it("allocates to an eval builder eval's splits and names them as eval inputs", () => {
    // Every split holds eval inputs, so all three are targetable and the whole allocation
    // goes to them.
    const result = build_synth_generation_splits(
      make_eval({
        splits: {
          train: eval_input("tag::train_tag"),
          val: eval_input("tag::val_tag"),
          test: eval_input("tag::test_tag"),
        },
        eval_configs_filter_id: "tag::golden_tag",
      }),
    )

    expect(result?.splits).toEqual({
      train_tag: 0.4,
      val_tag: 0.25,
      test_tag: 0.25,
      golden_tag: 0.1,
    })
    expect(result?.eval_input_tags).toEqual([
      "train_tag",
      "val_tag",
      "test_tag",
    ])
  })

  it("gives an eval builder eval's golden the same share as any other eval's", () => {
    // Golden is a tag on runs whatever the other splits hold, so generation fills it here
    // exactly as it does for an eval whose splits all hold runs.
    const result = build_synth_generation_splits(
      make_eval({
        splits: { test: eval_input("tag::test_tag") },
        eval_configs_filter_id: "tag::golden_tag",
      }),
    )

    expect(result?.splits).toEqual({ test_tag: 0.71, golden_tag: 0.29 })
    // Golden holds runs, so it is not one of the tags the caller writes as eval inputs.
    expect(result?.eval_input_tags).toEqual(["test_tag"])
  })

  it("allocates a legacy eval exactly as the task-run-only helper does", () => {
    const legacy = make_eval({
      eval_set_filter_id: "tag::test_tag",
      eval_configs_filter_id: "tag::golden_tag",
      splits: {},
    })

    const result = build_synth_generation_splits(legacy)

    expect(result?.splits).toEqual({ test_tag: 0.71, golden_tag: 0.29 })
    expect(result?.splits).toEqual(build_eval_generation_splits(legacy))
    expect(result?.eval_input_tags).toEqual([])
  })

  it("handles the mixed eval the legacy copilot flow creates", () => {
    // That flow writes the test cases as eval inputs and the train cases as runs. Both are
    // targetable, each through its own store, and golden still stays out.
    const result = build_synth_generation_splits(
      make_eval({
        splits: {
          test: eval_input("tag::test_tag"),
          train: task_run("tag::train_tag"),
        },
        eval_configs_filter_id: "tag::golden_tag",
      }),
    )

    expect(result?.splits).toEqual({
      train_tag: 0.54,
      test_tag: 0.33,
      golden_tag: 0.13,
    })
    expect(result?.eval_input_tags).toEqual(["test_tag"])
  })

  it("gives a rag eval no golden share, matching the task-run-only helper", () => {
    const result = build_synth_generation_splits(
      make_eval({
        template: "rag",
        eval_set_filter_id: "tag::test_tag",
        eval_configs_filter_id: "tag::golden_tag",
        splits: {},
      }),
    )

    expect(result?.splits).toEqual({ test_tag: 1 })
    expect(result?.eval_input_tags).toEqual([])
  })

  it("refuses when the test split names no tag, whichever store backs it", () => {
    expect(
      build_synth_generation_splits(
        make_eval({ splits: { test: eval_input("all") } }),
      ),
    ).toBeUndefined()
    expect(
      build_synth_generation_splits(
        make_eval({ splits: { test: eval_input("tag::") } }),
      ),
    ).toBeUndefined()
    expect(
      build_synth_generation_splits(
        make_eval({ splits: { train: eval_input("tag::train_tag") } }),
      ),
    ).toBeUndefined()
  })

  it("always produces splits that sum to 1", () => {
    const evals = [
      make_eval({
        splits: {
          train: eval_input("tag::a"),
          val: eval_input("tag::b"),
          test: eval_input("tag::c"),
        },
        eval_configs_filter_id: "tag::d",
      }),
      make_eval({
        splits: { train: task_run("tag::a"), test: eval_input("tag::c") },
        eval_configs_filter_id: "tag::d",
      }),
      make_eval({
        splits: { val: eval_input("tag::b"), test: eval_input("tag::c") },
      }),
    ]

    for (const evaluator of evals) {
      const splits = build_synth_generation_splits(evaluator)?.splits ?? {}
      const total = Object.values(splits).reduce((sum, v) => sum + v, 0)
      expect(total).toBeCloseTo(1, 10)
    }
  })
})

describe("add-eval-data entry points", () => {
  // Three buttons lead into the same "add data for this eval" flow. They used to build the
  // `splits` param each on their own, and drifted: two hardcoded 80/20 while the third
  // allocated across all four datasets. Each one asking this helper is the fix, so the
  // check is that none of them has grown its own allocation again — a divergence no
  // single-page test can see, since the bug is that two pages disagree.
  const src_dir = path.resolve(
    path.dirname(fileURLToPath(import.meta.url)),
    "../..",
  )
  //
  // The synthetic data intro asks for the sibling that also allocates to eval-input splits;
  // the other two send the user to /dataset/add_data, which writes runs, so they ask for the
  // task-run-only helper. Both live here, so neither can drift from the weights.
  const entry_points = {
    "synthetic data generation intro": {
      path: "routes/(app)/generate/[project_id]/[task_id]/data_gen_intro.svelte",
      helper: "build_synth_generation_splits(",
    },
    "eval detail page": {
      path: "routes/(app)/specs/[project_id]/[task_id]/[spec_id]/[eval_id]/+page.svelte",
      helper: "build_eval_generation_splits_param(",
    },
    "compare page": {
      path: "routes/(app)/specs/[project_id]/[task_id]/compare/+page.svelte",
      helper: "build_eval_generation_splits_param(",
    },
  }

  for (const [name, entry_point] of Object.entries(entry_points)) {
    it(`the ${name} builds its splits param with the shared helper`, () => {
      const source = readFileSync(path.join(src_dir, entry_point.path), "utf-8")

      expect(source).toContain(entry_point.helper)
      // No literal allocation anywhere: `tag:0.8,tag:0.2` and the rag-only `tag:1.0` are
      // exactly what these files used to write.
      expect(source).not.toMatch(/params\.set\(\s*"splits",\s*`/)
    })
  }
})
