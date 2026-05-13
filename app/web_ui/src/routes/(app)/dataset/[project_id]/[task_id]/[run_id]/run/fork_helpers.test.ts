import { describe, it, expect } from "vitest"
import {
  compute_forkable_run_ids,
  fork_target_from_user_block,
  content_string_from_user_message,
} from "./fork_helpers"
import type { Trace, TraceMessage, TaskRunAncestor } from "$lib/types"

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
  it("maps each non-turn-1 user message to its ancestor run id for a clean 3-turn chain", () => {
    const trace: Trace = [
      systemMsg("s"),
      userMsg("u1"),
      assistantMsg("a1"),
      userMsg("u2"),
      assistantMsg("a2"),
      userMsg("u3"),
      assistantMsg("a3"),
    ]
    const ancestors: TaskRunAncestor[] = [
      { run_id: "run-1", turn_index: 1 },
      { run_id: "run-2", turn_index: 2 },
      { run_id: "run-3", turn_index: 3 },
    ]
    const result = compute_forkable_run_ids(trace, ancestors)
    // Indices: 0 system, 1 user(turn1, not forkable), 2 assistant, 3 user(turn2),
    // 4 assistant, 5 user(turn3 leaf), 6 assistant.
    expect(result).toEqual([null, null, null, "run-2", null, "run-3", null])
  })

  it("suffix-aligns a broken-chain ancestor list — only the trailing user blocks are mapped", () => {
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
    const ancestors: TaskRunAncestor[] = [{ run_id: "run-3", turn_index: 3 }]
    const result = compute_forkable_run_ids(trace, ancestors)
    expect(result).toEqual([null, null, null, null, null, "run-3", null])
  })

  it("returns all nulls when ancestors is empty", () => {
    const trace: Trace = [systemMsg("s"), userMsg("u1"), assistantMsg("a1")]
    const result = compute_forkable_run_ids(trace, [])
    expect(result).toEqual([null, null, null])
  })

  it("returns all nulls for a trace with no user messages", () => {
    const trace: Trace = [systemMsg("s"), assistantMsg("a1")]
    const ancestors: TaskRunAncestor[] = [{ run_id: "run-x", turn_index: 1 }]
    const result = compute_forkable_run_ids(trace, ancestors)
    expect(result).toEqual([null, null])
  })

  it("skips turn 1 even when ancestors include it (single-turn chain)", () => {
    const trace: Trace = [systemMsg("s"), userMsg("u1"), assistantMsg("a1")]
    const ancestors: TaskRunAncestor[] = [{ run_id: "run-1", turn_index: 1 }]
    const result = compute_forkable_run_ids(trace, ancestors)
    expect(result).toEqual([null, null, null])
  })
})

describe("fork_target_from_user_block", () => {
  const trace: Trace = [
    systemMsg("s"),
    userMsg("hello"),
    assistantMsg("hi"),
    userMsg("how are you?"),
    assistantMsg("good"),
    userMsg("ok bye"),
    assistantMsg("bye"),
  ]
  const ancestors: TaskRunAncestor[] = [
    { run_id: "run-1", turn_index: 1 },
    { run_id: "run-2", turn_index: 2 },
    { run_id: "run-3", turn_index: 3 },
  ]

  it("returns the parent run id and prefill for an interior turn click", () => {
    const target = fork_target_from_user_block("run-2", 3, trace, ancestors)
    expect(target).not.toBeNull()
    expect(target?.turn_index).toBe(2)
    expect(target?.parent_run_id).toBe("run-1")
    expect(target?.trace_index).toBe(3)
    expect(target?.prefill).toBe("how are you?")
  })

  it("returns null when the forked turn is turn 1 (no parent exists)", () => {
    const target = fork_target_from_user_block("run-1", 1, trace, ancestors)
    expect(target).toBeNull()
  })

  it("returns the leaf's parent when the leaf user block is clicked", () => {
    const target = fork_target_from_user_block("run-3", 5, trace, ancestors)
    expect(target?.parent_run_id).toBe("run-2")
    expect(target?.turn_index).toBe(3)
    expect(target?.prefill).toBe("ok bye")
  })

  it("returns null when the run id is not found in ancestors", () => {
    const target = fork_target_from_user_block("unknown", 3, trace, ancestors)
    expect(target).toBeNull()
  })
})

describe("content_string_from_user_message", () => {
  it("returns the string content of a user message", () => {
    expect(content_string_from_user_message(userMsg("hi"))).toBe("hi")
  })
  it("returns an empty string for non-user messages", () => {
    expect(content_string_from_user_message(assistantMsg("hi"))).toBe("")
  })
  it("returns an empty string when the message is undefined", () => {
    expect(content_string_from_user_message(undefined)).toBe("")
  })
  it("returns an empty string when content is not a plain string (e.g. structured parts)", () => {
    const msg = {
      role: "user",
      content: [{ type: "text", text: "hi" }],
    } as unknown as TraceMessage
    expect(content_string_from_user_message(msg)).toBe("")
  })
})
