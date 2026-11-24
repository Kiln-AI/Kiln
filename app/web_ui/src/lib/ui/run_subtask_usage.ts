import type { TaskRun, Trace } from "$lib/types"

export type SubtaskReference = {
  project_id: string
  task_id: string
  run_id: string
}

export type SubtaskUsage = {
  // What the run's subtasks (Kiln task tool calls) spent, nested ones included.
  cost: number
  tokens: number
  latency_ms: number
  // The part of cost and tokens the run's own usage does not already hold.
  uncounted_cost: number
  uncounted_tokens: number
}

// Returns the subtask's saved run, or null when it can't be loaded.
export type SubtaskRunFetcher = (
  reference: SubtaskReference,
) => Promise<TaskRun | null>

// A subtask run that was never saved (an eval job's) has this in place of its id.
const UNSAVED_RUN_ID = "None"

function subtask_reference(
  kiln_task_tool_data: string,
): SubtaskReference | null {
  const [project_id, , task_id, run_id] = kiln_task_tool_data.split(":::")
  if (!project_id || !task_id || !run_id || run_id === UNSAVED_RUN_ID) {
    return null
  }
  return { project_id, task_id, run_id }
}

export function has_subtask_calls(trace: Trace | null | undefined): boolean {
  return (trace ?? []).some(
    (message) =>
      "kiln_task_tool_data" in message && message.kiln_task_tool_data,
  )
}

/**
 * Sums what the subtasks called in a trace spent.
 *
 * A Kiln task tool message that carries `usage` already has its subtask's cost
 * and tokens in the run's own usage. Older runs have no `usage` there: their
 * subtask's cost and tokens are read from the subtask's saved run and reported
 * as uncounted, for the caller to add to the run's usage. Latency is never in
 * the run's usage, so it always comes from the saved runs.
 */
export async function calculate_subtask_usage(
  trace: Trace | null | undefined,
  fetch_run: SubtaskRunFetcher,
  visited: Set<string> = new Set(),
): Promise<SubtaskUsage> {
  const total: SubtaskUsage = {
    cost: 0,
    tokens: 0,
    latency_ms: 0,
    uncounted_cost: 0,
    uncounted_tokens: 0,
  }

  for (const message of trace ?? []) {
    if (!("kiln_task_tool_data" in message) || !message.kiln_task_tool_data) {
      continue
    }
    const counted_usage = message.usage
    if (counted_usage) {
      total.cost += counted_usage.cost ?? 0
      total.tokens += counted_usage.total_tokens ?? 0
    }

    const reference = subtask_reference(message.kiln_task_tool_data)
    if (!reference) continue
    const key = `${reference.project_id}:${reference.task_id}:${reference.run_id}`
    if (visited.has(key)) continue
    visited.add(key)

    let subtask_run: TaskRun | null = null
    try {
      subtask_run = await fetch_run(reference)
    } catch (error) {
      console.warn(
        "Failed to fetch subtask usage, continuing on error as subtask run may have been deleted.",
        { ...reference, error },
      )
    }
    if (!subtask_run) continue

    const nested = await calculate_subtask_usage(
      subtask_run.trace,
      fetch_run,
      visited,
    )
    total.latency_ms +=
      (subtask_run.usage?.total_llm_latency_ms ?? 0) + nested.latency_ms
    if (!counted_usage) {
      const cost = (subtask_run.usage?.cost ?? 0) + nested.uncounted_cost
      const tokens =
        (subtask_run.usage?.total_tokens ?? 0) + nested.uncounted_tokens
      total.cost += cost
      total.tokens += tokens
      total.uncounted_cost += cost
      total.uncounted_tokens += tokens
    }
  }

  return total
}
