import { describe, expect, it } from "vitest"
import { traceIdForNextChatRequest } from "./streaming_chat"
import {
  hydrateSessionFromSnapshot,
  type ChatSessionSnapshot,
} from "./session_messages"

function snap(
  id: string,
  trace: ChatSessionSnapshot["task_run"]["trace"],
): ChatSessionSnapshot {
  return { id, task_run: { trace } }
}

describe("hydrateSessionFromSnapshot", () => {
  it("maps user and assistant trace messages and sets traceId on last assistant", () => {
    const { messages, continuationTraceId } = hydrateSessionFromSnapshot(
      snap("trace-sess", [
        { role: "user", content: "Hello" },
        { role: "assistant", content: "Hi there" },
      ]),
    )
    expect(messages).toHaveLength(2)
    expect(messages[0].role).toBe("user")
    expect(messages[0].content).toBe("Hello")
    expect(messages[1].role).toBe("assistant")
    expect(messages[1].parts?.[0]).toEqual({ type: "text", text: "Hi there" })
    expect(messages[1].traceId).toBe("trace-sess")
    expect(traceIdForNextChatRequest(messages)).toBe("trace-sess")
    expect(continuationTraceId).toBe("trace-sess")
  })

  it("maps reasoning_content into a reasoning part", () => {
    const { messages } = hydrateSessionFromSnapshot(
      snap("t2", [
        {
          role: "assistant",
          content: "answer",
          reasoning_content: "think",
        },
      ]),
    )
    expect(messages[0].parts).toEqual([
      { type: "reasoning", reasoning: "think" },
      { type: "text", text: "answer" },
    ])
  })

  it("maps tool_calls and tool messages", () => {
    const { messages } = hydrateSessionFromSnapshot(
      snap("t3", [
        {
          role: "assistant",
          tool_calls: [
            {
              id: "tc1",
              type: "function",
              function: { name: "math__add", arguments: '{"a":1,"b":2}' },
            },
          ],
        },
        { role: "tool", tool_call_id: "tc1", content: "3" },
      ]),
    )
    expect(messages).toHaveLength(1)
    const parts = messages[0].parts!
    expect(parts[0]).toMatchObject({
      type: "tool-math__add",
      toolCallId: "tc1",
      toolName: "math__add",
      input: { a: 1, b: 2 },
      output: "3",
    })
  })

  it("skips system and developer messages", () => {
    const { messages } = hydrateSessionFromSnapshot(
      snap("x", [
        { role: "system", content: "You are helpful" },
        { role: "developer", content: "internal" },
        { role: "user", content: "ok" },
      ]),
    )
    expect(messages.map((m) => m.role)).toEqual(["user"])
  })

  it("skips tool messages from the trace (folded into assistant parts)", () => {
    const { messages } = hydrateSessionFromSnapshot(
      snap("x", [
        { role: "tool", tool_call_id: "orphan", content: "result" },
        { role: "user", content: "ok" },
      ]),
    )
    expect(messages.map((m) => m.role)).toEqual(["user"])
  })

  it("continuationTraceId allows submit when trace ends on user", () => {
    const { messages, continuationTraceId } = hydrateSessionFromSnapshot(
      snap("sess-u", [{ role: "user", content: "Waiting" }]),
    )
    expect(traceIdForNextChatRequest(messages)).toBeUndefined()
    expect(continuationTraceId).toBe("sess-u")
  })

  it("handles empty trace", () => {
    const { messages, continuationTraceId } = hydrateSessionFromSnapshot(
      snap("empty", []),
    )
    expect(messages).toHaveLength(0)
    expect(continuationTraceId).toBe("empty")
  })

  it("handles null trace", () => {
    const { messages } = hydrateSessionFromSnapshot(snap("null-trace", null))
    expect(messages).toHaveLength(0)
  })

  it("parses tool call arguments that are not valid JSON as strings", () => {
    const { messages } = hydrateSessionFromSnapshot(
      snap("bad-args", [
        {
          role: "assistant",
          tool_calls: [
            {
              id: "tc2",
              type: "function",
              function: { name: "echo", arguments: "not-json" },
            },
          ],
        },
      ]),
    )
    const part = messages[0].parts![0]
    expect("input" in part && part.input).toBe("not-json")
  })
})
