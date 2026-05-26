import type { Trace, TraceMessage, RunChainEntry } from "$lib/types"

export type ForkTarget = {
  turn_index: number
  parent_run_id: string | null
  trace_index: number
  prefill: string
}

// Extract a plain-text representation of a user message's content. Mirrors
// the trace component's "content_from_message" for the simple string case.
// Structured content (image / audio parts) is out of scope for v1 fork
// prefill: returning "" means the composer opens with an empty textarea and
// the user retypes the prompt. Upgrade this when the trace editor lands.
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
// (or null when no chain entry maps to it, or when the user message at that
// index is turn 1 — turn 1 is not forkable per the functional spec). The
// result has the same length as `trace`. Non-user messages and turn 1's
// user message map to null.
export function compute_forkable_run_ids(
  trace: Trace,
  chain: RunChainEntry[],
): (string | null)[] {
  const result: (string | null)[] = trace.map(() => null)
  const user_trace_indices: number[] = []
  for (let i = 0; i < trace.length; i++) {
    if (trace[i].role === "user") {
      user_trace_indices.push(i)
    }
  }
  const total_turns = user_trace_indices.length
  if (total_turns === 0 || chain.length === 0) {
    return result
  }
  // Suffix-align the chain against the user messages: the last entry (the
  // leaf) corresponds to the last user message. A negative offset would
  // mean the server returned more chain entries than the trace can support
  // — caller guards against that by capping chain length to turn_count.
  const offset = total_turns - chain.length
  if (offset < 0) return result
  for (let k = 0; k < chain.length; k++) {
    const entry = chain[k]
    if (entry.turn_index === 1) continue // turn 1 is not forkable
    const trace_idx = user_trace_indices[offset + k]
    if (trace_idx !== undefined) {
      result[trace_idx] = entry.run_id
    }
  }
  return result
}

// Look up the data needed to open a fork composer for a clicked user
// block. Returns null if the click target can't be resolved (defensive —
// the trace component only renders the fork button when a chain entry was
// already mapped, so this should not normally happen).
export function fork_target_from_user_block(
  run_id: string,
  trace_index: number,
  trace: Trace,
  chain: RunChainEntry[],
): ForkTarget | null {
  const this_turn = chain.find((c) => c.run_id === run_id)
  if (!this_turn) return null
  // Turn 1 is not forkable (no parent exists). The trace component already
  // filters this out via compute_forkable_run_ids; returning null here is a
  // defensive guard against being called on turn 1 directly.
  if (this_turn.turn_index <= 1) return null
  const parent = chain.find((c) => c.turn_index === this_turn.turn_index - 1)
  return {
    turn_index: this_turn.turn_index,
    parent_run_id: parent?.run_id ?? null,
    trace_index,
    prefill: content_string_from_user_message(trace[trace_index]),
  }
}
