import { describe, expect, it } from "vitest"
import {
  autoModeConsentPayloadFromEvent,
  normalizeContextUsage,
  StreamEventProcessor,
  type ContextUsage,
  type StreamEvent,
} from "./streaming_chat"

// Phase 5 note: the traceIdForNextChatRequest suite died with the function —
// the browser keys conversations on session ids and never derives a
// continuation key from message trace ids (functional spec §4).

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
  it("maps the legacy enable-only shape (no trigger) to the enable variant", () => {
    // Pre-FR2 desktops emit only enable_tool_call_id/reason/siblings; the
    // parsed payload must read as the enable trigger with the gating id
    // falling back to the enable id.
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
      spawn: null,
      siblingToolCalls: [],
    })
  })

  it("prefers gating_tool_call_id when both spellings are present", () => {
    const payload = autoModeConsentPayloadFromEvent({
      type: "auto-mode-consent-required",
      trigger: "enable_auto_mode",
      gating_tool_call_id: "call_gating",
      enable_tool_call_id: "call_gating",
      reason: null,
    })
    expect(payload.gatingToolCallId).toBe("call_gating")
    expect(payload.reason).toBeNull()
  })

  it("maps the spawn trigger with its spawn info and no reason", () => {
    const sibling = {
      toolCallId: "tc_sib",
      toolName: "add",
      input: {},
      requiresApproval: false,
    }
    const payload = autoModeConsentPayloadFromEvent({
      type: "auto-mode-consent-required",
      trigger: "spawn_subagent",
      gating_tool_call_id: "call_spawn",
      spawn: { agent_type: "general", name: "Helper", prompt: "do things" },
      sibling_tool_calls: [sibling],
    })
    expect(payload).toEqual({
      trigger: "spawn_subagent",
      gatingToolCallId: "call_spawn",
      reason: null,
      spawn: {
        agentType: "general",
        name: "Helper",
        prompt: "do things",
        rawInput: {
          agent_type: "general",
          name: "Helper",
          prompt: "do things",
        },
      },
      siblingToolCalls: [sibling],
    })
  })

  it("preserves unknown spawn fields verbatim in rawInput (schema growth)", () => {
    const wireSpawn = {
      agent_type: "general",
      name: "Helper",
      prompt: "do things",
      max_rounds: 7,
      model: "future-field",
    }
    const payload = autoModeConsentPayloadFromEvent({
      type: "auto-mode-consent-required",
      trigger: "spawn_subagent",
      gating_tool_call_id: "call_spawn",
      spawn: wireSpawn as unknown as { name?: string },
    })
    expect(payload.spawn?.rawInput).toEqual(wireSpawn)
  })

  it("tolerates a malformed spawn value without throwing", () => {
    const payload = autoModeConsentPayloadFromEvent({
      type: "auto-mode-consent-required",
      trigger: "spawn_subagent",
      gating_tool_call_id: "call_spawn",
      spawn: "not-an-object" as unknown as { name?: string },
    })
    expect(payload.trigger).toBe("spawn_subagent")
    expect(payload.spawn).toBeNull()
  })

  it("treats an unknown trigger as the enable variant (forward compat)", () => {
    const payload = autoModeConsentPayloadFromEvent({
      type: "auto-mode-consent-required",
      trigger: "something_new",
      gating_tool_call_id: "call_x",
      spawn: { name: "ignored" },
    })
    expect(payload.trigger).toBe("enable_auto_mode")
    expect(payload.spawn).toBeNull()
    expect(payload.gatingToolCallId).toBe("call_x")
  })
})

describe("StreamEventProcessor kiln_compaction_status (Phase 5)", () => {
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
