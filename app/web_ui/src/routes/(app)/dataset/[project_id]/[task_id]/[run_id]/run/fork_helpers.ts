import type { Trace, TraceMessage, TaskRunAncestor } from "$lib/types"

export type ForkTarget = {
  turn_index: number
  parent_run_id: string | null
  trace_index: number
  prefill: string
}

// Extract a plain-text representation of a user message's content. Mirrors
// the trace component's "content_from_message" for the simple string case.
// We don't try to flatten structured content (images/audio) — fork prefill
// only supports plaintext, matching the existing append composer.
//
// Structured-content forks (e.g. user messages whose content is a list of
// text + image parts) are explicitly out of scope for v1; see
// specs/projects/multiturn_trace_forking/functional_spec.md "Out of Scope"
// and "Open / Deferred". Returning "" here means the composer opens with
// an empty textarea — the user can still type a new prompt and Send, but
// the original structured content is not represented in the prefill. When
// the trace editor lands, this is the function to upgrade.
export function content_string_from_user_message(
  message: TraceMessage | undefined,
): string {
  if (!message) return ""
  if (message.role !== "user") return ""
  if (typeof message.content === "string") {
    return message.content
  }
  return ""
}

// Compute, for each trace index, the run id of the user turn at that index
// (or null when no ancestor maps to it, or when the user message at that
// index is turn 1 — turn 1 is not forkable per the functional spec). The
// result has the same length as `trace`. Non-user messages and turn 1's
// user message map to null.
export function compute_forkable_run_ids(
  trace: Trace,
  ancestors: TaskRunAncestor[],
): (string | null)[] {
  const result: (string | null)[] = trace.map(() => null)
  const user_trace_indices: number[] = []
  for (let i = 0; i < trace.length; i++) {
    if (trace[i].role === "user") {
      user_trace_indices.push(i)
    }
  }
  const total_turns = user_trace_indices.length
  if (total_turns === 0 || ancestors.length === 0) {
    return result
  }
  // Suffix-align the ancestor list against the user messages: the last
  // ancestor (the leaf) corresponds to the last user message.
  const offset = total_turns - ancestors.length
  for (let k = 0; k < ancestors.length; k++) {
    const ancestor = ancestors[k]
    if (ancestor.turn_index === 1) continue // turn 1 is not forkable
    const trace_idx = user_trace_indices[offset + k]
    if (trace_idx !== undefined) {
      result[trace_idx] = ancestor.run_id
    }
  }
  return result
}

// Look up the data needed to open a fork composer for a clicked user
// block. Returns null if the click target can't be resolved (defensive —
// the trace component only renders the fork button when an ancestor was
// already mapped, so this should not normally happen).
export function fork_target_from_user_block(
  run_id: string,
  trace_index: number,
  trace: Trace,
  ancestors: TaskRunAncestor[],
): ForkTarget | null {
  const this_turn = ancestors.find((a) => a.run_id === run_id)
  if (!this_turn) return null
  // Turn 1 is not forkable (no parent exists). The trace component already
  // filters this out via compute_forkable_run_ids; returning null here is a
  // defensive guard against being called on turn 1 directly.
  if (this_turn.turn_index <= 1) return null
  const parent = ancestors.find(
    (a) => a.turn_index === this_turn.turn_index - 1,
  )
  return {
    turn_index: this_turn.turn_index,
    parent_run_id: parent?.run_id ?? null,
    trace_index,
    prefill: content_string_from_user_message(trace[trace_index]),
  }
}
