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
 * Status of the few-shot example fetching process.
 */
export type FewShotStatus =
  | "loading"
  | "auto_selected" // A 5-star sample was found and auto-selected
  | "user_select" // Samples exist but none are 5-star, user must select
  | "manual_entry" // No samples exist, user must enter manually

/**
 * Result of fetching few-shot examples from the dataset.
 */
export type FewShotFetchResult = {
  status: Exclude<FewShotStatus, "loading">
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
 * 1. If a 5-star rated sample exists, auto-select it
 * 2. If samples exist but none are 5-star, return them for user selection
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
      status: "manual_entry",
      selected_example: null,
      available_runs: [],
    }
  }

  // First, look for 5-star rated samples
  const five_star_runs = runs.filter(is_five_star_rated)
  if (five_star_runs.length > 0) {
    // Sort by ID for consistency (pick the first one)
    five_star_runs.sort((a, b) => (a.id ?? "").localeCompare(b.id ?? ""))
    const selected = five_star_runs[0]
    return {
      status: "auto_selected",
      selected_example: task_run_to_example(selected),
      available_runs: runs,
    }
  }

  // No 5-star samples, but samples exist - user must select
  // Sort runs by rating (highest first), then by whether they have repaired output
  const sorted_runs = [...runs].sort((a, b) => {
    // Repaired outputs first
    if (a.repaired_output && !b.repaired_output) return -1
    if (!a.repaired_output && b.repaired_output) return 1

    // Then by rating value
    const a_rating = a.output?.rating?.value ?? 0
    const b_rating = b.output?.rating?.value ?? 0
    if (b_rating !== a_rating) return b_rating - a_rating

    // Finally by ID for stability
    return (a.id ?? "").localeCompare(b.id ?? "")
  })

  return {
    status: "user_select",
    selected_example: null,
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
