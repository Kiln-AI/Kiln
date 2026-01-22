import { client } from "$lib/api_client"
import type { TaskRun } from "$lib/types"

/**
 * A few-shot example consisting of an input/output pair.
 */
export type FewShotExample = {
  input: string
  output: string
}

/**
 * How the example was auto-selected (data label, not UI state).
 */
export type AutoSelectType = "highly_rated" | "most_recent" | null

/**
 * Result of fetching few-shot examples from the dataset.
 */
export type FewShotFetchResult = {
  auto_select_type: AutoSelectType
  selected_example: FewShotExample | null
  available_runs: TaskRun[]
}

/**
 * Checks if a task run has a 5-star rating.
 */
function is_five_star_rated(run: TaskRun): boolean {
  const rating = run.output?.rating
  if (!rating) return false
  return rating.type === "five_star" && rating.value === 5
}

/**
 * Extract the output string from a task run, preferring repaired output.
 */
function get_output_string(run: TaskRun): string {
  if (run.repaired_output?.output) {
    return run.repaired_output.output
  }
  return run.output?.output ?? ""
}

/**
 * Converts a TaskRun to a FewShotExample.
 */
export function task_run_to_example(run: TaskRun): FewShotExample {
  return {
    input: run.input ?? "",
    output: get_output_string(run),
  }
}

/**
 * Fetches task runs and determines the few-shot selection status.
 *
 * Priority:
 * 1. If a 5-star rated sample exists, auto-select it (confident)
 * 2. If samples exist but none are 5-star, auto-select the most recent
 * 3. If no samples exist, indicate manual entry is needed
 *
 * @throws Error if fetching fails
 */
export async function fetch_few_shot_candidates(
  project_id: string,
  task_id: string,
): Promise<FewShotFetchResult> {
  const { data: runs, error } = await client.GET(
    "/api/projects/{project_id}/tasks/{task_id}/runs",
    {
      params: {
        path: { project_id, task_id },
      },
    },
  )

  if (error) {
    throw new Error(
      typeof error === "string"
        ? error
        : (error as { detail?: string }).detail ?? "Failed to fetch runs",
    )
  }

  if (!runs || runs.length === 0) {
    return {
      auto_select_type: null,
      selected_example: null,
      available_runs: [],
    }
  }

  // Sort runs by recency (most recent first)
  const sorted_runs = [...runs].sort((a, b) => {
    const a_date = a.created_at ? new Date(a.created_at).getTime() : 0
    const b_date = b.created_at ? new Date(b.created_at).getTime() : 0
    return b_date - a_date
  })

  // First, look for 5-star rated samples (most recent 5-star)
  const five_star_run = sorted_runs.find(is_five_star_rated)
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

/**
 * Builds a task prompt with instruction, requirements, and optional few-shot examples.
 * Uses the backend prompt builder for consistent formatting.
 */
export async function build_prompt_with_few_shot(
  project_id: string,
  task_id: string,
  examples: FewShotExample[],
): Promise<string> {
  const { data, error } = await client.POST(
    "/api/projects/{project_id}/tasks/{task_id}/build_prompt_with_examples",
    {
      params: {
        path: { project_id, task_id },
      },
      body: {
        examples: examples,
      },
    },
  )

  if (error) {
    throw new Error(
      typeof error === "string"
        ? error
        : (error as { detail?: string }).detail ?? "Failed to build prompt",
    )
  }

  return data?.prompt ?? ""
}
