import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { get } from "svelte/store"
import type { ChatMessage, StreamChatOptions } from "./streaming_chat"

vi.mock("./streaming_chat", () => ({
  streamChat: vi.fn(),
  chatGenerateId: vi.fn(() => `id-${Math.random().toString(36).slice(2, 7)}`),
  traceIdForNextChatRequest: vi.fn(() => undefined),
}))

vi.mock("$lib/api_client", () => ({
  base_url: "http://test:8000",
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

      store.sendMessage("hello")

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

      store.sendMessage("  hello  ")
      expect(get(store).messages[0].content).toBe("hello")
    })

    it("ignores empty messages", async () => {
      const { createChatSessionStore } = await importFreshWithMock()
      const store = createChatSessionStore()

      store.sendMessage("")
      store.sendMessage("   ")
      expect(get(store).messages).toHaveLength(0)
      expect(get(store).status).toBe("ready")
    })

    it("guards against sending when not ready", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      streamChatMock.mockImplementation(noopStreamChat)
      const store = createChatSessionStore()

      store.sendMessage("first")
      expect(get(store).status).toBe("submitted")

      store.sendMessage("second")
      expect(get(store).messages).toHaveLength(2)
      expect(streamChatMock).toHaveBeenCalledTimes(1)
    })

    it("transitions to streaming when onAssistantMessage is called", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      const capture: { options: StreamChatOptions | null } = { options: null }
      streamChatMock.mockImplementation(capturingStreamChat(capture))
      const store = createChatSessionStore()

      store.sendMessage("hi")
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

      store.sendMessage("hi")
      capture.options!.onFinish()

      expect(get(store).status).toBe("ready")
      expect(get(store).abortController).toBeNull()
    })

    it("adds error message on error callback", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      const capture: { options: StreamChatOptions | null } = { options: null }
      streamChatMock.mockImplementation(capturingStreamChat(capture))
      const store = createChatSessionStore()

      store.sendMessage("hi")
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

      store.sendMessage("hi")
      capture.options!.onError(new Error("fail"))
      expect(get(store).messages.some((m) => m.role === "error")).toBe(true)

      store.sendMessage("retry")
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

      store.sendMessage("hi")
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

      store.sendMessage("hi")
      capture.options!.onInlineError!("server error", "trace-xyz")

      const state = get(store)
      expect(state.status).toBe("ready")
      const errorMsg = state.messages.find((m) => m.role === "error")
      expect(errorMsg).toBeDefined()
      expect(errorMsg?.content).toBe("server error")
      expect(errorMsg?.traceId).toBe("trace-xyz")
    })
  })

  describe("stop", () => {
    it("aborts the current request", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      streamChatMock.mockImplementation(noopStreamChat)
      const store = createChatSessionStore()

      store.sendMessage("hi")
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

      store.sendMessage("first question")
      capture.options!.onFinish()

      store.sendMessage("second question")
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

      store.sendMessage("hello")
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

      store.sendMessage("hi")
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

      store.sendMessage("hi")
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

      store.sendMessage("hi")
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

      store.sendMessage("hello")
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

      store.sendMessage("hello")
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

      storeA.sendMessage("msg for A")
      capture.options!.onFinish()

      expect(get(storeA).messages).toHaveLength(2)
      expect(get(storeB).messages).toHaveLength(0)
    })
  })

  describe("setOnToolCallsPending", () => {
    it("passes the handler through to streamChat", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      const capture: { options: StreamChatOptions | null } = { options: null }
      streamChatMock.mockImplementation(capturingStreamChat(capture))
      const store = createChatSessionStore()

      const handler = vi.fn().mockResolvedValue({ "tool-1": true })
      store.setOnToolCallsPending(handler)

      store.sendMessage("hi")
      expect(capture.options!.onToolCallsPending).toBe(handler)
    })

    it("does not pass handler when not set", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      const capture: { options: StreamChatOptions | null } = { options: null }
      streamChatMock.mockImplementation(capturingStreamChat(capture))
      const store = createChatSessionStore()

      store.sendMessage("hi")
      expect(capture.options!.onToolCallsPending).toBeUndefined()
    })

    it("can clear the handler by setting null", async () => {
      const { createChatSessionStore, streamChatMock } =
        await importFreshWithMock()
      const capture: { options: StreamChatOptions | null } = { options: null }
      streamChatMock.mockImplementation(capturingStreamChat(capture))
      const store = createChatSessionStore()

      const handler = vi.fn().mockResolvedValue({})
      store.setOnToolCallsPending(handler)
      store.setOnToolCallsPending(null)

      store.sendMessage("hi")
      expect(capture.options!.onToolCallsPending).toBeUndefined()
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
})

describe("chatSessionStore global instance", () => {
  it("is exported and functional", async () => {
    const { chatSessionStore } = await importFreshWithMock()
    const state = get(chatSessionStore)
    expect(state.messages).toEqual([])
    expect(state.status).toBe("ready")
  })
})
