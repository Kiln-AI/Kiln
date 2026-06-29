// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest"
import { get } from "svelte/store"
import {
  createAutoRunStore,
  type AutoRunChatSink,
  type AutoRunStore,
} from "./auto_run_store"
import type {
  ChatMessage,
  ContextUsage,
  ToolCallsPendingItem,
} from "./streaming_chat"

vi.mock("$lib/api_client", () => ({
  base_url: "http://localhost:8757",
}))

// A controllable fake EventSource installed on globalThis. Records the
// construction URL and close() calls; tests drive message/open/error.
type Listener = (event: MessageEvent | Event) => void

class FakeEventSource {
  static instances: FakeEventSource[] = []
  url: string
  closed = false
  onopen: ((this: EventSource, ev: Event) => void) | null = null
  onmessage: ((this: EventSource, ev: MessageEvent) => void) | null = null
  onerror: ((this: EventSource, ev: Event) => void) | null = null
  private listeners: Record<string, Listener[]> = {}

  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }

  addEventListener(type: string, listener: Listener) {
    ;(this.listeners[type] ||= []).push(listener)
  }

  close() {
    this.closed = true
  }

  open() {
    this.onopen?.call(this as unknown as EventSource, new Event("open"))
  }

  message(data: unknown) {
    const event = { data: JSON.stringify(data) } as MessageEvent
    this.onmessage?.call(this as unknown as EventSource, event)
  }

  fail() {
    this.onerror?.call(this as unknown as EventSource, new Event("error"))
  }

  static latest(): FakeEventSource {
    return FakeEventSource.instances[FakeEventSource.instances.length - 1]
  }

  static reset() {
    FakeEventSource.instances = []
  }
}

interface SinkCalls {
  beginAssistantTurn: number
  assistantUpdates: ChatMessage[]
  traces: string[]
  errors: string[]
  toolStart: number[]
  toolEnd: number[]
  activity: boolean[]
  working: boolean[]
  userMessages: string[]
  idleReasons: (string | null)[]
  offReasons: (string | null)[]
  pendingToolCalls: ToolCallsPendingItem[][]
  contextUsages: ContextUsage[]
  compactionStatuses: boolean[]
}

function makeSink(): { sink: AutoRunChatSink; calls: SinkCalls } {
  const calls: SinkCalls = {
    beginAssistantTurn: 0,
    assistantUpdates: [],
    traces: [],
    errors: [],
    toolStart: [],
    toolEnd: [],
    activity: [],
    working: [],
    userMessages: [],
    idleReasons: [],
    offReasons: [],
    pendingToolCalls: [],
    contextUsages: [],
    compactionStatuses: [],
  }
  const sink: AutoRunChatSink = {
    beginAssistantTurn: () => {
      calls.beginAssistantTurn += 1
    },
    onAssistantMessage: (update) => {
      const draft: ChatMessage = { id: "a", role: "assistant", parts: [] }
      update(draft)
      calls.assistantUpdates.push(draft)
    },
    onChatTrace: (tid) => calls.traces.push(tid),
    onContextUsage: (usage) => calls.contextUsages.push(usage),
    onCompactionStatus: (c) => calls.compactionStatuses.push(c),
    onInlineError: (msg) => calls.errors.push(msg),
    onToolExecutionStart: (n) => calls.toolStart.push(n),
    onToolExecutionEnd: (n) => calls.toolEnd.push(n),
    onShowActivityIndicator: (s) => calls.activity.push(s),
    onWorkingChange: (w) => calls.working.push(w),
    onUserMessage: (c) => calls.userMessages.push(c),
    onAutoModeIdle: (r) => calls.idleReasons.push(r),
    onAutoModeOff: (r) => calls.offReasons.push(r),
    onToolCallsPending: (items) => calls.pendingToolCalls.push(items),
  }
  return { sink, calls }
}

function readerFromChunks(
  chunks: string[],
): ReadableStreamDefaultReader<Uint8Array> {
  const encoder = new TextEncoder()
  let i = 0
  return {
    read: () => {
      if (i < chunks.length) {
        return Promise.resolve({
          done: false,
          value: encoder.encode(chunks[i++]),
        })
      }
      return Promise.resolve({ done: true, value: undefined })
    },
  } as unknown as ReadableStreamDefaultReader<Uint8Array>
}

describe("auto_run_store", () => {
  let store: AutoRunStore
  let calls: SinkCalls

  beforeEach(() => {
    // @ts-expect-error install fake on global
    globalThis.EventSource = FakeEventSource
    FakeEventSource.reset()
    store = createAutoRunStore()
    const made = makeSink()
    calls = made.calls
    store.bind(made.sink)
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it("enable → attach → events feed into the processor", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ run_id: "ar_1" }),
    })
    vi.stubGlobal("fetch", fetchMock)

    // Backend-tool path (an enable_tool_call_id is present): a burst starts
    // immediately, so a fresh assistant turn is opened to render it.
    const result = await store.requestEnable({
      trace_id: "t1",
      enable_tool_call_id: "call_enable",
    })
    expect(result.ok).toBe(true)

    // Enable POST went out with the seed body.
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe("http://localhost:8757/api/chat/auto/enable")
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      trace_id: "t1",
      enable_tool_call_id: "call_enable",
    })

    // A fresh assistant turn was started and the events stream opened.
    expect(calls.beginAssistantTurn).toBe(1)
    const source = FakeEventSource.latest()
    expect(source.url).toBe("http://localhost:8757/api/chat/auto/ar_1/events")

    // auto-mode-on confirms the on state from the runner.
    source.message({ type: "auto-mode-on", run_id: "ar_1" })
    expect(get(store.autoModeOn)).toBe(true)
    expect(get(store.runId)).toBe("ar_1")

    // A normal chat event flows to the processor → sink.
    source.message({ type: "text-start", id: "x" })
    source.message({ type: "text-delta", delta: "Hello" })
    expect(calls.assistantUpdates.length).toBeGreaterThan(0)
    const last = calls.assistantUpdates[calls.assistantUpdates.length - 1]
    expect(last.parts?.[0]).toEqual({ type: "text", text: "Hello" })
  })

  it("manual arm (no enable_tool_call_id) does NOT begin an assistant turn but still attaches", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ run_id: "ar_arm" }),
    })
    vi.stubGlobal("fetch", fetchMock)

    // Manual enable only arms the conversation (functional spec §4.1(2)): the
    // server creates the run IDLE without an empty upstream burst, so there's no
    // immediate assistant turn to open — the indicator just turns on.
    const result = await store.requestEnable({ trace_id: "t1" })
    expect(result.ok).toBe(true)
    expect(calls.beginAssistantTurn).toBe(0)

    // The events stream still opens so the indicator + future bursts render.
    const source = FakeEventSource.latest()
    expect(source.url).toBe("http://localhost:8757/api/chat/auto/ar_arm/events")
    // The server buffers on→idle markers; replaying them lands on flag-on/idle.
    source.message({ type: "auto-mode-on", run_id: "ar_arm" })
    source.message({
      type: "auto-mode-idle",
      run_id: "ar_arm",
      reason: "armed",
    })
    expect(get(store.autoModeOn)).toBe(true)
    expect(get(store.working)).toBe(false)
  })

  it("arm sets the armed flag without any server call; disarm clears it", () => {
    const fetchMock = vi.fn()
    vi.stubGlobal("fetch", fetchMock)
    expect(get(store.armed)).toBe(false)
    store.arm()
    expect(get(store.armed)).toBe(true)
    // Client-only: no enable POST and no events stream.
    expect(fetchMock).not.toHaveBeenCalled()
    expect(FakeEventSource.instances.length).toBe(0)
    store.disarm()
    expect(get(store.armed)).toBe(false)
  })

  it("no-trace enable (Revision R2) seeds the first message, begins a turn, attaches, clears armed", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ run_id: "ar_new" }),
    })
    vi.stubGlobal("fetch", fetchMock)
    // The conversation was armed client-side (brand-new chat, no trace_id).
    store.arm()
    expect(get(store.armed)).toBe(true)

    // The first send creates the run via enable with extra_messages + no trace_id.
    const result = await store.requestEnable({
      extra_messages: [{ role: "user", content: "do the thing" }],
    })
    expect(result.ok).toBe(true)

    // The enable POST carried the first message and NO trace_id.
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe("http://localhost:8757/api/chat/auto/enable")
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      extra_messages: [{ role: "user", content: "do the thing" }],
    })

    // A burst starts immediately (extra_messages), so an assistant turn opened,
    // the events stream attached, and the client-armed flag cleared (the real
    // server run now owns the on-state).
    expect(calls.beginAssistantTurn).toBe(1)
    expect(get(store.armed)).toBe(false)
    const source = FakeEventSource.latest()
    expect(source.url).toBe("http://localhost:8757/api/chat/auto/ar_new/events")
    source.message({ type: "auto-mode-on", run_id: "ar_new" })
    expect(get(store.autoModeOn)).toBe(true)
    expect(get(store.runId)).toBe("ar_new")
  })

  it("tool-calls-pending on the observer stream hands off to the approval sink (graceful stop)", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ run_id: "ar_stop" }),
    })
    vi.stubGlobal("fetch", fetchMock)
    await store.requestEnable({
      trace_id: "t1",
      enable_tool_call_id: "call_enable",
    })
    const source = FakeEventSource.latest()
    source.message({ type: "auto-mode-on", run_id: "ar_stop" })

    // Graceful stop: the runner surfaces the final turn's client tool calls.
    const items = [
      {
        toolCallId: "tc1",
        toolName: "call_kiln_api",
        input: { path: "/x" },
        requiresApproval: true,
      },
    ]
    source.message({ type: "tool-calls-pending", items })
    // Handed off to the existing approval machinery (not auto-executed).
    expect(calls.pendingToolCalls.length).toBe(1)
    expect(calls.pendingToolCalls[0]).toEqual(items)
    // Working sub-state cleared; the tool-calls-pending event is NOT forwarded to
    // the processor as a normal chat event.
    expect(get(store.working)).toBe(false)

    // The accompanying auto-mode-off clears the indicator (normal mode again).
    source.message({
      type: "auto-mode-off",
      run_id: "ar_stop",
      reason: "user_stopped",
    })
    expect(get(store.autoModeOn)).toBe(false)
    expect(calls.offReasons).toContain("user_stopped")
  })

  it("auto-mode-off clears state and closes the stream", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ run_id: "ar_2" }),
    })
    vi.stubGlobal("fetch", fetchMock)
    await store.requestEnable({ trace_id: "t" })
    const source = FakeEventSource.latest()
    source.message({ type: "auto-mode-on", run_id: "ar_2" })
    expect(get(store.autoModeOn)).toBe(true)

    source.message({
      type: "auto-mode-off",
      run_id: "ar_2",
      reason: "asked_user",
    })
    expect(get(store.autoModeOn)).toBe(false)
    expect(get(store.runId)).toBeNull()
    expect(get(store.offReason)).toBe("asked_user")
    expect(source.closed).toBe(true)
    expect(calls.offReasons).toEqual(["asked_user"])
  })

  it("stop posts to the run's stop endpoint without flipping state locally", async () => {
    const enableFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ run_id: "ar_3" }),
    })
    vi.stubGlobal("fetch", enableFetch)
    await store.requestEnable({ trace_id: "t" })
    FakeEventSource.latest().message({ type: "auto-mode-on", run_id: "ar_3" })

    const stopFetch = vi.fn().mockResolvedValue({ ok: true })
    vi.stubGlobal("fetch", stopFetch)
    await store.stop()

    expect(stopFetch).toHaveBeenCalledTimes(1)
    expect(stopFetch.mock.calls[0][0]).toBe(
      "http://localhost:8757/api/chat/auto/ar_3/stop",
    )
    // State stays "on" until the authoritative auto-mode-off arrives.
    expect(get(store.autoModeOn)).toBe(true)
  })

  it("decline posts the decline body and consumes the interactive stream", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      body: {
        getReader: () =>
          readerFromChunks([
            'data: {"type":"text-start","id":"x"}\n\n',
            'data: {"type":"text-delta","delta":"resumed"}\n\n',
          ]),
      },
    })
    vi.stubGlobal("fetch", fetchMock)

    await store.decline({
      trace_id: "t9",
      enable_tool_call_id: "call_1",
      siblings: [],
    })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe("http://localhost:8757/api/chat/auto/decline")
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      trace_id: "t9",
      enable_tool_call_id: "call_1",
      siblings: [],
    })
    expect(calls.beginAssistantTurn).toBe(1)
    const last = calls.assistantUpdates[calls.assistantUpdates.length - 1]
    expect(last.parts?.[0]).toEqual({ type: "text", text: "resumed" })
    // No EventSource opened for the decline (interactive resume path).
    expect(FakeEventSource.instances.length).toBe(0)
  })

  it("re-attach opens the events stream and replays buffered events with no gap", () => {
    store.attach("ar_re")
    const source = FakeEventSource.latest()
    expect(source.url).toBe("http://localhost:8757/api/chat/auto/ar_re/events")
    expect(get(store.autoModeOn)).toBe(true)
    expect(get(store.runId)).toBe("ar_re")

    // Replayed buffer (in-progress turn) arrives before live events.
    source.open()
    source.message({ type: "auto-mode-on", run_id: "ar_re" })
    source.message({ type: "text-start", id: "x" })
    source.message({ type: "text-delta", delta: "buffered" })
    source.message({ type: "text-delta", delta: " + live" })

    const last = calls.assistantUpdates[calls.assistantUpdates.length - 1]
    expect(last.parts?.[0]).toEqual({ type: "text", text: "buffered + live" })
  })

  it("events 404 / connection failure falls back to off without throwing", () => {
    store.attach("ar_gone")
    const source = FakeEventSource.latest()
    expect(get(store.autoModeOn)).toBe(true)

    // EventSource errors before opening (events 404 → unknown/GC'd run).
    expect(() => source.fail()).not.toThrow()
    expect(get(store.autoModeOn)).toBe(false)
    expect(get(store.runId)).toBeNull()
    expect(source.closed).toBe(true)
    expect(calls.offReasons).toEqual([null])
  })

  it("enable 429 returns an error and opens no stream", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 429,
      json: () => Promise.resolve({ detail: "Too many auto runs" }),
    })
    vi.stubGlobal("fetch", fetchMock)

    const result = await store.requestEnable({ trace_id: "t" })
    expect(result.ok).toBe(false)
    expect(result.error).toBe("Too many auto runs")
    expect(get(store.autoModeOn)).toBe(false)
    expect(FakeEventSource.instances.length).toBe(0)
    expect(calls.beginAssistantTurn).toBe(0)
  })

  it("detach closes the observer and clears the indicator without signalling off", () => {
    store.attach("ar_nav")
    const source = FakeEventSource.latest()
    source.message({ type: "auto-mode-on", run_id: "ar_nav" })
    expect(get(store.autoModeOn)).toBe(true)

    store.detach()
    expect(get(store.autoModeOn)).toBe(false)
    expect(get(store.runId)).toBeNull()
    expect(source.closed).toBe(true)
    // Navigation, not an off-event: the sink is not told the run ended.
    expect(calls.offReasons).toEqual([])
  })

  it("auto-mode-idle keeps the flag ON and only clears the working sub-state", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ run_id: "ar_idle" }),
    })
    vi.stubGlobal("fetch", fetchMock)
    await store.requestEnable({ trace_id: "t" })
    const source = FakeEventSource.latest()
    source.message({ type: "auto-mode-on", run_id: "ar_idle" })
    expect(get(store.autoModeOn)).toBe(true)
    expect(get(store.working)).toBe(true)

    source.message({
      type: "auto-mode-idle",
      run_id: "ar_idle",
      reason: "asked_user",
    })
    // Flag persists (Revision R1); only working clears. Stream stays open.
    expect(get(store.autoModeOn)).toBe(true)
    expect(get(store.working)).toBe(false)
    expect(get(store.runId)).toBe("ar_idle")
    expect(source.closed).toBe(false)
    expect(calls.idleReasons).toEqual(["asked_user"])
    // Idle is NOT an off-event: the conversation flag is unchanged.
    expect(calls.offReasons).toEqual([])
    // working timeline: on (enable attach) → on (auto-mode-on) → off (idle).
    expect(calls.working).toEqual([true, true, false])
  })

  it("only auto-mode-off clears the indicator after an idle burst", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ run_id: "ar_io" }),
    })
    vi.stubGlobal("fetch", fetchMock)
    await store.requestEnable({ trace_id: "t" })
    const source = FakeEventSource.latest()
    source.message({ type: "auto-mode-on", run_id: "ar_io" })
    source.message({ type: "auto-mode-idle", run_id: "ar_io", reason: "done" })
    expect(get(store.autoModeOn)).toBe(true)

    source.message({
      type: "auto-mode-off",
      run_id: "ar_io",
      reason: "user_stopped",
    })
    expect(get(store.autoModeOn)).toBe(false)
    expect(get(store.working)).toBe(false)
    expect(get(store.runId)).toBeNull()
    expect(source.closed).toBe(true)
    expect(calls.offReasons).toEqual(["user_stopped"])
  })

  it("sendMessage injects via /message, never posting stop", async () => {
    const enableFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ run_id: "ar_inj" }),
    })
    vi.stubGlobal("fetch", enableFetch)
    await store.requestEnable({ trace_id: "t" })
    FakeEventSource.latest().message({ type: "auto-mode-on", run_id: "ar_inj" })

    const messageFetch = vi.fn().mockResolvedValue({ ok: true })
    vi.stubGlobal("fetch", messageFetch)
    const result = await store.sendMessage("keep going", "trace-9")

    expect(result.ok).toBe(true)
    expect(messageFetch).toHaveBeenCalledTimes(1)
    const [url, init] = messageFetch.mock.calls[0]
    expect(url).toBe("http://localhost:8757/api/chat/auto/ar_inj/message")
    expect((init as RequestInit).method).toBe("POST")
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      content: "keep going",
      trace_id: "trace-9",
    })
    // Inject never stops: no /stop call, flag stays on, working set.
    expect(
      messageFetch.mock.calls.some((c) => String(c[0]).endsWith("/stop")),
    ).toBe(false)
    expect(get(store.autoModeOn)).toBe(true)
    expect(get(store.working)).toBe(true)
  })

  it("sendMessage with no active run returns an error and posts nothing", async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal("fetch", fetchMock)
    const result = await store.sendMessage("hi")
    expect(result.ok).toBe(false)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("a user-message echo renders a fresh user turn and marks working", async () => {
    store.attach("ar_echo")
    const source = FakeEventSource.latest()
    source.message({ type: "auto-mode-on", run_id: "ar_echo" })
    // Simulate going idle then injecting: the echo arrives on the stream.
    source.message({
      type: "auto-mode-idle",
      run_id: "ar_echo",
      reason: "done",
    })
    expect(get(store.working)).toBe(false)

    source.message({ type: "user-message", content: "do the next thing" })
    expect(calls.userMessages).toEqual(["do the next thing"])
    expect(get(store.working)).toBe(true)
    expect(get(store.autoModeOn)).toBe(true)
  })

  it("resolve returns {run_id, current_trace_id, status} for an active run", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          run_id: "ar_r",
          current_trace_id: "t_now",
          status: "running",
        }),
    })
    vi.stubGlobal("fetch", fetchMock)

    const result = await store.resolve("t_stale")
    expect(result).toEqual({
      run_id: "ar_r",
      current_trace_id: "t_now",
      status: "running",
    })
    const [url] = fetchMock.mock.calls[0]
    expect(url).toBe(
      "http://localhost:8757/api/chat/auto/resolve?trace_id=t_stale",
    )
  })

  it("resolve returns null on 404 (no active run)", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: () => Promise.resolve({ detail: "no active run" }),
    })
    vi.stubGlobal("fetch", fetchMock)
    expect(await store.resolve("t_stale")).toBeNull()
  })

  it("resolve returns null on network error", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error("boom"))
    vi.stubGlobal("fetch", fetchMock)
    expect(await store.resolve("t")).toBeNull()
  })

  // ── Phase 9: reconnecting affordance + on-attach liveness ──────────────────

  it("beginReconnect sets the reconnecting affordance; attach clears it on open", () => {
    expect(get(store.reconnecting)).toBe(false)
    store.beginReconnect()
    expect(get(store.reconnecting)).toBe(true)

    store.attach("ar_rc")
    // Still reconnecting through the connecting window (no stream established).
    expect(get(store.reconnecting)).toBe(true)

    const source = FakeEventSource.latest()
    source.open()
    // Attach established → the affordance clears (can't get stuck on).
    expect(get(store.reconnecting)).toBe(false)
  })

  it("attach clears reconnecting on the first event even without onopen", () => {
    store.beginReconnect()
    store.attach("ar_rc2")
    expect(get(store.reconnecting)).toBe(true)

    const source = FakeEventSource.latest()
    source.message({ type: "auto-mode-state", run_id: "ar_rc2", working: true })
    expect(get(store.reconnecting)).toBe(false)
  })

  it("attach with initialWorking drives the thinking indicator immediately", () => {
    // Phase 9: a RUNNING run (from resolve status) shows working before any event.
    store.beginReconnect()
    store.attach("ar_work", true)
    expect(get(store.working)).toBe(true)
    expect(get(store.autoModeOn)).toBe(true)

    // An IDLE run (initialWorking=false) shows "· waiting for you" immediately.
    store.detach()
    store.beginReconnect()
    store.attach("ar_wait", false)
    expect(get(store.working)).toBe(false)
    expect(get(store.autoModeOn)).toBe(true)
  })

  it("auto-mode-state snapshot sets working + flag and clears reconnecting", () => {
    store.beginReconnect()
    store.attach("ar_state")
    const source = FakeEventSource.latest()

    // Working snapshot → thinking indicator on, reconnecting cleared.
    source.message({
      type: "auto-mode-state",
      run_id: "ar_state",
      flag_on: true,
      working: true,
    })
    expect(get(store.autoModeOn)).toBe(true)
    expect(get(store.working)).toBe(true)
    expect(get(store.reconnecting)).toBe(false)

    // Idle snapshot → working off, flag stays on.
    source.message({
      type: "auto-mode-state",
      run_id: "ar_state",
      flag_on: true,
      working: false,
    })
    expect(get(store.working)).toBe(false)
    expect(get(store.autoModeOn)).toBe(true)
  })

  it("reconnecting clears on error (404) so the affordance can't get stuck", () => {
    store.beginReconnect()
    store.attach("ar_rc_gone")
    expect(get(store.reconnecting)).toBe(true)

    const source = FakeEventSource.latest()
    source.fail() // events 404 / connection failure before opening
    expect(get(store.reconnecting)).toBe(false)
    expect(get(store.autoModeOn)).toBe(false)
  })

  it("reconnecting clears on auto-mode-off and on detach", () => {
    store.beginReconnect()
    store.attach("ar_rc_off")
    const source = FakeEventSource.latest()
    source.message({
      type: "auto-mode-off",
      run_id: "ar_rc_off",
      reason: "user_stopped",
    })
    expect(get(store.reconnecting)).toBe(false)

    store.beginReconnect()
    expect(get(store.reconnecting)).toBe(true)
    store.detach()
    expect(get(store.reconnecting)).toBe(false)
  })

  it("is a pure observer: an off event never posts stop", async () => {
    const enableFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ run_id: "ar_4" }),
    })
    vi.stubGlobal("fetch", enableFetch)
    await store.requestEnable({ trace_id: "t" })

    const postSpy = vi.fn().mockResolvedValue({ ok: true })
    vi.stubGlobal("fetch", postSpy)

    const source = FakeEventSource.latest()
    source.message({ type: "auto-mode-on", run_id: "ar_4" })
    source.message({ type: "auto-mode-off", run_id: "ar_4", reason: "done" })

    expect(postSpy).not.toHaveBeenCalled()
  })
})
