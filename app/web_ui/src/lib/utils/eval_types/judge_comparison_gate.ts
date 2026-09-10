import type { Eval, EvalConfig, EvalDataType } from "$lib/types"
import { assertNever } from "$lib/utils/exhaustive"
import {
  extractV2Props,
  getV2TypeFromEvalConfig,
  referenceDataKeys,
} from "./registry"

/**
 * Whether an eval's data type means its V1 judges grade against ground truth.
 *
 * A switch rather than an `=== "reference_answer"` equality test: a fourth
 * `EvalDataType` that needs reference data would answer false silently, which is the
 * same failure the "anything that isn't v2" spelling below exists to prevent, one level
 * down. `assertNever` makes adding a member break the build until it is classified.
 *
 * Mirrors `eval_grades_against_reference_data` (`app/desktop/studio_server/eval_api.py`).
 * An absent value means the eval never declared one, so nothing asks for a reference.
 * `undefined` is accepted alongside `null` so an older payload that omits the field
 * answers false rather than reaching `assertNever`.
 */
function eval_grades_against_reference_data(
  data_type: EvalDataType | null | undefined,
): boolean {
  if (data_type === null || data_type === undefined) {
    return false
  }
  switch (data_type) {
    case "reference_answer":
      return true
    case "final_answer":
    case "full_trace":
      return false
    default:
      return assertNever(data_type)
  }
}

/**
 * Whether judge comparison must refuse to run this judge.
 *
 * Judge comparison scores each golden dataset item as *itself*: the item is both the
 * thing being graded and the record it would be graded against, so
 * `EvalTaskInput.from_trace` deliberately supplies no reference data (populating it
 * would make the reference byte-identical to the output and every judge would pass
 * every item). A judge that grades against reference data therefore has nothing to
 * read here, whatever the golden set contains.
 *
 * Two judge kinds land in that state, which is why one predicate covers both:
 *
 * - a V2 judge declaring at least one reference key — `check_reference_key` skips
 *   every item with `missing_reference_key`
 * - a V1 judge (`g_eval` / `llm_as_judge`) on a `reference_answer` eval — `GEval`
 *   raises "Eval job item is required for reference answer evaluation" per item
 *
 * The client mirror of `judge_requires_reference_data`
 * (`app/desktop/studio_server/eval_api.py`), which is what actually refuses the run.
 * This one decides what the page shows.
 *
 * The V1 arm is spelled "anything that isn't v2", matching `judge_scores_dataset_runs`
 * server-side: a judge type added to the enum later is blocked here rather than quietly
 * reaching the per-item error this exists to prevent.
 *
 * No condition on where the golden items come from: golden is TaskRun-only by
 * construction (`Eval.eval_configs_filter_id` is `DatasetFilterId`-typed, and
 * `_calibration_item` raises for anything else).
 */
export function compute_run_disallowed_missing_ref_data(
  eval_config: EvalConfig,
  evaluator: Eval,
): boolean {
  if (eval_config.config_type !== "v2") {
    return eval_grades_against_reference_data(evaluator.evaluation_data_type)
  }
  const v2_type = getV2TypeFromEvalConfig(eval_config)
  if (v2_type === null) {
    return false
  }
  const props = extractV2Props(eval_config, v2_type)
  return props !== null && referenceDataKeys(props).length > 0
}

/**
 * The subset of `eval_configs` judge comparison can actually score. Mirrors the
 * filtering `run_calibration` applies server-side, so a page that offers "Run All
 * Evals" offers it for exactly the judges the run will cover.
 */
export function comparable_eval_configs(
  eval_configs: EvalConfig[] | null,
  evaluator: Eval | null,
): EvalConfig[] {
  if (!eval_configs || !evaluator) {
    return []
  }
  return eval_configs.filter(
    (eval_config) =>
      !compute_run_disallowed_missing_ref_data(eval_config, evaluator),
  )
}
