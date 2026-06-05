// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest"
import { get } from "svelte/store"
import {
  createAutoRunStore,
  type AutoRunChatSink,
  type AutoRunStore,
} from "./auto_run_store"
import type { ChatMessage } from "./streaming_chat"

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
  offReasons: (string | null)[]
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
    offReasons: [],
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
    onInlineError: (msg) => calls.errors.push(msg),
    onToolExecutionStart: (n) => calls.toolStart.push(n),
    onToolExecutionEnd: (n) => calls.toolEnd.push(n),
    onShowActivityIndicator: (s) => calls.activity.push(s),
    onAutoModeOff: (r) => calls.offReasons.push(r),
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

    const result = await store.requestEnable({ trace_id: "t1" })
    expect(result.ok).toBe(true)

    // Enable POST went out with the seed body.
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe("http://localhost:8757/api/chat/auto/enable")
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      trace_id: "t1",
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
