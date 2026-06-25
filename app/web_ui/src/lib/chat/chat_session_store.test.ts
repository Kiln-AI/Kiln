import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { get, writable } from "svelte/store"
import type {
  ChatMessage,
  ContextUsage,
  StreamChatOptions,
} from "./streaming_chat"

vi.mock("./streaming_chat", () => ({
  streamChat: vi.fn(),
  chatGenerateId: vi.fn(() => `id-${Math.random().toString(36).slice(2, 7)}`),
  traceIdForNextChatRequest: vi.fn(() => undefined),
}))

const mockClientGet = vi.fn()
vi.mock("$lib/api_client", () => ({
  base_url: "http://test:8000",
  client: {
    GET: (...args: unknown[]) => mockClientGet(...args),
  },
}))

const mockHydrate = vi.fn()
vi.mock("./session_messages", () => ({
  hydrateSessionFromSnapshot: (...args: unknown[]) => mockHydrate(...args),
}))

const mockAppState = {
  path: "/test",
  pageName: "Test Page",
  pageDescription: "A test page",
  currentProject: null,
  currentTask: null,
}

vi.mock("$lib/agent", () => ({
  getCurrentAppState: vi.fn(() => ({ ...mockAppState })),
  buildContextHeader: vi.fn(() => null),
}))

const mockConsentStore = writable(true)
vi.mock("$lib/stores", () => ({
  chat_cost_disclaimer_acknowledged: mockConsentStore,
}))

function stubSessionStorage() {
  const store: Record<string, string> = {}
  return {
    store,
    mock: {
      getItem: vi.fn((key: string) => store[key] ?? null),
      setItem: vi.fn((key: string, value: string) => {
        store[key] = value
      }),
      removeItem: vi.fn((key: string) => {
        delete store[key]
      }),
    },
  }
}

let storage: ReturnType<typeof stubSessionStorage>

async function importFreshWithMock() {
  const storeModule = await import("./chat_session_store")
  const streamingModule = await import("./streaming_chat")
  const streamChatMock = vi.mocked(streamingModule.streamChat)
  return { ...storeModule, streamChatMock }
}

function noopStreamChat(): Promise<void> {
  return Promise.resolve()
}

// A configurable fake auto-run store. ``autoModeOn`` defaults off; pass an
// override to simulate the conversation flag being on (inject-on-send paths).
function makeFakeAutoRun(
  overrides: Partial<{
    autoModeOn: boolean
    armed: boolean
    requestEnable: ReturnType<typeof vi.fn>
    sendMessage: ReturnType<typeof vi.fn>
    stop: ReturnType<typeof vi.fn>
    resolve: ReturnType<typeof vi.fn>
    attach: ReturnType<typeof vi.fn>
    beginReconnect: ReturnType<typeof vi.fn>
    arm: ReturnType<typeof vi.fn>
    disarm: ReturnType<typeof vi.fn>
  }> = {},
) {
  return {
    autoModeOn: writable(overrides.autoModeOn ?? false),
    armed: writable(overrides.armed ?? false),
    working: writable(false),
    reconnecting: writable(false),
    runId: writable(overrides.autoModeOn ? "ar_test" : null),
    offReason: writable(null),
    connection: writable("idle"),
    bind: vi.fn(),
    requestEnable:
      overrides.requestEnable ?? vi.fn().mockResolvedValue({ ok: true }),
    decline: vi.fn().mockResolvedValue(undefined),
    sendMessage:
      overrides.sendMessage ?? vi.fn().mockResolvedValue({ ok: true }),
    stop: overrides.stop ?? vi.fn().mockResolvedValue(undefined),
    resolve: overrides.resolve ?? vi.fn().mockResolvedValue(null),
    beginReconnect: overrides.beginReconnect ?? vi.fn(),
    attach: overrides.attach ?? vi.fn(),
    detach: vi.fn(),
    arm: overrides.arm ?? vi.fn(),
    disarm: overrides.disarm ?? vi.fn(),
    _close: vi.fn(),
  } as unknown as Parameters<
    typeof import("./chat_session_store").createChatSessionStore
  >[1]
}

function capturingStreamChat(capture: {
  options: StreamChatOptions | null
}): (options: StreamChatOptions) => Promise<void> {
  return (opts: StreamChatOptions) => {
    capture.options = opts
    return Promise.resolve()
  }
}

beforeEach(() => {
  storage = stubSessionStorage()
  vi.stubGlobal("window", {
    sessionStorage: storage.mock,
  })
  vi.stubGlobal("sessionStorage", storage.mock)
  mockConsentStore.set(true)
  mockClientGet.mockReset()
  mockHydrate.mockReset()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.resetModules()
  vi.restoreAllMocks()
})

describe("createChatSessionStore", () => {
  it("has correct initial state", async () => {
    const { createChatSessionStore } = await importFreshWithMock()
    const store = createChatSessionStore()
    const state = get(store)
    expect(state.messages).toEqual([])
    expect(state.status).toBe("ready")
    expect(state.abortController).toBeNull()
    expect(state.collapsedPartKeys).toEqual({})
  })

  describe("sendMessage", () => {
    it("appends user and assistant messages and sets status to submitted", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      streamChatMock.mockImplementation(noopStreamChat)
      const store = createChatSessionStore()

      await store.sendMessage("hello")

      const state = get(store)
      expect(state.messages).toHaveLength(2)
      expect(state.messages[0].role).toBe("user")
      expect(state.messages[0].content).toBe("hello")
      expect(state.messages[1].role).toBe("assistant")
      expect(state.messages[1].parts).toEqual([])
      expect(state.status).toBe("submitted")
      expect(state.abortController).toBeInstanceOf(AbortController)
    })

    it("trims whitespace from input", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      streamChatMock.mockImplementation(noopStreamChat)
      const store = createChatSessionStore()

      await store.sendMessage("  hello  ")
      expect(get(store).messages[0].content).toBe("hello")
    })

    it("ignores empty messages", async () => {
      const { createChatSessionStore } = await importFreshWithMock()
      const store = createChatSessionStore()

      await store.sendMessage("")
      await store.sendMessage("   ")
      expect(get(store).messages).toHaveLength(0)
      expect(get(store).status).toBe("ready")
    })

    it("guards against sending when not ready", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      streamChatMock.mockImplementation(noopStreamChat)
      const store = createChatSessionStore()

      await store.sendMessage("first")
      expect(get(store).status).toBe("submitted")

      await store.sendMessage("second")
      expect(get(store).messages).toHaveLength(2)
      expect(streamChatMock).toHaveBeenCalledTimes(1)
    })

    it("transitions to streaming when onAssistantMessage is called", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      const capture: { options: StreamChatOptions | null } = { options: null }
      streamChatMock.mockImplementation(capturingStreamChat(capture))
      const store = createChatSessionStore()

      await store.sendMessage("hi")
      expect(get(store).status).toBe("submitted")

      capture.options!.onAssistantMessage((draft: ChatMessage) => {
        draft.parts = [{ type: "text", text: "response" }]
      })

      const state = get(store)
      expect(state.status).toBe("streaming")
      expect(state.messages[1].parts).toEqual([
        { type: "text", text: "response" },
      ])
    })

    it("transitions to ready on finish", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      const capture: { options: StreamChatOptions | null } = { options: null }
      streamChatMock.mockImplementation(capturingStreamChat(capture))
      const store = createChatSessionStore()

      await store.sendMessage("hi")
      capture.options!.onFinish()

      expect(get(store).status).toBe("ready")
      expect(get(store).abortController).toBeNull()
    })

    it("resets activity indicator and toolExecuting on finish", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      const capture: { options: StreamChatOptions | null } = { options: null }
      streamChatMock.mockImplementation(capturingStreamChat(capture))
      const store = createChatSessionStore()

      await store.sendMessage("hi")
      capture.options!.onShowActivityIndicator!(true)
      capture.options!.onToolExecutionStart!(1)
      expect(get(store).showActivityIndicator).toBe(true)
      expect(get(store).toolExecuting).toBe(true)

      capture.options!.onFinish()

      expect(get(store).showActivityIndicator).toBe(false)
      expect(get(store).toolExecuting).toBe(false)
    })

    it("resets activity indicator and toolExecuting on error", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      const capture: { options: StreamChatOptions | null } = { options: null }
      streamChatMock.mockImplementation(capturingStreamChat(capture))
      const store = createChatSessionStore()

      await store.sendMessage("hi")
      capture.options!.onShowActivityIndicator!(true)
      capture.options!.onToolExecutionStart!(1)

      capture.options!.onError(new Error("boom"))

      expect(get(store).showActivityIndicator).toBe(false)
      expect(get(store).toolExecuting).toBe(false)
    })

    it("adds error message on error callback", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      const capture: { options: StreamChatOptions | null } = { options: null }
      streamChatMock.mockImplementation(capturingStreamChat(capture))
      const store = createChatSessionStore()

      await store.sendMessage("hi")
      capture.options!.onError(new Error("network failure"))

      const state = get(store)
      expect(state.status).toBe("ready")
      expect(state.messages).toHaveLength(3)
      expect(state.messages[2].role).toBe("error")
      expect(state.messages[2].content).toBe("network failure")
    })

    it("removes existing error messages before sending", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      const capture: { options: StreamChatOptions | null } = { options: null }
      streamChatMock.mockImplementation(capturingStreamChat(capture))
      const store = createChatSessionStore()

      await store.sendMessage("hi")
      capture.options!.onError(new Error("fail"))
      expect(get(store).messages.some((m) => m.role === "error")).toBe(true)

      await store.sendMessage("retry")
      expect(
        get(store).messages.filter((m) => m.role === "error"),
      ).toHaveLength(0)
      expect(streamChatMock).toHaveBeenCalledTimes(2)
    })

    it("sets traceId on assistant message via onChatTrace", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      const capture: { options: StreamChatOptions | null } = { options: null }
      streamChatMock.mockImplementation(capturingStreamChat(capture))
      const store = createChatSessionStore()

      await store.sendMessage("hi")
      capture.options!.onChatTrace!("trace-abc")

      const state = get(store)
      const assistant = state.messages[1]
      expect(assistant.traceId).toBe("trace-abc")
    })

    it("adds inline error message via onInlineError", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      const capture: { options: StreamChatOptions | null } = { options: null }
      streamChatMock.mockImplementation(capturingStreamChat(capture))
      const store = createChatSessionStore()

      await store.sendMessage("hi")
      capture.options!.onInlineError!("server error", "trace-xyz")

      const state = get(store)
      expect(state.status).toBe("ready")
      const errorMsg = state.messages.find((m) => m.role === "error")
      expect(errorMsg).toBeDefined()
      expect(errorMsg?.content).toBe("server error")
      expect(errorMsg?.traceId).toBe("trace-xyz")
    })

    it("blocks sending when consent not acknowledged and no callback", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      streamChatMock.mockImplementation(noopStreamChat)
      const store = createChatSessionStore()
      mockConsentStore.set(false)

      const sent = await store.sendMessage("hello")
      expect(sent).toBe(false)
      expect(get(store).messages).toHaveLength(0)
      expect(streamChatMock).not.toHaveBeenCalled()
    })

    it("prompts for consent and sends on approval", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      streamChatMock.mockImplementation(noopStreamChat)
      const store = createChatSessionStore()
      mockConsentStore.set(false)
      store.onConsentNeeded = () => Promise.resolve(true)

      const sent = await store.sendMessage("hello")
      expect(sent).toBe(true)
      expect(get(store).messages).toHaveLength(2)
      expect(streamChatMock).toHaveBeenCalledTimes(1)
    })

    it("does not send when consent is denied", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      streamChatMock.mockImplementation(noopStreamChat)
      const store = createChatSessionStore()
      mockConsentStore.set(false)
      store.onConsentNeeded = () => Promise.resolve(false)

      const sent = await store.sendMessage("hello")
      expect(sent).toBe(false)
      expect(get(store).messages).toHaveLength(0)
      expect(streamChatMock).not.toHaveBeenCalled()
    })

    it("surfaces an inline error when enabling auto mode fails (429)", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      const capture: { options: StreamChatOptions | null } = { options: null }
      streamChatMock.mockImplementation(capturingStreamChat(capture))

      // Fake auto-run store whose enable fails like a 429 "Too many auto runs".
      const requestEnable = vi.fn().mockResolvedValue({
        ok: false,
        error: "Too many auto runs",
      })
      const fakeAutoRun = makeFakeAutoRun({ requestEnable })

      const store = createChatSessionStore(undefined, fakeAutoRun)
      store.onAutoModeConsentNeeded = () => Promise.resolve(true)

      await store.sendMessage("hi")
      // Drive the consent path the interactive stream hands off to.
      await capture.options!.onAutoModeConsentRequired!({
        traceId: "trace-1",
        enableToolCallId: "call_1",
        reason: null,
        siblingToolCalls: [],
      })

      expect(requestEnable).toHaveBeenCalledTimes(1)
      const errorMsg = get(store).messages.find((m) => m.role === "error")
      expect(errorMsg).toBeDefined()
      expect(errorMsg?.content).toBe(
        "Couldn't start auto mode: Too many auto runs",
      )
    })

    it("skips consent prompt when already acknowledged", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      streamChatMock.mockImplementation(noopStreamChat)
      const store = createChatSessionStore()
      mockConsentStore.set(true)
      const consentFn = vi.fn(() => Promise.resolve(true))
      store.onConsentNeeded = consentFn

      const sent = await store.sendMessage("hello")
      expect(sent).toBe(true)
      expect(consentFn).not.toHaveBeenCalled()
    })

    it("injects via the auto run (not /api/chat) when auto mode is on, never stopping it", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      streamChatMock.mockImplementation(noopStreamChat)
      const sendMessage = vi.fn().mockResolvedValue({ ok: true })
      const stop = vi.fn().mockResolvedValue(undefined)
      const fakeAutoRun = makeFakeAutoRun({
        autoModeOn: true,
        sendMessage,
        stop,
      })
      const store = createChatSessionStore(undefined, fakeAutoRun)

      const sent = await store.sendMessage("keep going")
      expect(sent).toBe(true)
      // Routed to the inject endpoint, NOT the interactive stream, and the run
      // was never stopped (Revision R1 inject-on-send).
      expect(sendMessage).toHaveBeenCalledTimes(1)
      expect(sendMessage.mock.calls[0][0]).toBe("keep going")
      expect(stop).not.toHaveBeenCalled()
      expect(streamChatMock).not.toHaveBeenCalled()
    })

    it("armed-first-send (Revision R2) creates the run via enable seeded with the message, no trace_id", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      streamChatMock.mockImplementation(noopStreamChat)
      const requestEnable = vi.fn().mockResolvedValue({ ok: true })
      const sendMessage = vi.fn().mockResolvedValue({ ok: true })
      // Armed client-side on a brand-new conversation: no run yet (autoModeOn off).
      const fakeAutoRun = makeFakeAutoRun({
        armed: true,
        requestEnable,
        sendMessage,
      })
      const store = createChatSessionStore(undefined, fakeAutoRun)

      const sent = await store.sendMessage("first message")
      expect(sent).toBe(true)

      // The first send creates the run via enable seeded with the message and
      // NO trace_id — never the /message inject path (no run exists yet) and
      // never the interactive stream.
      expect(requestEnable).toHaveBeenCalledTimes(1)
      const seed = requestEnable.mock.calls[0][0]
      expect(seed.trace_id).toBeUndefined()
      expect(seed.extra_messages).toEqual([
        { role: "user", content: "first message" },
      ])
      expect(sendMessage).not.toHaveBeenCalled()
      expect(streamChatMock).not.toHaveBeenCalled()

      // The user message is rendered locally (the server does not echo a seed's
      // extra_messages; only the /message inject path echoes).
      const msgs = get(store).messages
      expect(msgs[msgs.length - 1]).toMatchObject({
        role: "user",
        content: "first message",
      })
    })

    it("armed-first-send surfaces an enable failure and does not consume the input", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      streamChatMock.mockImplementation(noopStreamChat)
      const requestEnable = vi
        .fn()
        .mockResolvedValue({ ok: false, error: "Too many auto runs" })
      const fakeAutoRun = makeFakeAutoRun({ armed: true, requestEnable })
      const store = createChatSessionStore(undefined, fakeAutoRun)

      const sent = await store.sendMessage("first message")
      expect(sent).toBe(false)
      // The failure surfaces as an inline error message in the transcript.
      const errors = get(store).messages.filter((m) => m.role === "error")
      expect(errors.length).toBe(1)
      expect(errors[0].content).toContain("Too many auto runs")
    })

    it("does not re-prompt auto-mode consent while auto mode is already on", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      streamChatMock.mockImplementation(noopStreamChat)
      const fakeAutoRun = makeFakeAutoRun({ autoModeOn: true })
      const store = createChatSessionStore(undefined, fakeAutoRun)
      const autoConsent = vi.fn(() => Promise.resolve(true))
      store.onAutoModeConsentNeeded = autoConsent

      await store.sendMessage("again")
      // Sending while on injects directly; the interactive consent handoff
      // (auto-mode-consent-required) is never reached, so no re-prompt.
      expect(autoConsent).not.toHaveBeenCalled()
      expect(streamChatMock).not.toHaveBeenCalled()
    })

    it("injects even while the interactive status is not ready (auto bursts run server-side)", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      streamChatMock.mockImplementation(noopStreamChat)
      const sendMessage = vi.fn().mockResolvedValue({ ok: true })
      const fakeAutoRun = makeFakeAutoRun({ autoModeOn: true, sendMessage })
      const store = createChatSessionStore(undefined, fakeAutoRun)

      const sent = await store.sendMessage("during a burst")
      expect(sent).toBe(true)
      expect(sendMessage).toHaveBeenCalledTimes(1)
    })

    it("drives autoWorking from the auto-run sink during bursts and clears it on idle/off", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      streamChatMock.mockImplementation(noopStreamChat)
      // Capture the sink the store registers via bind() so we can simulate the
      // auto runner's control events (the same path that fires during bursts).
      let boundSink: import("./auto_run_store").AutoRunChatSink | null = null
      const fakeAutoRun = makeFakeAutoRun({ autoModeOn: true })
      ;(
        fakeAutoRun as unknown as {
          bind: (s: import("./auto_run_store").AutoRunChatSink) => void
        }
      ).bind = (s) => {
        boundSink = s
      }
      const store = createChatSessionStore(undefined, fakeAutoRun)
      expect(boundSink).not.toBeNull()

      // Burst working → the chat view's transcript-loading flag turns on, the
      // SAME state interactive streaming would set (the loading-indicator fix).
      boundSink!.onWorkingChange(true)
      expect(get(store).autoWorking).toBe(true)

      // Idle keeps the flag on (handled by the indicator binding) but clears the
      // working sub-state so the thinking dots stop.
      boundSink!.onAutoModeIdle("done")
      expect(get(store).autoWorking).toBe(false)

      boundSink!.onWorkingChange(true)
      expect(get(store).autoWorking).toBe(true)
      boundSink!.onAutoModeOff("user_stopped")
      expect(get(store).autoWorking).toBe(false)
    })

    it("renders an echoed injected user message as a fresh user turn", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      streamChatMock.mockImplementation(noopStreamChat)
      let boundSink: import("./auto_run_store").AutoRunChatSink | null = null
      const fakeAutoRun = makeFakeAutoRun({ autoModeOn: true })
      ;(
        fakeAutoRun as unknown as {
          bind: (s: import("./auto_run_store").AutoRunChatSink) => void
        }
      ).bind = (s) => {
        boundSink = s
      }
      const store = createChatSessionStore(undefined, fakeAutoRun)

      boundSink!.onUserMessage("injected text")
      const msgs = get(store).messages
      const user = msgs.find((m) => m.role === "user")
      expect(user?.content).toBe("injected text")
      // A fresh assistant turn follows so the burst renders into a new turn.
      expect(msgs[msgs.length - 1].role).toBe("assistant")
    })

    it("surfaces an inline error when injecting a message fails", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      streamChatMock.mockImplementation(noopStreamChat)
      const sendMessage = vi
        .fn()
        .mockResolvedValue({ ok: false, error: "Run is gone" })
      const fakeAutoRun = makeFakeAutoRun({ autoModeOn: true, sendMessage })
      const store = createChatSessionStore(undefined, fakeAutoRun)

      const sent = await store.sendMessage("hi")
      expect(sent).toBe(false)
      const errorMsg = get(store).messages.find((m) => m.role === "error")
      expect(errorMsg?.content).toBe("Couldn't send the message: Run is gone")
    })
  })

  describe("stop", () => {
    it("aborts the current request", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      streamChatMock.mockImplementation(noopStreamChat)
      const store = createChatSessionStore()

      await store.sendMessage("hi")
      const controller = get(store).abortController!
      expect(controller.signal.aborted).toBe(false)

      store.stop()
      expect(controller.signal.aborted).toBe(true)
    })

    it("does nothing when no request is in-flight", async () => {
      const { createChatSessionStore } = await importFreshWithMock()
      const store = createChatSessionStore()
      expect(() => store.stop()).not.toThrow()
    })
  })

  describe("retryLastRequest", () => {
    it("trims from last user message and re-sends", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      const capture: { options: StreamChatOptions | null } = { options: null }
      streamChatMock.mockImplementation(capturingStreamChat(capture))
      const store = createChatSessionStore()

      await store.sendMessage("first question")
      capture.options!.onFinish()

      await store.sendMessage("second question")
      capture.options!.onError(new Error("fail"))

      const beforeRetry = get(store).messages.length
      expect(beforeRetry).toBe(5)

      store.retryLastRequest()
      const state = get(store)
      const userMessages = state.messages.filter((m) => m.role === "user")
      expect(userMessages[userMessages.length - 1].content).toBe(
        "second question",
      )
    })

    it("is a no-op when status is not ready (stream in progress)", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      const capture: { options: StreamChatOptions | null } = { options: null }
      streamChatMock.mockImplementation(capturingStreamChat(capture))
      const store = createChatSessionStore()

      await store.sendMessage("hello")
      // Don't call onFinish — status stays "submitted"
      const callCountAfterSend = streamChatMock.mock.calls.length
      const messagesAfterSend = get(store).messages.length

      store.retryLastRequest()

      expect(streamChatMock).toHaveBeenCalledTimes(callCountAfterSend)
      expect(get(store).messages).toHaveLength(messagesAfterSend)
    })

    it("does nothing when there are no user messages", async () => {
      const { createChatSessionStore } = await importFreshWithMock()
      const store = createChatSessionStore()
      expect(() => store.retryLastRequest()).not.toThrow()
      expect(get(store).messages).toHaveLength(0)
    })
  })

  describe("reset", () => {
    it("clears all state", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      streamChatMock.mockImplementation(noopStreamChat)
      const store = createChatSessionStore("test_session")

      await store.sendMessage("hi")
      store.togglePartCollapsed("some-key", false)

      store.reset()
      const state = get(store)
      expect(state.messages).toEqual([])
      expect(state.status).toBe("ready")
      expect(state.abortController).toBeNull()
      expect(state.collapsedPartKeys).toEqual({})
    })

    it("writes empty state to sessionStorage via persisted.set", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      streamChatMock.mockImplementation(noopStreamChat)
      const store = createChatSessionStore("test_session")

      await store.sendMessage("hi")
      store.reset()

      const stored = JSON.parse(storage.store["test_session"])
      expect(stored.messages).toEqual([])
      expect(stored.collapsedPartKeys).toEqual({})
    })

    it("aborts in-flight request", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      streamChatMock.mockImplementation(noopStreamChat)
      const store = createChatSessionStore()

      await store.sendMessage("hi")
      const controller = get(store).abortController!

      store.reset()
      expect(controller.signal.aborted).toBe(true)
    })
  })

  describe("togglePartCollapsed", () => {
    it("flips collapse state for a key", async () => {
      const { createChatSessionStore } = await importFreshWithMock()
      const store = createChatSessionStore()

      store.togglePartCollapsed("key1", false)
      expect(get(store).collapsedPartKeys["key1"]).toBe(true)

      store.togglePartCollapsed("key1", true)
      expect(get(store).collapsedPartKeys["key1"]).toBe(false)
    })
  })

  describe("persistence", () => {
    it("persists messages to sessionStorage", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      const capture: { options: StreamChatOptions | null } = { options: null }
      streamChatMock.mockImplementation(capturingStreamChat(capture))
      const store = createChatSessionStore("persist_test")

      await store.sendMessage("hello")
      capture.options!.onFinish()

      const stored = JSON.parse(storage.store["persist_test"])
      expect(stored.messages).toHaveLength(2)
      expect(stored.messages[0].content).toBe("hello")
    })

    it("restores messages from sessionStorage on creation", async () => {
      const existingMessages: ChatMessage[] = [
        { id: "u1", role: "user", content: "saved message" },
        { id: "a1", role: "assistant", parts: [{ type: "text", text: "hi" }] },
      ]
      storage.store["restore_test"] = JSON.stringify({
        messages: existingMessages,
        collapsedPartKeys: { "a1-part-0": true },
      })

      const { createChatSessionStore } = await importFreshWithMock()
      const store = createChatSessionStore("restore_test")
      const state = get(store)
      expect(state.messages).toHaveLength(2)
      expect(state.messages[0].content).toBe("saved message")
      expect(state.collapsedPartKeys["a1-part-0"]).toBe(true)
      expect(state.status).toBe("ready")
      expect(state.abortController).toBeNull()
    })

    it("does not persist without a sessionStorageKey", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      streamChatMock.mockImplementation(noopStreamChat)
      const keysBefore = new Set(Object.keys(storage.store))
      const store = createChatSessionStore()

      await store.sendMessage("hello")
      const keysAfter = Object.keys(storage.store).filter(
        (k) => !keysBefore.has(k),
      )
      expect(keysAfter).toHaveLength(0)
    })
  })

  describe("independent instances", () => {
    it("two stores with different keys are independent", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      const capture: { options: StreamChatOptions | null } = { options: null }
      streamChatMock.mockImplementation(capturingStreamChat(capture))

      const storeA = createChatSessionStore("store_a")
      const storeB = createChatSessionStore("store_b")

      await storeA.sendMessage("msg for A")
      capture.options!.onFinish()

      expect(get(storeA).messages).toHaveLength(2)
      expect(get(storeB).messages).toHaveLength(0)
    })
  })

  describe("tool approval", () => {
    it("has correct initial approval state", async () => {
      const { createChatSessionStore } = await importFreshWithMock()
      const store = createChatSessionStore()
      const state = get(store)
      expect(state.toolApprovalWaiter).toBeNull()
      expect(state.toolApprovalPicks).toEqual({})
    })

    it("always registers an internal onToolCallsPending handler", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      const capture: { options: StreamChatOptions | null } = { options: null }
      streamChatMock.mockImplementation(capturingStreamChat(capture))
      const store = createChatSessionStore()

      await store.sendMessage("hi")
      expect(capture.options!.onToolCallsPending).toBeDefined()
      expect(typeof capture.options!.onToolCallsPending).toBe("function")
    })

    it("sets approval state when onToolCallsPending is called with approval items", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      const capture: { options: StreamChatOptions | null } = { options: null }
      streamChatMock.mockImplementation(capturingStreamChat(capture))
      const store = createChatSessionStore()

      await store.sendMessage("hi")
      const handler = capture.options!.onToolCallsPending!
      handler({
        items: [
          {
            toolCallId: "tc1",
            toolName: "read_file",
            input: {},
            requiresApproval: true,
            approvalDescription: "Read a file",
          },
        ],
      })

      const state = get(store)
      expect(state.toolApprovalWaiter).not.toBeNull()
      expect(state.toolApprovalWaiter!.payload.items).toHaveLength(1)
      expect(state.toolApprovalWaiter!.payload.items[0].toolCallId).toBe("tc1")
      expect(state.toolApprovalPicks).toEqual({ tc1: undefined })
    })

    it("auto-resolves when no items require approval", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      const capture: { options: StreamChatOptions | null } = { options: null }
      streamChatMock.mockImplementation(capturingStreamChat(capture))
      const store = createChatSessionStore()

      await store.sendMessage("hi")
      const handler = capture.options!.onToolCallsPending!
      const result = await handler({
        items: [
          {
            toolCallId: "tc1",
            toolName: "read_file",
            input: {},
            requiresApproval: false,
          },
        ],
      })

      expect(result).toEqual({})
      expect(get(store).toolApprovalWaiter).toBeNull()
    })

    it("applyToolApprovalRun sets pick to true", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      const capture: { options: StreamChatOptions | null } = { options: null }
      streamChatMock.mockImplementation(capturingStreamChat(capture))
      const store = createChatSessionStore()

      await store.sendMessage("hi")
      const handler = capture.options!.onToolCallsPending!
      handler({
        items: [
          {
            toolCallId: "tc1",
            toolName: "t1",
            input: {},
            requiresApproval: true,
          },
          {
            toolCallId: "tc2",
            toolName: "t2",
            input: {},
            requiresApproval: true,
          },
        ],
      })

      store.applyToolApprovalRun("tc1")
      expect(get(store).toolApprovalPicks["tc1"]).toBe(true)
      expect(get(store).toolApprovalWaiter).not.toBeNull()
    })

    it("applyToolApprovalSkip sets pick to false", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      const capture: { options: StreamChatOptions | null } = { options: null }
      streamChatMock.mockImplementation(capturingStreamChat(capture))
      const store = createChatSessionStore()

      await store.sendMessage("hi")
      const handler = capture.options!.onToolCallsPending!
      handler({
        items: [
          {
            toolCallId: "tc1",
            toolName: "t1",
            input: {},
            requiresApproval: true,
          },
          {
            toolCallId: "tc2",
            toolName: "t2",
            input: {},
            requiresApproval: true,
          },
        ],
      })

      store.applyToolApprovalSkip("tc1")
      expect(get(store).toolApprovalPicks["tc1"]).toBe(false)
      expect(get(store).toolApprovalWaiter).not.toBeNull()
    })

    it("resolves promise and clears state when all approvals are decided", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      const capture: { options: StreamChatOptions | null } = { options: null }
      streamChatMock.mockImplementation(capturingStreamChat(capture))
      const store = createChatSessionStore()

      await store.sendMessage("hi")
      const handler = capture.options!.onToolCallsPending!
      const promise = handler({
        items: [
          {
            toolCallId: "tc1",
            toolName: "t1",
            input: {},
            requiresApproval: true,
          },
          {
            toolCallId: "tc2",
            toolName: "t2",
            input: {},
            requiresApproval: true,
          },
        ],
      })

      store.applyToolApprovalRun("tc1")
      store.applyToolApprovalSkip("tc2")

      const decisions = await promise
      expect(decisions).toEqual({ tc1: true, tc2: false })
      expect(get(store).toolApprovalWaiter).toBeNull()
      expect(get(store).toolApprovalPicks).toEqual({})
    })

    it("applyToolApprovalRun is a no-op when no waiter is active", async () => {
      const { createChatSessionStore } = await importFreshWithMock()
      const store = createChatSessionStore()
      expect(() => store.applyToolApprovalRun("tc1")).not.toThrow()
      expect(get(store).toolApprovalWaiter).toBeNull()
    })

    it("applyToolApprovalSkip is a no-op when no waiter is active", async () => {
      const { createChatSessionStore } = await importFreshWithMock()
      const store = createChatSessionStore()
      expect(() => store.applyToolApprovalSkip("tc1")).not.toThrow()
      expect(get(store).toolApprovalWaiter).toBeNull()
    })

    it("reset clears tool approval state", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      const capture: { options: StreamChatOptions | null } = { options: null }
      streamChatMock.mockImplementation(capturingStreamChat(capture))
      const store = createChatSessionStore()

      await store.sendMessage("hi")
      const handler = capture.options!.onToolCallsPending!
      handler({
        items: [
          {
            toolCallId: "tc1",
            toolName: "t1",
            input: {},
            requiresApproval: true,
          },
        ],
      })
      expect(get(store).toolApprovalWaiter).not.toBeNull()

      store.reset()
      expect(get(store).toolApprovalWaiter).toBeNull()
      expect(get(store).toolApprovalPicks).toEqual({})
    })
  })

  describe("loadSession", () => {
    it("loads messages and sets continuation trace id", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      streamChatMock.mockImplementation(noopStreamChat)
      const store = createChatSessionStore()

      const messages: ChatMessage[] = [
        { id: "u1", role: "user", content: "hello" },
        { id: "a1", role: "assistant", parts: [{ type: "text", text: "hi" }] },
      ]
      store.loadSession(messages, "trace-123")

      const state = get(store)
      expect(state.messages).toHaveLength(2)
      expect(state.messages[0].content).toBe("hello")
      expect(state.status).toBe("ready")
      expect(state.abortController).toBeNull()
    })

    it("aborts in-flight request when loading a session", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      streamChatMock.mockImplementation(noopStreamChat)
      const store = createChatSessionStore()

      await store.sendMessage("hi")
      const controller = get(store).abortController!

      store.loadSession([], "trace-456")
      expect(controller.signal.aborted).toBe(true)
    })

    it("uses continuation trace id for subsequent messages", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      const capture: { options: StreamChatOptions | null } = { options: null }
      streamChatMock.mockImplementation(capturingStreamChat(capture))
      const store = createChatSessionStore()

      store.loadSession([], "trace-cont")
      await store.sendMessage("follow up")

      expect(capture.options!.traceId).toBe("trace-cont")
    })
  })

  describe("toolExecuting", () => {
    it("sets toolExecuting to true on onToolExecutionStart", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      const capture: { options: StreamChatOptions | null } = { options: null }
      streamChatMock.mockImplementation(capturingStreamChat(capture))
      const store = createChatSessionStore()

      await store.sendMessage("hi")
      expect(get(store).toolExecuting).toBe(false)

      capture.options!.onToolExecutionStart!(1)
      expect(get(store).toolExecuting).toBe(true)
    })

    it("sets toolExecuting to false on onToolExecutionEnd", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      const capture: { options: StreamChatOptions | null } = { options: null }
      streamChatMock.mockImplementation(capturingStreamChat(capture))
      const store = createChatSessionStore()

      await store.sendMessage("hi")
      capture.options!.onToolExecutionStart!(1)
      expect(get(store).toolExecuting).toBe(true)

      capture.options!.onToolExecutionEnd!(1)
      expect(get(store).toolExecuting).toBe(false)
    })

    it("resets toolExecuting on reset", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      const capture: { options: StreamChatOptions | null } = { options: null }
      streamChatMock.mockImplementation(capturingStreamChat(capture))
      const store = createChatSessionStore()

      await store.sendMessage("hi")
      capture.options!.onToolExecutionStart!(1)
      expect(get(store).toolExecuting).toBe(true)

      store.reset()
      expect(get(store).toolExecuting).toBe(false)
    })
  })

  describe("streaming status guard", () => {
    it("only transitions to streaming once across multiple onAssistantMessage calls", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      const capture: { options: StreamChatOptions | null } = { options: null }
      streamChatMock.mockImplementation(capturingStreamChat(capture))
      const store = createChatSessionStore()

      const statusTransitions: string[] = []
      let prevStatus = ""
      store.subscribe((s) => {
        if (s.status !== prevStatus) {
          statusTransitions.push(s.status)
          prevStatus = s.status
        }
      })
      statusTransitions.length = 0
      prevStatus = "ready"

      await store.sendMessage("hi")
      expect(get(store).status).toBe("submitted")

      capture.options!.onAssistantMessage((draft: ChatMessage) => {
        draft.parts = [{ type: "text", text: "a" }]
      })
      capture.options!.onAssistantMessage((draft: ChatMessage) => {
        draft.parts = [{ type: "text", text: "ab" }]
      })
      capture.options!.onAssistantMessage((draft: ChatMessage) => {
        draft.parts = [{ type: "text", text: "abc" }]
      })

      const streamingTransitions = statusTransitions.filter(
        (s) => s === "streaming",
      )
      expect(streamingTransitions.length).toBe(1)
    })
  })

  describe("corrupt sessionStorage", () => {
    it("starts fresh when sessionStorage contains invalid JSON", async () => {
      storage.store["corrupt_test"] = "not valid json{{"

      const { createChatSessionStore } = await importFreshWithMock()
      const store = createChatSessionStore("corrupt_test")
      const state = get(store)
      expect(state.messages).toEqual([])
      expect(state.collapsedPartKeys).toEqual({})
      expect(state.status).toBe("ready")
    })
  })

  describe("context header", () => {
    it("prepends context header on first message when buildContextHeader returns a header", async () => {
      const agentModule = await import("$lib/agent")
      const buildMock = vi.mocked(agentModule.buildContextHeader)
      buildMock.mockReturnValueOnce(
        "<new_app_ui_context>\nPath: /test\n</new_app_ui_context>",
      )

      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      const capture: { options: StreamChatOptions | null } = { options: null }
      streamChatMock.mockImplementation(capturingStreamChat(capture))
      const store = createChatSessionStore()

      await store.sendMessage("hello")

      const apiMessage = capture.options!.messages[0]
      expect(apiMessage.content).toContain("<new_app_ui_context>")
      expect(apiMessage.content).toContain("hello")
    })

    it("stores clean user text without header in messages", async () => {
      const agentModule = await import("$lib/agent")
      const buildMock = vi.mocked(agentModule.buildContextHeader)
      buildMock.mockReturnValueOnce(
        "<new_app_ui_context>\nPath: /test\n</new_app_ui_context>",
      )

      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      streamChatMock.mockImplementation(noopStreamChat)
      const store = createChatSessionStore()

      await store.sendMessage("hello")

      const state = get(store)
      const userMsg = state.messages.find((m) => m.role === "user")
      expect(userMsg?.content).toBe("hello")
      expect(userMsg?.content).not.toContain("<new_app_ui_context>")
    })

    it("does not prepend header when buildContextHeader returns null", async () => {
      const agentModule = await import("$lib/agent")
      const buildMock = vi.mocked(agentModule.buildContextHeader)
      buildMock.mockReturnValue(null)

      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      const capture: { options: StreamChatOptions | null } = { options: null }
      streamChatMock.mockImplementation(capturingStreamChat(capture))
      const store = createChatSessionStore()

      await store.sendMessage("hello")

      const apiMessage = capture.options!.messages[0]
      expect(apiMessage.content).toBe("hello")
    })

    it("updates lastSentAppState when header is sent", async () => {
      const agentModule = await import("$lib/agent")
      const buildMock = vi.mocked(agentModule.buildContextHeader)
      const getStateMock = vi.mocked(agentModule.getCurrentAppState)
      const testState = {
        path: "/test",
        pageName: "Test",
        pageDescription: "Desc",
        currentProject: null,
        currentTask: null,
      }
      getStateMock.mockReturnValue(testState)
      buildMock.mockReturnValueOnce(
        "<new_app_ui_context>\nPath: /test\n</new_app_ui_context>",
      )

      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      streamChatMock.mockImplementation(noopStreamChat)
      const store = createChatSessionStore("ctx_test")

      await store.sendMessage("hello")

      const stored = JSON.parse(storage.store["ctx_test"])
      expect(stored.lastSentAppState).toEqual(testState)
    })

    it("resets lastSentAppState on reset", async () => {
      const agentModule = await import("$lib/agent")
      const buildMock = vi.mocked(agentModule.buildContextHeader)
      buildMock.mockReturnValueOnce(
        "<new_app_ui_context>\nPath: /test\n</new_app_ui_context>",
      )

      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      streamChatMock.mockImplementation(noopStreamChat)
      const store = createChatSessionStore("reset_ctx_test")

      await store.sendMessage("hello")
      store.reset()

      const stored = JSON.parse(storage.store["reset_ctx_test"])
      expect(stored.lastSentAppState).toBeNull()
    })

    it("updates lastSentAppState even when no header is sent", async () => {
      const agentModule = await import("$lib/agent")
      const buildMock = vi.mocked(agentModule.buildContextHeader)
      buildMock.mockReturnValue(null)

      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      streamChatMock.mockImplementation(noopStreamChat)
      const store = createChatSessionStore("no_update_test")

      await store.sendMessage("hello")

      const stored = JSON.parse(storage.store["no_update_test"])
      expect(stored.lastSentAppState).not.toBeNull()
    })
  })
})

describe("resyncOnLoad (hard-refresh resync)", () => {
  it("active conversation hydrates from the current leaf, attaches, and turns the indicator on", async () => {
    const { createChatSessionStore, streamChatMock } =
      await importFreshWithMock()
    streamChatMock.mockImplementation(noopStreamChat)

    // The stored (stale) leaf comes from the restored messages.
    const streaming = await import("./streaming_chat")
    vi.mocked(streaming.traceIdForNextChatRequest).mockReturnValue("t_stale")

    // The server resolves it to the active run whose current leaf is t_now and
    // whose burst is RUNNING (Phase 9).
    const resolve = vi.fn().mockResolvedValue({
      run_id: "ar_live",
      current_trace_id: "t_now",
      status: "running",
    })
    const attach = vi.fn()
    const beginReconnect = vi.fn()
    const auto = makeFakeAutoRun({ resolve, attach, beginReconnect })

    // Hydration from the current leaf returns caught-up messages.
    const hydratedMessages: ChatMessage[] = [
      { id: "u1", role: "user", content: "hi" },
      { id: "a1", role: "assistant", parts: [], traceId: "t_now" },
    ]
    mockClientGet.mockResolvedValue({
      data: { id: "t_now", task_run: { trace: [] } },
      error: undefined,
    })
    mockHydrate.mockReturnValue({
      messages: hydratedMessages,
      continuationTraceId: "t_now",
    })

    const store = createChatSessionStore("resync_active", auto)
    await store.resyncOnLoad()

    // Resolved the stale leaf, hydrated from the CURRENT leaf, attached the run.
    expect(resolve).toHaveBeenCalledWith("t_stale")
    expect(mockClientGet).toHaveBeenCalledWith(
      "/api/chat/sessions/{session_id}",
      { params: { path: { session_id: "t_now" } } },
    )
    // Phase 9: attach is driven by the resolved liveness (RUNNING → working) and
    // the reconnecting affordance is shown for the connecting window.
    expect(beginReconnect).toHaveBeenCalled()
    expect(attach).toHaveBeenCalledWith("ar_live", true)
    // The caught-up messages replaced the stale restored view.
    expect(get(store).messages).toEqual(hydratedMessages)
  })

  it("attaches even when snapshot hydration returns a structured error (CR Moderate item 1)", async () => {
    // resolve() already proved the run is live; a snapshot error/empty response
    // must NOT short-circuit — fall through to attach so the indicator + live
    // stream are restored, same as the thrown-exception fallback.
    const { createChatSessionStore, streamChatMock } =
      await importFreshWithMock()
    streamChatMock.mockImplementation(noopStreamChat)

    const streaming = await import("./streaming_chat")
    vi.mocked(streaming.traceIdForNextChatRequest).mockReturnValue("t_stale")

    const resolve = vi.fn().mockResolvedValue({
      run_id: "ar_live",
      current_trace_id: "t_now",
      status: "idle",
    })
    const attach = vi.fn()
    const auto = makeFakeAutoRun({ resolve, attach })

    // Structured error from the snapshot fetch (no data).
    mockClientGet.mockResolvedValue({
      data: undefined,
      error: { detail: "boom" },
    })

    const store = createChatSessionStore("resync_snapshot_error", auto)
    await store.resyncOnLoad()

    expect(resolve).toHaveBeenCalledWith("t_stale")
    // Hydration did not happen (no messages to apply)...
    expect(mockHydrate).not.toHaveBeenCalled()
    // ...but we STILL attach so the conversation isn't left looking dead (IDLE
    // status → not working).
    expect(attach).toHaveBeenCalledWith("ar_live", false)
  })

  it("bails without hydrating/attaching if the user switches conversations mid-resync", async () => {
    // Race guard: the active trace changes (user picked another conversation)
    // while the snapshot GET is in flight. resyncOnLoad must NOT loadSession()
    // (overwriting the now-current session) nor attach() the stale run.
    const { createChatSessionStore, streamChatMock } =
      await importFreshWithMock()
    streamChatMock.mockImplementation(noopStreamChat)

    const streaming = await import("./streaming_chat")
    // storedTraceId and the post-resolve guard see "t_stale"; the post-GET guard
    // sees "t_switched" — i.e. the user navigated to a different conversation.
    vi.mocked(streaming.traceIdForNextChatRequest)
      .mockReturnValueOnce("t_stale")
      .mockReturnValueOnce("t_stale")
      .mockReturnValue("t_switched")

    const resolve = vi.fn().mockResolvedValue({
      run_id: "ar_live",
      current_trace_id: "t_now",
      status: "running",
    })
    const attach = vi.fn()
    const auto = makeFakeAutoRun({ resolve, attach })

    mockClientGet.mockResolvedValue({
      data: { id: "t_now", task_run: { trace: [] } },
      error: undefined,
    })

    const store = createChatSessionStore("resync_switched", auto)
    await store.resyncOnLoad()

    expect(resolve).toHaveBeenCalledWith("t_stale")
    expect(mockClientGet).toHaveBeenCalled()
    // Bailed: the stale run was neither hydrated into nor attached to the
    // newly-selected conversation.
    expect(mockHydrate).not.toHaveBeenCalled()
    expect(attach).not.toHaveBeenCalled()
  })

  it("inactive conversation (resolve 404) leaves the restored state and never attaches", async () => {
    const { createChatSessionStore, streamChatMock } =
      await importFreshWithMock()
    streamChatMock.mockImplementation(noopStreamChat)

    const streaming = await import("./streaming_chat")
    vi.mocked(streaming.traceIdForNextChatRequest).mockReturnValue("t_stale")

    const resolve = vi.fn().mockResolvedValue(null)
    const attach = vi.fn()
    const beginReconnect = vi.fn()
    const auto = makeFakeAutoRun({ resolve, attach, beginReconnect })

    const store = createChatSessionStore("resync_inactive", auto)
    await store.resyncOnLoad()

    expect(resolve).toHaveBeenCalledWith("t_stale")
    expect(mockClientGet).not.toHaveBeenCalled()
    expect(attach).not.toHaveBeenCalled()
    // Phase 9: no reconnecting affordance when there's no active run to attach to.
    expect(beginReconnect).not.toHaveBeenCalled()
  })

  it("no stored trace id is a no-op (does not call resolve)", async () => {
    const { createChatSessionStore, streamChatMock } =
      await importFreshWithMock()
    streamChatMock.mockImplementation(noopStreamChat)

    const streaming = await import("./streaming_chat")
    vi.mocked(streaming.traceIdForNextChatRequest).mockReturnValue(undefined)

    const resolve = vi.fn()
    const auto = makeFakeAutoRun({ resolve })

    const store = createChatSessionStore("resync_empty", auto)
    await store.resyncOnLoad()

    expect(resolve).not.toHaveBeenCalled()
  })
})

describe("chatSessionStore global instance", () => {
  it("is exported and functional", async () => {
    const { chatSessionStore } = await importFreshWithMock()
    const state = get(chatSessionStore)
    expect(state.messages).toEqual([])
    expect(state.status).toBe("ready")
  })
})

describe("contextUsage", () => {
  const usage: ContextUsage = {
    context_tokens: 90_000,
    context_limit: 150_000,
    context_percent: 0.6,
    compacted: false,
  }

  it("is null initially", async () => {
    const { createChatSessionStore } = await importFreshWithMock()
    const store = createChatSessionStore()
    expect(get(store).contextUsage).toBeNull()
  })

  it("is set via the onContextUsage stream callback", async () => {
    const { createChatSessionStore, streamChatMock } =
      await importFreshWithMock()
    const capture: { options: StreamChatOptions | null } = { options: null }
    streamChatMock.mockImplementation(capturingStreamChat(capture))
    const store = createChatSessionStore()

    await store.sendMessage("hi")
    capture.options!.onContextUsage!(usage)

    expect(get(store).contextUsage).toEqual(usage)
  })

  it("persists contextUsage to sessionStorage", async () => {
    const { createChatSessionStore, streamChatMock } =
      await importFreshWithMock()
    const capture: { options: StreamChatOptions | null } = { options: null }
    streamChatMock.mockImplementation(capturingStreamChat(capture))
    const store = createChatSessionStore("ctx_session")

    await store.sendMessage("hi")
    capture.options!.onContextUsage!(usage)

    const stored = JSON.parse(storage.store["ctx_session"])
    expect(stored.contextUsage).toEqual(usage)
  })

  it("restores persisted contextUsage on a fresh store", async () => {
    storage.store["ctx_restore"] = JSON.stringify({
      messages: [],
      collapsedPartKeys: {},
      lastSentAppState: null,
      contextUsage: usage,
    })
    const { createChatSessionStore } = await importFreshWithMock()
    const store = createChatSessionStore("ctx_restore")
    expect(get(store).contextUsage).toEqual(usage)
  })

  it("sets contextUsage on loadSession", async () => {
    const { createChatSessionStore } = await importFreshWithMock()
    const store = createChatSessionStore()
    store.loadSession([], "trace-load", usage)
    expect(get(store).contextUsage).toEqual(usage)
  })

  it("defaults contextUsage to null when loadSession omits it", async () => {
    const { createChatSessionStore } = await importFreshWithMock()
    const store = createChatSessionStore()
    store.loadSession([], "trace-load")
    expect(get(store).contextUsage).toBeNull()
  })

  it("clears contextUsage on reset", async () => {
    const { createChatSessionStore, streamChatMock } =
      await importFreshWithMock()
    const capture: { options: StreamChatOptions | null } = { options: null }
    streamChatMock.mockImplementation(capturingStreamChat(capture))
    const store = createChatSessionStore()

    await store.sendMessage("hi")
    capture.options!.onContextUsage!(usage)
    expect(get(store).contextUsage).toEqual(usage)

    store.reset()
    expect(get(store).contextUsage).toBeNull()
  })
})

describe("compacting (Phase 5)", () => {
  it("is false initially", async () => {
    const { createChatSessionStore } = await importFreshWithMock()
    const store = createChatSessionStore()
    expect(get(store).compacting).toBe(false)
  })

  it("is set true via the onCompactionStatus stream callback", async () => {
    const { createChatSessionStore, streamChatMock } =
      await importFreshWithMock()
    const capture: { options: StreamChatOptions | null } = { options: null }
    streamChatMock.mockImplementation(capturingStreamChat(capture))
    const store = createChatSessionStore()

    await store.sendMessage("hi")
    capture.options!.onCompactionStatus!(true)
    expect(get(store).compacting).toBe(true)

    capture.options!.onCompactionStatus!(false)
    expect(get(store).compacting).toBe(false)
  })

  it("clears compacting on finish", async () => {
    const { createChatSessionStore, streamChatMock } =
      await importFreshWithMock()
    const capture: { options: StreamChatOptions | null } = { options: null }
    streamChatMock.mockImplementation(capturingStreamChat(capture))
    const store = createChatSessionStore()

    await store.sendMessage("hi")
    capture.options!.onCompactionStatus!(true)
    expect(get(store).compacting).toBe(true)

    capture.options!.onFinish()
    expect(get(store).compacting).toBe(false)
  })

  it("clears compacting on reset", async () => {
    const { createChatSessionStore, streamChatMock } =
      await importFreshWithMock()
    const capture: { options: StreamChatOptions | null } = { options: null }
    streamChatMock.mockImplementation(capturingStreamChat(capture))
    const store = createChatSessionStore()

    await store.sendMessage("hi")
    capture.options!.onCompactionStatus!(true)
    expect(get(store).compacting).toBe(true)

    store.reset()
    expect(get(store).compacting).toBe(false)
  })

  it("is not persisted to sessionStorage", async () => {
    const { createChatSessionStore, streamChatMock } =
      await importFreshWithMock()
    const capture: { options: StreamChatOptions | null } = { options: null }
    streamChatMock.mockImplementation(capturingStreamChat(capture))
    const store = createChatSessionStore("kiln_chat_test")

    await store.sendMessage("hi")
    capture.options!.onCompactionStatus!(true)
    expect(get(store).compacting).toBe(true)

    // ``compacting`` is runtime-only — it must never be written into the
    // persisted sessionStorage payload.
    const persisted = storage.store["kiln_chat_test"]
    expect(persisted).toBeDefined()
    expect(persisted).not.toContain("compacting")
  })
})
