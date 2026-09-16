import type { Trace, RunChainEntry } from "$lib/types"

export type ForkTarget = {
  turn_index: number
  parent_run_id: string | null
  trace_index: number
  prefill: string
}

// Compute, for each trace index, the run id used to fork at that point. The
// fork affordance lives on the assistant message that ends a turn (forking
// "after" the assistant continues the conversation down a new branch). For a
// forkable user turn K (K >= 2), we map the run id of turn K onto the
// assistant message immediately preceding turn K's user message (i.e. turn
// K-1's final assistant message). The result has the same length as `trace`;
// every other index is null. Turn 1 is not forkable (no parent exists), so the
// leaf turn's trailing assistant message is never mapped.
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
    const user_idx = user_trace_indices[offset + k]
    if (user_idx === undefined) continue
    // Place the fork affordance on the assistant message immediately
    // preceding this user turn (the previous turn's final assistant
    // response), not on the user message itself.
    const assistant_idx = user_idx - 1
    if (assistant_idx >= 0 && trace[assistant_idx]?.role === "assistant") {
      result[assistant_idx] = entry.run_id
    }
  }
  return result
}

// Look up the data needed to open a fork composer for a clicked assistant
// block. `run_id` is the run mapped onto that assistant message by
// compute_forkable_run_ids — the turn that the new branch will create
// (turn K). Forking continues the conversation after the clicked assistant
// message with a fresh (un-seeded) next message, so prefill is always empty.
// Returns null if the click target can't be resolved (defensive — the trace
// component only renders the fork button when a chain entry was mapped).
export function fork_target_from_assistant_block(
  run_id: string,
  trace_index: number,
  chain: RunChainEntry[],
): ForkTarget | null {
  const this_turn = chain.find((c) => c.run_id === run_id)
  if (!this_turn) return null
  // The mapped run is always turn 2+ (turn 1 is filtered out upstream);
  // guard defensively anyway.
  if (this_turn.turn_index <= 1) return null
  const parent = chain.find((c) => c.turn_index === this_turn.turn_index - 1)
  return {
    turn_index: this_turn.turn_index,
    parent_run_id: parent?.run_id ?? null,
    // Truncate the displayed transcript just after the clicked assistant
    // message, so it stays visible while everything that followed is hidden.
    trace_index: trace_index + 1,
    // No seeding: forking from an assistant message starts a brand-new turn.
    prefill: "",
  }
}
