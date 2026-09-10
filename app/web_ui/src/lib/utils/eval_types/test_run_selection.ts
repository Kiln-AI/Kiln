import type { TaskRunOutput } from "$lib/types"

/**
 * Pick the dataset run the Test Judge pane should start on.
 *
 * Judges that read the execution trace (step_count_check, tool_call_check, and
 * any check whose output source points at the trace) tell the user nothing
 * useful about a run without one. A missing trace skips with missing_trace; an
 * empty trace is worse, since `[]` is truthy in JS and gets sent as a real
 * trace, then scored as zero steps / zero tool calls -- a misleading result
 * rather than a skip. So prefer a run that has real trace messages.
 *
 * Runs arrive newest-first and that order is preserved, so this picks the most
 * recent run with a trace, falling back to the most recent run overall.
 */
export function select_default_test_run(
  available_runs: TaskRunOutput[],
): TaskRunOutput | null {
  const run_with_trace = available_runs.find((run) => !!run.trace?.length)
  return run_with_trace ?? available_runs[0] ?? null
}
