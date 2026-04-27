import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { get, writable } from "svelte/store"
import type { ChatMessage, StreamChatOptions } from "./streaming_chat"

vi.mock("./streaming_chat", () => ({
  streamChat: vi.fn(),
  chatGenerateId: vi.fn(() => `id-${Math.random().toString(36).slice(2, 7)}`),
  traceIdForNextChatRequest: vi.fn(() => undefined),
}))

vi.mock("$lib/api_client", () => ({
  base_url: "http://test:8000",
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

describe("chatSessionStore global instance", () => {
  it("is exported and functional", async () => {
    const { chatSessionStore } = await importFreshWithMock()
    const state = get(chatSessionStore)
    expect(state.messages).toEqual([])
    expect(state.status).toBe("ready")
  })
})
