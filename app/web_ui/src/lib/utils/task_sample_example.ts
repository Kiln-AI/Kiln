import { client } from "$lib/api_client"
import type {
  RunSummary,
  TaskOutputRating,
  TaskRun,
  TaskRunOutput,
} from "$lib/types"

/**
 * A task sample example consisting of an input/output pair.
 */
export type TaskSampleExample = {
  input: string
  output: string
}

/**
 * How the example was auto-selected (data label, not UI state).
 */
export type AutoSelectType = "highly_rated" | "most_recent"

/**
 * Result of fetching task sample examples from the dataset.
 */
export type TaskSampleFetchResult = {
  auto_select_type: AutoSelectType | null
  selected_example: TaskSampleExample | null
  available_runs: TaskRun[]
}

/** Whether a rating is a five-star rating with the top score of 5. */
export function is_five_star_rating(
  rating: Pick<TaskOutputRating, "type" | "value"> | null | undefined,
): boolean {
  if (!rating) return false
  return rating.type === "five_star" && rating.value === 5
}

/**
 * Extract the output string from a task run, preferring repaired output.
 */
function get_output_string(run: TaskRun | TaskRunOutput): string {
  if (run.repaired_output?.output) {
    return run.repaired_output.output
  }
  return run.output?.output ?? ""
}

/**
 * Converts a TaskRun to a TaskSampleExample.
 */
export function task_run_to_example(
  run: TaskRun | TaskRunOutput,
): TaskSampleExample {
  return {
    input: run.input ?? "",
    output: get_output_string(run),
  }
}

/** The most candidate runs `fetch_task_sample_candidates` returns. */
export const TASK_SAMPLE_CANDIDATE_LIMIT = 100

/**
 * Fetches up to `TASK_SAMPLE_CANDIDATE_LIMIT` candidate runs and determines the
 * task sample selection status.
 *
 * The candidates are the task's newest runs. With a `candidate_filter`, they are
 * the newest runs the filter keeps, chosen from the task's run summaries, so
 * older matching runs are found even when every recent run is filtered out.
 *
 * Priority over the candidates:
 * 1. If a 5-star rated sample exists, auto-select it (confident)
 * 2. If samples exist but none are 5-star, auto-select the most recent
 * 3. If no samples exist, indicate manual entry is needed
 *
 * @throws Error if fetching fails
 */
export async function fetch_task_sample_candidates(
  project_id: string,
  task_id: string,
  candidate_filter?: (run: RunSummary) => boolean,
): Promise<TaskSampleFetchResult> {
  const candidates = candidate_filter
    ? await fetch_filtered_candidate_runs(project_id, task_id, candidate_filter)
    : await fetch_newest_runs(project_id, task_id)
  if (candidates.length === 0) {
    return {
      auto_select_type: null,
      selected_example: null,
      available_runs: [],
    }
  }

  const sorted_runs = newest_first(candidates)

  // First, look for 5-star rated samples (most recent 5-star)
  const five_star_run = sorted_runs.find((run) =>
    is_five_star_rating(run.output?.rating),
  )
  if (five_star_run) {
    return {
      auto_select_type: "highly_rated",
      selected_example: task_run_to_example(five_star_run),
      available_runs: sorted_runs,
    }
  }

  // No 5-star samples, but samples exist - auto-select the most recent
  const most_recent = sorted_runs[0]

  return {
    auto_select_type: "most_recent",
    selected_example: task_run_to_example(most_recent),
    available_runs: sorted_runs,
  }
}

async function fetch_filtered_candidate_runs(
  project_id: string,
  task_id: string,
  candidate_filter: (run: RunSummary) => boolean,
): Promise<TaskRun[]> {
  const { data: summaries, error } = await client.GET(
    "/api/projects/{project_id}/tasks/{task_id}/runs_summaries",
    { params: { path: { project_id, task_id } } },
  )
  if (error) {
    throw request_error(error, "Failed to fetch run summaries")
  }
  const run_ids = newest_first((summaries ?? []).filter(candidate_filter))
    .slice(0, TASK_SAMPLE_CANDIDATE_LIMIT)
    .flatMap((summary) => (summary.id ? [summary.id] : []))
  // An empty `run_ids` is dropped from the query, so the request would not filter.
  if (run_ids.length === 0) {
    return []
  }
  return fetch_newest_runs(project_id, task_id, run_ids)
}

async function fetch_newest_runs(
  project_id: string,
  task_id: string,
  run_ids?: string[],
): Promise<TaskRun[]> {
  const { data: runs, error } = await client.GET(
    "/api/projects/{project_id}/tasks/{task_id}/runs",
    {
      params: {
        path: { project_id, task_id },
        query: {
          limit: TASK_SAMPLE_CANDIDATE_LIMIT,
          ...(run_ids ? { run_ids } : {}),
        },
      },
    },
  )
  if (error) {
    throw request_error(error, "Failed to fetch runs")
  }
  return runs ?? []
}

function request_error(error: unknown, fallback: string): Error {
  return new Error(
    typeof error === "string"
      ? error
      : (error as { message?: string }).message ?? fallback,
  )
}

function newest_first<T extends { created_at?: string | null }>(
  items: T[],
): T[] {
  const time = (item: T) =>
    item.created_at ? new Date(item.created_at).getTime() : 0
  return [...items].sort((a, b) => time(b) - time(a))
}
