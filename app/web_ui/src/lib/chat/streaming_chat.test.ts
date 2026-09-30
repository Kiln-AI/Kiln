import { describe, expect, it } from "vitest"
import {
  autoModeConsentPayloadFromEvent,
  normalizeContextUsage,
  StreamEventProcessor,
  type ChatMessage,
  type ContextUsage,
  type StreamEvent,
} from "./streaming_chat"

describe("normalizeContextUsage", () => {
  it("returns null for absent payload", () => {
    expect(normalizeContextUsage(null)).toBeNull()
    expect(normalizeContextUsage(undefined)).toBeNull()
    expect(normalizeContextUsage({})).toBeNull()
  })

  it("normalizes a full payload", () => {
    expect(
      normalizeContextUsage({
        context_tokens: 100,
        context_limit: 1000,
        context_percent: 0.1,
        compacted: true,
      }),
    ).toEqual({
      context_tokens: 100,
      context_limit: 1000,
      context_percent: 0.1,
      compacted: true,
    })
  })

  it("defaults missing numbers to 0 and compacted to false", () => {
    expect(normalizeContextUsage({ context_percent: 0.5 })).toEqual({
      context_tokens: 0,
      context_limit: 0,
      context_percent: 0.5,
      compacted: false,
    })
  })
})

describe("StreamEventProcessor context_usage", () => {
  function makeProcessor(onContextUsage: (u: ContextUsage) => void) {
    return new StreamEventProcessor({
      onAssistantMessage: () => {},
      onContextUsage,
    })
  }

  it("fires onContextUsage when kiln_chat_trace carries context_usage", () => {
    const usages: ContextUsage[] = []
    const traces: string[] = []
    const processor = new StreamEventProcessor({
      onAssistantMessage: () => {},
      onChatTrace: (t) => traces.push(t),
      onContextUsage: (u) => usages.push(u),
    })
    const event: StreamEvent = {
      type: "kiln_chat_trace",
      trace_id: "trace-1",
      context_usage: {
        context_tokens: 90,
        context_limit: 100,
        context_percent: 0.9,
        compacted: true,
      },
    }
    processor.handleEvent(event)
    expect(traces).toEqual(["trace-1"])
    expect(usages).toEqual([
      {
        context_tokens: 90,
        context_limit: 100,
        context_percent: 0.9,
        compacted: true,
      },
    ])
  })

  it("does not fire onContextUsage when context_usage is absent", () => {
    const usages: ContextUsage[] = []
    const processor = makeProcessor((u) => usages.push(u))
    processor.handleEvent({ type: "kiln_chat_trace", trace_id: "trace-2" })
    expect(usages).toHaveLength(0)
  })

  it("normalizes a partial context_usage without throwing", () => {
    const usages: ContextUsage[] = []
    const processor = makeProcessor((u) => usages.push(u))
    processor.handleEvent({
      type: "kiln_chat_trace",
      trace_id: "trace-3",
      context_usage: { context_percent: 0.42 },
    })
    expect(usages).toEqual([
      {
        context_tokens: 0,
        context_limit: 0,
        context_percent: 0.42,
        compacted: false,
      },
    ])
  })
})

describe("autoModeConsentPayloadFromEvent", () => {
  it("falls back to enable_tool_call_id when no gating id is sent", () => {
    const payload = autoModeConsentPayloadFromEvent({
      type: "auto-mode-consent-required",
      enable_tool_call_id: "call_enable",
      reason: "let me work",
      sibling_tool_calls: [],
    })
    expect(payload).toEqual({
      trigger: "enable_auto_mode",
      gatingToolCallId: "call_enable",
      reason: "let me work",
      siblingToolCalls: [],
    })
  })

  it("prefers gating_tool_call_id when both spellings are present", () => {
    const payload = autoModeConsentPayloadFromEvent({
      type: "auto-mode-consent-required",
      trigger: "enable_auto_mode",
      gating_tool_call_id: "call_gating",
      enable_tool_call_id: "call_enable_fallback",
      reason: null,
    })
    expect(payload.gatingToolCallId).toBe("call_gating")
    expect(payload.reason).toBeNull()
  })

  it("treats an unknown trigger as the enable variant (forward compat)", () => {
    const payload = autoModeConsentPayloadFromEvent({
      type: "auto-mode-consent-required",
      trigger: "something_new",
      gating_tool_call_id: "call_x",
    })
    expect(payload.trigger).toBe("enable_auto_mode")
    expect(payload.gatingToolCallId).toBe("call_x")
  })
})

describe("StreamEventProcessor kiln_compaction_status", () => {
  function makeProcessor(onCompactionStatus: (c: boolean) => void) {
    return new StreamEventProcessor({
      onAssistantMessage: () => {},
      onCompactionStatus,
    })
  }

  it("sets compacting=true on a started status event", () => {
    const states: boolean[] = []
    const processor = makeProcessor((c) => states.push(c))
    processor.handleEvent({ type: "kiln_compaction_status", state: "started" })
    expect(states).toEqual([true])
  })

  it("clears compacting on the next text content event", () => {
    const states: boolean[] = []
    const processor = makeProcessor((c) => states.push(c))
    processor.handleEvent({ type: "kiln_compaction_status", state: "started" })
    processor.handleEvent({ type: "text-start" })
    processor.handleEvent({ type: "text-delta", delta: "hi" })
    expect(states[0]).toBe(true)
    // The first content event clears it; later content events keep it cleared.
    expect(states.slice(1).every((s) => s === false)).toBe(true)
    expect(states).toContain(false)
  })

  it("clears compacting on the snapshot (kiln_chat_trace) event", () => {
    const states: boolean[] = []
    const processor = makeProcessor((c) => states.push(c))
    processor.handleEvent({ type: "kiln_compaction_status", state: "started" })
    processor.handleEvent({ type: "kiln_chat_trace", trace_id: "trace-1" })
    expect(states[0]).toBe(true)
    expect(states[states.length - 1]).toBe(false)
  })

  it("does NOT clear compacting on a finished status event (stays up until content)", () => {
    // A fast/buffered started→finished pair must not collapse the visible
    // window. Only real assistant content clears the indicator, so a "finished"
    // event on its own is ignored (no clear emitted).
    const states: boolean[] = []
    const processor = makeProcessor((c) => states.push(c))
    processor.handleEvent({ type: "kiln_compaction_status", state: "started" })
    processor.handleEvent({ type: "kiln_compaction_status", state: "finished" })
    // Only the "started" → true was emitted; "finished" produced no callback.
    expect(states).toEqual([true])
  })

  it("stays compacting through a started→finished pair, clears on first content", () => {
    const states: boolean[] = []
    const processor = makeProcessor((c) => states.push(c))
    processor.handleEvent({ type: "kiln_compaction_status", state: "started" })
    processor.handleEvent({ type: "kiln_compaction_status", state: "finished" })
    expect(states).toEqual([true])
    // The first real assistant content is what clears it.
    processor.handleEvent({ type: "text-start" })
    expect(states[states.length - 1]).toBe(false)
  })

  it("clears compacting on an error event", () => {
    const states: boolean[] = []
    const processor = new StreamEventProcessor({
      onAssistantMessage: () => {},
      onCompactionStatus: (c) => states.push(c),
      onInlineError: () => {},
    })
    processor.handleEvent({ type: "kiln_compaction_status", state: "started" })
    processor.handleEvent({ type: "error", message: "boom" })
    expect(states[0]).toBe(true)
    expect(states[states.length - 1]).toBe(false)
  })
})

describe("StreamEventProcessor kiln-chat-retry", () => {
  function makeProcessor(
    onRetry: (attempt: number, max: number) => void,
    onRetryClear: () => void,
  ) {
    return new StreamEventProcessor({
      onAssistantMessage: () => {},
      onRetry,
      onRetryClear,
    })
  }

  it("fires onRetry with attempt/max on a kiln-chat-retry event", () => {
    const retries: Array<[number, number]> = []
    let clears = 0
    const processor = makeProcessor(
      (a, m) => retries.push([a, m]),
      () => {
        clears += 1
      },
    )
    processor.handleEvent({
      type: "kiln-chat-retry",
      attempt: 3,
      max_attempts: 10,
      status_code: 503,
    })
    expect(retries).toEqual([[3, 10]])
    expect(clears).toBe(0)
  })

  it("clears exactly once on the next non-retry event (not per token)", () => {
    const retries: Array<[number, number]> = []
    let clears = 0
    const processor = makeProcessor(
      (a, m) => retries.push([a, m]),
      () => {
        clears += 1
      },
    )
    processor.handleEvent({
      type: "kiln-chat-retry",
      attempt: 1,
      max_attempts: 10,
    })
    // The recovered round streams several tokens — clear must fire just once.
    processor.handleEvent({ type: "text-start" })
    processor.handleEvent({ type: "text-delta", delta: "a" })
    processor.handleEvent({ type: "text-delta", delta: "b" })
    expect(clears).toBe(1)
  })

  it("does not clear when no retry is active", () => {
    let clears = 0
    const processor = makeProcessor(
      () => {},
      () => {
        clears += 1
      },
    )
    processor.handleEvent({ type: "text-delta", delta: "hi" })
    expect(clears).toBe(0)
  })
})

describe("StreamEventProcessor error events", () => {
  type CapturedError = { message: string; traceId?: string; code?: string }

  function collectErrors(): {
    processor: StreamEventProcessor
    errors: CapturedError[]
  } {
    const errors: CapturedError[] = []
    const processor = new StreamEventProcessor({
      onAssistantMessage: () => {},
      onInlineError: (message, traceId, code) =>
        errors.push({ message, traceId, code }),
    })
    return { processor, errors }
  }

  it("surfaces errorText from a forwarded provider error", () => {
    const { processor, errors } = collectErrors()
    processor.handleEvent({ type: "error", errorText: "Rate limit exceeded" })
    expect(errors).toEqual([
      { message: "Rate limit exceeded", traceId: undefined, code: undefined },
    ])
  })

  it("prefers message over errorText and forwards trace id and code", () => {
    const { processor, errors } = collectErrors()
    processor.handleEvent({
      type: "error",
      message: "Desktop error",
      errorText: "provider detail",
      trace_id: "trace-9",
      code: "SOME_CODE",
    })
    expect(errors).toEqual([
      { message: "Desktop error", traceId: "trace-9", code: "SOME_CODE" },
    ])
  })

  it("falls back to a generic message when neither field is present", () => {
    const { processor, errors } = collectErrors()
    processor.handleEvent({ type: "error" })
    expect(errors[0].message).toBe("An error occurred.")
  })
})

describe("StreamEventProcessor accumulation", () => {
  function makeDraftProcessor(): {
    processor: StreamEventProcessor
    draft: ChatMessage
  } {
    const draft: ChatMessage = { id: "a", role: "assistant", parts: [] }
    const processor = new StreamEventProcessor({
      onAssistantMessage: (update) => update(draft),
    })
    return { processor, draft }
  }

  it("orders text and tool parts as they stream and records tool output", () => {
    const { processor, draft } = makeDraftProcessor()
    processor.handleEvent({ type: "text-start" })
    processor.handleEvent({ type: "text-delta", delta: "Checking" })
    processor.handleEvent({ type: "text-end" })
    processor.handleEvent({
      type: "tool-input-available",
      toolCallId: "tc1",
      toolName: "call_kiln_api",
      input: { method: "GET", url_path: "/api/projects" },
    })
    processor.handleEvent({
      type: "tool-output-available",
      toolCallId: "tc1",
      output: "[]",
    })
    expect(draft.parts).toEqual([
      { type: "text", text: "Checking" },
      {
        type: "tool-call_kiln_api",
        toolCallId: "tc1",
        toolName: "call_kiln_api",
        input: { method: "GET", url_path: "/api/projects" },
        output: "[]",
      },
    ])
  })

  it("reset drops accumulated parts so the next turn starts empty", () => {
    const { processor, draft } = makeDraftProcessor()
    processor.handleEvent({ type: "text-delta", delta: "first turn" })
    processor.reset()
    processor.handleEvent({ type: "text-delta", delta: "second" })
    expect(draft.parts).toEqual([{ type: "text", text: "second" }])
  })
})
