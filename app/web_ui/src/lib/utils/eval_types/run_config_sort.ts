import type {
  Eval,
  EvalOutputScore,
  EvalResultSummary,
  TaskRunConfig,
} from "$lib/types"
import { string_to_json_key } from "$lib/utils/json_schema_editor/json_schema_templates"

/**
 * The output scores that can rank run configs or correlate with human ratings.
 *
 * Custom-typed scores are code-eval-only metrics (cost, latency, token counts)
 * with no rating scale, so a higher value is not a better result and the
 * server returns no summary entry for them.
 */
export function correlatable_scores(
  output_scores: EvalOutputScore[] | undefined | null,
): EvalOutputScore[] {
  return (output_scores || []).filter((score) => score.type !== "custom")
}

/**
 * Sort run configs for display: the task's default first, then by the eval's
 * last correlatable score (highest first), then alphabetically by name.
 *
 * Run configs missing a score for that key sort after those that have one.
 */
export function sort_task_run_configs(
  configs: TaskRunConfig[] | null,
  evaluator: Eval | null,
  score_summary: EvalResultSummary | null,
  default_run_config_id: string | null | undefined,
): TaskRunConfig[] {
  if (!configs || !configs.length) return []

  const sortable_scores = correlatable_scores(evaluator?.output_scores)

  return [...configs].sort((a, b) => {
    // Default run config always comes first. The null check matters: run
    // config ids are nullable, so without it an unsaved config would match a
    // task that has no default set.
    if (default_run_config_id != null) {
      if (a.id === default_run_config_id) return -1
      if (b.id === default_run_config_id) return 1
    }

    // If we have scores to rank by, sort by the last one
    if (sortable_scores.length && score_summary?.results) {
      const lastScoreKey = string_to_json_key(
        sortable_scores[sortable_scores.length - 1]!.name,
      )

      const scoreA =
        score_summary.results["" + a.id]?.[lastScoreKey]?.mean_score
      const scoreB =
        score_summary.results["" + b.id]?.[lastScoreKey]?.mean_score

      // If both have scores, sort by score (higher first)
      if (
        scoreA !== null &&
        scoreA !== undefined &&
        scoreB !== null &&
        scoreB !== undefined
      ) {
        return scoreB - scoreA
      }

      // If only one has a score, it comes first
      if (scoreA !== null && scoreA !== undefined) return -1
      if (scoreB !== null && scoreB !== undefined) return 1
    }

    // Fallback to sort by name
    return a.name.localeCompare(b.name)
  })
}
