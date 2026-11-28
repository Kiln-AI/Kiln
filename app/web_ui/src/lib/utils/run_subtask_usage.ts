import type { TaskRun, Trace } from "$lib/types"
import type { UiProperty } from "$lib/ui/property_list"
import { formatLatency } from "$lib/utils/formatters"

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
  // False when a subtask's figure could not be read: its run was not saved
  // (an eval job's) or could not be loaded. Latency is only ever on the saved
  // run; cost and tokens are also on the tool message of newer runs.
  latency_complete: boolean
  cost_complete: boolean
}

// Returns the subtask's saved run, or null when it can't be loaded.
export type SubtaskRunFetcher = (
  reference: SubtaskReference,
) => Promise<TaskRun | null>

type MessageSpend = { cost?: number | null; total_tokens?: number | null }

type SubtaskCall = {
  // The usage on the tool message, already in the run's own usage. Null on
  // older runs and on calls that reported nothing.
  counted: MessageSpend | null
  // Null when the subtask run was not saved or the tool data is malformed.
  reference: SubtaskReference | null
}

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

function reference_key(reference: SubtaskReference): string {
  return `${reference.project_id}:${reference.task_id}:${reference.run_id}`
}

// Only Kiln task tools report usage today, so the other tool messages hold none.
function subtask_calls(trace: Trace | null | undefined): SubtaskCall[] {
  const calls: SubtaskCall[] = []
  for (const message of trace ?? []) {
    if (!("kiln_task_tool_data" in message) || !message.kiln_task_tool_data) {
      continue
    }
    calls.push({
      counted: message.usage ?? null,
      reference: subtask_reference(message.kiln_task_tool_data),
    })
  }
  return calls
}

function empty_usage(): SubtaskUsage {
  return {
    cost: 0,
    tokens: 0,
    latency_ms: 0,
    uncounted_cost: 0,
    uncounted_tokens: 0,
    latency_complete: true,
    cost_complete: true,
  }
}

export function has_subtask_calls(trace: Trace | null | undefined): boolean {
  return subtask_calls(trace).length > 0
}

/** Which Usage panel rows need a subtask run to be fetched. */
export function subtask_fetch_needs(trace: Trace | null | undefined): {
  cost: boolean
  latency: boolean
} {
  const calls = subtask_calls(trace)
  return {
    cost: calls.some((call) => !call.counted && call.reference),
    latency: calls.some((call) => call.reference),
  }
}

/**
 * The subtask figures known from the trace alone: the cost and tokens on the
 * tool messages of newer runs. Shown while the saved subtask runs load.
 */
export function known_subtask_usage(
  trace: Trace | null | undefined,
): SubtaskUsage {
  const total = empty_usage()
  const seen = new Set<string>()
  for (const call of subtask_calls(trace)) {
    if (call.reference) {
      const key = reference_key(call.reference)
      if (seen.has(key)) continue
      seen.add(key)
    }
    if (call.counted) {
      total.cost += call.counted.cost ?? 0
      total.tokens += call.counted.total_tokens ?? 0
    } else {
      total.cost_complete = false
    }
    total.latency_complete = false
  }
  return total
}

/**
 * Sums what the subtasks called in a trace spent.
 *
 * A Kiln task tool message that carries `usage` already has its subtask's cost
 * and tokens in the run's own usage. Older runs have no `usage` there: their
 * subtask's cost and tokens are read from the subtask's saved run and reported
 * as uncounted, for the caller to add to the run's usage. Latency is never in
 * the run's usage, so it always comes from the saved runs.
 *
 * A subtask run referenced more than once is counted once: it ran once.
 */
export async function calculate_subtask_usage(
  trace: Trace | null | undefined,
  fetch_run: SubtaskRunFetcher,
  visited: Set<string> = new Set(),
): Promise<SubtaskUsage> {
  const total = empty_usage()

  for (const { counted, reference } of subtask_calls(trace)) {
    if (reference) {
      const key = reference_key(reference)
      if (visited.has(key)) continue
      visited.add(key)
    }
    if (counted) {
      total.cost += counted.cost ?? 0
      total.tokens += counted.total_tokens ?? 0
    }

    let subtask_run: TaskRun | null = null
    if (reference) {
      try {
        subtask_run = await fetch_run(reference)
      } catch (error) {
        console.warn("Failed to fetch a subtask run for its usage.", {
          ...reference,
          error,
        })
      }
    }
    if (!subtask_run) {
      total.latency_complete = false
      if (!counted) total.cost_complete = false
      continue
    }

    const nested = await calculate_subtask_usage(
      subtask_run.trace,
      fetch_run,
      visited,
    )
    total.latency_ms +=
      (subtask_run.usage?.total_llm_latency_ms ?? 0) + nested.latency_ms
    total.latency_complete &&= nested.latency_complete
    if (!counted) {
      const cost = (subtask_run.usage?.cost ?? 0) + nested.uncounted_cost
      const tokens =
        (subtask_run.usage?.total_tokens ?? 0) + nested.uncounted_tokens
      total.cost += cost
      total.tokens += tokens
      total.uncounted_cost += cost
      total.uncounted_tokens += tokens
      total.cost_complete &&= nested.cost_complete
    }
  }

  return total
}

export type RunUsageTotals = {
  cost: number
  tokens: number
  latency_ms: number
}

/**
 * The run's totals for the Usage panel: its own usage plus the part of its
 * subtasks' usage that the run's usage does not already hold.
 */
export function run_usage_totals(
  run_usage: RunUsageTotals,
  subtask_usage: SubtaskUsage | null,
): RunUsageTotals {
  return {
    cost: run_usage.cost + (subtask_usage?.uncounted_cost ?? 0),
    tokens: run_usage.tokens + (subtask_usage?.uncounted_tokens ?? 0),
    latency_ms: run_usage.latency_ms + (subtask_usage?.latency_ms ?? 0),
  }
}

const COST_INCOMPLETE_TOOLTIP =
  "Leaves out subtasks whose usage was not recorded: runs from an older Kiln version whose subtask runs were not saved or could not be loaded."
const LATENCY_INCOMPLETE_TOOLTIP =
  "Leaves out subtasks whose runs were not saved or could not be loaded, such as the subtasks of an eval run. Their cost and tokens are included."

/**
 * The Usage panel rows. `loading` names the rows still waiting on subtask
 * runs; the other rows show what is already known.
 */
export function usage_properties(
  run_usage: RunUsageTotals,
  subtasks: SubtaskUsage | null,
  loading: { cost: boolean; latency: boolean },
): UiProperty[] {
  const totals = run_usage_totals(run_usage, subtasks)
  const cost_incomplete = subtasks !== null && !subtasks.cost_complete
  const latency_incomplete = subtasks !== null && !subtasks.latency_complete
  const rows: UiProperty[] = []

  const add_total = (
    name: string,
    value: number,
    format: (value: number) => string | number,
    is_loading: boolean,
    incomplete: boolean,
    tooltip: string,
  ) => {
    if (is_loading) {
      rows.push({ name, value: "Loading..." })
    } else if (value > 0) {
      rows.push({
        name,
        value: format(value),
        ...(incomplete ? { warn_icon: true, tooltip } : {}),
      })
    }
  }
  const add_subtasks = (
    name: string,
    value: number,
    format: (value: number) => string | number,
    is_loading: boolean,
  ) => {
    if (is_loading) {
      rows.push({ name, value: "Loading..." })
    } else if (value > 0) {
      rows.push({ name, value: format(value) })
    }
  }
  const dollars = (value: number) => `$${value.toFixed(6)}`
  const count = (value: number) => value

  add_total(
    "Total Cost",
    totals.cost,
    dollars,
    loading.cost,
    cost_incomplete,
    COST_INCOMPLETE_TOOLTIP,
  )
  add_subtasks("Subtasks Cost", subtasks?.cost ?? 0, dollars, loading.cost)
  add_total(
    "Total Tokens",
    totals.tokens,
    count,
    loading.cost,
    cost_incomplete,
    COST_INCOMPLETE_TOOLTIP,
  )
  add_subtasks("Subtasks Tokens", subtasks?.tokens ?? 0, count, loading.cost)
  add_total(
    "Total Latency",
    totals.latency_ms,
    formatLatency,
    loading.latency,
    latency_incomplete,
    LATENCY_INCOMPLETE_TOOLTIP,
  )
  add_subtasks(
    "Subtasks Latency",
    subtasks?.latency_ms ?? 0,
    formatLatency,
    loading.latency,
  )
  return rows
}
