import type { Eval } from "$lib/types"

export type EvalSplitName = "train" | "val" | "test"

export type EvalSplitRef = {
  source: "task_run" | "eval_input"
  filter_id: string
}

// The deprecated flat field a Kiln build predating `splits` stored a split in. Only these
// two splits ever had one, and only when they're TaskRun-backed.
//
// MIRRORS PYTHON: `LEGACY_SPLIT_FIELDS` in `libs/core/kiln_ai/datamodel/eval.py`. That
// map is the source of truth. Adding a split name there means adding it here.
const LEGACY_SPLIT_FIELDS = {
  test: "eval_set_filter_id",
  train: "train_set_filter_id",
} as const

/**
 * One of an eval's splits.
 *
 * `splits` is the only home. The server migrates a legacy flat field into `splits` when
 * it loads the eval, and serializes that field as null, so every eval the API hands this
 * client already carries its splits in `splits`. The legacy read below is a fallback for
 * an eval that somehow reaches the client unmigrated, and it never wins: once a split is
 * in `splits`, that is the eval's answer.
 *
 * MIRRORS PYTHON: this is `Eval.migrate_legacy_split_fields` in
 * `libs/core/kiln_ai/datamodel/eval.py`, precedence included. Nothing enforces that the
 * two stay in step, so a change to that validator (or to `LEGACY_SPLIT_FIELDS` above)
 * has to be made here as well.
 */
export function eval_split(
  evaluator: Eval | null | undefined,
  name: EvalSplitName,
): EvalSplitRef | undefined {
  if (!evaluator) {
    return undefined
  }
  const split = evaluator.splits?.[name]
  if (split) {
    return { source: split.source, filter_id: split.filter_id }
  }
  const legacy_field =
    name in LEGACY_SPLIT_FIELDS
      ? LEGACY_SPLIT_FIELDS[name as keyof typeof LEGACY_SPLIT_FIELDS]
      : undefined
  const legacy_filter_id = legacy_field ? evaluator[legacy_field] : null
  if (legacy_filter_id) {
    return { source: "task_run", filter_id: legacy_filter_id }
  }
  return undefined
}

/**
 * The filter id of one of an eval's splits, whichever store backs it.
 *
 * For display only. A filter id is a predicate, not a location — the same `tag::x`
 * selects different items depending on the split's backing — so anything that resolves
 * the filter itself wants task_run_split_filter_id instead.
 */
export function eval_split_filter_id(
  evaluator: Eval | null | undefined,
  name: EvalSplitName,
): string | undefined {
  return eval_split(evaluator, name)?.filter_id
}

/**
 * The filter id of one of an eval's splits, only when its items are TaskRuns.
 *
 * Dataset tags, `/dataset` links and synthetic data generation all address the task's
 * runs. An EvalInput-backed split's filter id is a valid string in that grammar but
 * points at nothing in that store, so callers building those get undefined instead of a
 * link that silently lands on an empty dataset view.
 */
export function task_run_split_filter_id(
  evaluator: Eval | null | undefined,
  name: EvalSplitName,
): string | undefined {
  const split = eval_split(evaluator, name)
  return split?.source === "task_run" ? split.filter_id : undefined
}
