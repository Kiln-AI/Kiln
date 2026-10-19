import { describe, it, expect } from "vitest"
import {
  eval_split,
  eval_split_filter_id,
  task_run_split_filter_id,
} from "./eval_splits"
import type { Eval } from "$lib/types"

function make_eval(fields: Partial<Eval>): Eval {
  return { id: "eval1", name: "Eval", output_scores: [], ...fields } as Eval
}

describe("eval_split", () => {
  it("falls back to a legacy flat field on an unmigrated eval", () => {
    const evaluator = make_eval({
      eval_set_filter_id: "tag::test_x",
      train_set_filter_id: "tag::train_x",
      splits: {},
    })

    expect(eval_split(evaluator, "test")).toEqual({
      source: "task_run",
      filter_id: "tag::test_x",
    })
    expect(eval_split(evaluator, "train")).toEqual({
      source: "task_run",
      filter_id: "tag::train_x",
    })
  })

  it("reads a split the server wrote to the splits dict", () => {
    const evaluator = make_eval({
      eval_set_filter_id: null,
      splits: {
        test: { source: "task_run", filter_id: "tag::test_x" },
        val: { source: "task_run", filter_id: "tag::val_x" },
      },
    })

    expect(eval_split(evaluator, "test")?.filter_id).toBe("tag::test_x")
    expect(eval_split(evaluator, "val")?.filter_id).toBe("tag::val_x")
  })

  it("reads an EvalInput-backed split with its source", () => {
    const evaluator = make_eval({
      eval_set_filter_id: null,
      splits: { test: { source: "eval_input", filter_id: "tag::inputs" } },
    })

    expect(eval_split(evaluator, "test")).toEqual({
      source: "eval_input",
      filter_id: "tag::inputs",
    })
  })

  it("prefers the splits entry when both are populated, as the datamodel does", () => {
    const evaluator = make_eval({
      eval_set_filter_id: "tag::legacy",
      splits: { test: { source: "task_run", filter_id: "tag::native" } },
    })

    expect(eval_split(evaluator, "test")?.filter_id).toBe("tag::native")
  })

  it("is undefined for a split the eval does not have", () => {
    const evaluator = make_eval({
      eval_set_filter_id: "tag::test_x",
      train_set_filter_id: null,
      splits: {},
    })

    expect(eval_split(evaluator, "train")).toBeUndefined()
    expect(eval_split(evaluator, "val")).toBeUndefined()
  })

  it("is undefined for an eval that hasn't loaded", () => {
    expect(eval_split(null, "test")).toBeUndefined()
    expect(eval_split(undefined, "test")).toBeUndefined()
  })

  it("tolerates an eval with no splits key at all", () => {
    expect(eval_split(make_eval({}), "test")).toBeUndefined()
  })
})

describe("task_run_split_filter_id", () => {
  it("returns the filter id of a TaskRun-backed split", () => {
    const evaluator = make_eval({
      splits: { val: { source: "task_run", filter_id: "tag::val_x" } },
    })

    expect(task_run_split_filter_id(evaluator, "val")).toBe("tag::val_x")
  })

  it("refuses an EvalInput-backed split, which addresses a different store", () => {
    const evaluator = make_eval({
      eval_set_filter_id: null,
      splits: { test: { source: "eval_input", filter_id: "tag::inputs" } },
    })

    // Displaying the filter id is still correct; building a dataset link from it is not.
    expect(eval_split_filter_id(evaluator, "test")).toBe("tag::inputs")
    expect(task_run_split_filter_id(evaluator, "test")).toBeUndefined()
  })
})
