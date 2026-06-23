import { describe, it, expect } from "vitest"
import {
  compute_forkable_run_ids,
  fork_target_from_assistant_block,
} from "./fork_helpers"
import type { Trace, TraceMessage, RunChainEntry } from "$lib/types"

function userMsg(content: string): TraceMessage {
  return { role: "user", content } as TraceMessage
}
function assistantMsg(content: string): TraceMessage {
  return { role: "assistant", content } as TraceMessage
}
function systemMsg(content: string): TraceMessage {
  return { role: "system", content } as TraceMessage
}

describe("compute_forkable_run_ids", () => {
  it("maps each non-turn-1 user message to its chain entry run id for a clean 3-turn chain", () => {
    const trace: Trace = [
      systemMsg("s"),
      userMsg("u1"),
      assistantMsg("a1"),
      userMsg("u2"),
      assistantMsg("a2"),
      userMsg("u3"),
      assistantMsg("a3"),
    ]
    const chain: RunChainEntry[] = [
      { run_id: "run-1", turn_index: 1 },
      { run_id: "run-2", turn_index: 2 },
      { run_id: "run-3", turn_index: 3 },
    ]
    const result = compute_forkable_run_ids(trace, chain)
    // The fork affordance sits on the assistant message that precedes each
    // forkable user turn: turn 2 (run-2) maps onto assistant a1 (index 2) and
    // turn 3 (run-3) maps onto assistant a2 (index 4). The leaf's trailing
    // assistant a3 (index 6) is not forkable.
    expect(result).toEqual([null, null, "run-2", null, "run-3", null, null])
  })

  it("suffix-aligns a broken chain — only the trailing user blocks are mapped", () => {
    const trace: Trace = [
      systemMsg("s"),
      userMsg("u1"),
      assistantMsg("a1"),
      userMsg("u2"),
      assistantMsg("a2"),
      userMsg("u3"),
      assistantMsg("a3"),
    ]
    // The chain is broken above turn 3, so we only have the leaf.
    const chain: RunChainEntry[] = [{ run_id: "run-3", turn_index: 3 }]
    const result = compute_forkable_run_ids(trace, chain)
    // run-3 maps onto the assistant (index 4) preceding the leaf user turn.
    expect(result).toEqual([null, null, null, null, "run-3", null, null])
  })

  it("returns all nulls when chain is empty", () => {
    const trace: Trace = [systemMsg("s"), userMsg("u1"), assistantMsg("a1")]
    const result = compute_forkable_run_ids(trace, [])
    expect(result).toEqual([null, null, null])
  })

  it("returns all nulls for a trace with no user messages", () => {
    const trace: Trace = [systemMsg("s"), assistantMsg("a1")]
    const chain: RunChainEntry[] = [{ run_id: "run-x", turn_index: 1 }]
    const result = compute_forkable_run_ids(trace, chain)
    expect(result).toEqual([null, null])
  })

  it("skips turn 1 even when chain includes it (single-turn chain)", () => {
    const trace: Trace = [systemMsg("s"), userMsg("u1"), assistantMsg("a1")]
    const chain: RunChainEntry[] = [{ run_id: "run-1", turn_index: 1 }]
    const result = compute_forkable_run_ids(trace, chain)
    expect(result).toEqual([null, null, null])
  })
})

describe("fork_target_from_assistant_block", () => {
  const chain: RunChainEntry[] = [
    { run_id: "run-1", turn_index: 1 },
    { run_id: "run-2", turn_index: 2 },
    { run_id: "run-3", turn_index: 3 },
  ]

  it("returns the parent run id and an empty prefill for an interior assistant click", () => {
    // Forking on turn 1's assistant (index 2) creates a new turn 2.
    const target = fork_target_from_assistant_block("run-2", 2, chain)
    expect(target).not.toBeNull()
    expect(target?.turn_index).toBe(2)
    expect(target?.parent_run_id).toBe("run-1")
    // Truncates just after the clicked assistant message.
    expect(target?.trace_index).toBe(3)
    expect(target?.prefill).toBe("")
  })

  it("returns null when the mapped turn is turn 1 (no parent exists)", () => {
    const target = fork_target_from_assistant_block("run-1", 0, chain)
    expect(target).toBeNull()
  })

  it("returns the leaf's parent when the assistant before the leaf turn is clicked", () => {
    // Forking on turn 2's assistant (index 4) creates a new turn 3.
    const target = fork_target_from_assistant_block("run-3", 4, chain)
    expect(target?.parent_run_id).toBe("run-2")
    expect(target?.turn_index).toBe(3)
    expect(target?.trace_index).toBe(5)
    expect(target?.prefill).toBe("")
  })

  it("returns null when the run id is not found in chain", () => {
    const target = fork_target_from_assistant_block("unknown", 2, chain)
    expect(target).toBeNull()
  })
})
