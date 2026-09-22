import type { Eval } from "$lib/types"
import { eval_split } from "$lib/utils/eval_splits"
import {
  allocate_splits,
  encode_splits_for_url,
  type WeightedSplit,
} from "$lib/utils/splits_util"

// How generated data is divided between an eval's splits. These are relative weights, not
// percentages: whichever splits the eval can't receive data for are dropped and the rest are
// rescaled to 100% (see allocate_splits). Most goes to train because that's the set which has
// to be large; golden gets the least because it's the hand-curated one.
// Mirrored by TEST_DEAL_WEIGHT / TRAIN_DEAL_WEIGHT / VAL_DEAL_WEIGHT in
// app/desktop/studio_server/utils/copilot_utils.py, which deals the eval
// builder's cases. Change one and change the other, or generated data and
// builder-saved data land in the splits at different ratios.
export const TRAIN_SPLIT_WEIGHT = 40
export const VAL_SPLIT_WEIGHT = 25
export const TEST_SPLIT_WEIGHT = 25
export const GOLDEN_SPLIT_WEIGHT = 10

// The tag a filter selects, or undefined if the filter isn't a tag filter. An empty tag
// ("tag::") counts as not tag-shaped: there is no tag there to write onto a run.
function tag_from_filter_id(
  filter_id: string | null | undefined,
): string | undefined {
  if (!filter_id?.startsWith("tag::")) {
    return undefined
  }
  return filter_id.slice("tag::".length) || undefined
}

// A split's tag and the store its cases live in.
type SplitTarget = {
  tag: string
  source: "task_run" | "eval_input"
}

// The tag one of the eval's splits selects, whichever store backs it. Undefined when the eval
// doesn't have the split at all (splits are legitimately absent — see
// specs/projects/eval_splits_v1_v2/functional_spec.md §3.2 — and nothing here may invent one)
// or its filter names no tag.
function split_target(
  evaluator: Eval,
  name: "train" | "val" | "test",
): SplitTarget | undefined {
  const split = eval_split(evaluator, name)
  const tag = tag_from_filter_id(split?.filter_id)
  if (!split || !tag) {
    return undefined
  }
  return { tag, source: split.source }
}

// The tag one of the eval's splits selects, but only when generated data can actually land in
// it: the split has to hold TaskRuns. Generation appends TaskRuns to the dataset, so an
// EvalInput-backed split would never see the data we tagged for it.
function targetable_split_tag(
  evaluator: Eval,
  name: "train" | "val" | "test",
): string | undefined {
  const target = split_target(evaluator, name)
  return target?.source === "task_run" ? target.tag : undefined
}

// The eval's golden tag, or undefined when nothing can be dealt into it.
//
// Rag evals are given a golden tag at creation like every other eval, but the rag flow has no
// human-ratings step and never reads it. Allocating to it would write the user's generated
// data into a tag nothing can consume, so rag skips golden and its weight goes to the other
// splits.
function golden_tag(evaluator: Eval): string | undefined {
  // Golden is a plain filter id on the eval rather than a split — it's deliberately absent
  // from the splits dict, so it's read directly.
  return evaluator.template === "rag"
    ? undefined
    : tag_from_filter_id(evaluator.eval_configs_filter_id)
}

/**
 * The tags generated data should be split across for an eval, as fractions summing to 1.
 *
 * Every split the data can't reach is dropped and the remaining weights rescaled, so an eval
 * with only the splits it was born with (test + golden, the shape of every pre-existing eval)
 * still gets a full allocation. Order matters: it decides who wins the leftover percentage
 * points, and train/val/test/golden is the order of that claim.
 *
 * Returns undefined when the test split can't be targeted at all. That split is mandatory —
 * with no tag to write runs into there is nothing to generate for — so the caller refuses
 * rather than generating data that lands nowhere.
 */
export function build_eval_generation_splits(
  evaluator: Eval,
): Record<string, number> | undefined {
  const test_tag = targetable_split_tag(evaluator, "test")
  if (!test_tag) {
    return undefined
  }

  const weighted: WeightedSplit[] = []
  const train_tag = targetable_split_tag(evaluator, "train")
  if (train_tag) {
    weighted.push({ tag: train_tag, weight: TRAIN_SPLIT_WEIGHT })
  }
  const val_tag = targetable_split_tag(evaluator, "val")
  if (val_tag) {
    weighted.push({ tag: val_tag, weight: VAL_SPLIT_WEIGHT })
  }
  weighted.push({ tag: test_tag, weight: TEST_SPLIT_WEIGHT })
  const golden = golden_tag(evaluator)
  if (golden) {
    weighted.push({ tag: golden, weight: GOLDEN_SPLIT_WEIGHT })
  }

  return allocate_splits(weighted)
}

export type SynthGenerationSplits = {
  splits: Record<string, number>
  // The subset of `splits` whose tags select eval inputs rather than runs.
  eval_input_tags: string[]
}

/**
 * The tags synthetic data generation should spread an eval's cases over, and which of those
 * tags hold eval inputs.
 *
 * The same allocation as build_eval_generation_splits, except that an EvalInput-backed split
 * is allocated to rather than dropped: this flow can write a case to either store, so it
 * reports the backing instead of refusing.
 *
 * Returns undefined for the same reason build_eval_generation_splits does — no test split
 * naming a tag — so callers can refuse rather than generating cases that land nowhere.
 */
export function build_synth_generation_splits(
  evaluator: Eval,
): SynthGenerationSplits | undefined {
  const test = split_target(evaluator, "test")
  if (!test) {
    return undefined
  }

  const weighted: WeightedSplit[] = []
  const eval_input_tags: string[] = []
  // Order matters: it decides who wins the leftover percentage points, and
  // train/val/test/golden is the order of that claim.
  const add_split = (target: SplitTarget | undefined, weight: number) => {
    if (!target) {
      return
    }
    weighted.push({ tag: target.tag, weight })
    if (target.source === "eval_input") {
      eval_input_tags.push(target.tag)
    }
  }
  add_split(split_target(evaluator, "train"), TRAIN_SPLIT_WEIGHT)
  add_split(split_target(evaluator, "val"), VAL_SPLIT_WEIGHT)
  add_split(test, TEST_SPLIT_WEIGHT)

  const golden = golden_tag(evaluator)
  if (golden) {
    weighted.push({ tag: golden, weight: GOLDEN_SPLIT_WEIGHT })
  }

  return { splits: allocate_splits(weighted), eval_input_tags }
}

/**
 * The same allocation as build_eval_generation_splits, encoded for the `splits` URL param.
 *
 * Every flow that sends the user off to add data for an eval goes through here, so the
 * allocation an eval gets doesn't depend on which button was pressed to reach it. Returns
 * undefined for the same reason build_eval_generation_splits does — no targetable test
 * split — so callers can refuse rather than navigating with no allocation.
 */
export function build_eval_generation_splits_param(
  evaluator: Eval,
): string | undefined {
  const splits = build_eval_generation_splits(evaluator)
  return splits ? encode_splits_for_url(splits) : undefined
}
