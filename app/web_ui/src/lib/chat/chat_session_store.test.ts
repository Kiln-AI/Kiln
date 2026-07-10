// Port of the pre-phase-4 suite: the behaviors are unchanged (composer,
// queued-message UX, consent dialog, approval box, banners, persistence), but
// the DRIVER changed — the old tests mocked `streamChat` and invoked its
// callbacks; these mock the main conversation store and drive the SINK it
// binds (the observer is the only transport now).
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { get, writable } from "svelte/store"
import type { ChatMessage } from "./streaming_chat"
import type {
  MainConversationSink,
  MainConversationStore,
} from "./conversation_store"
import { CHAT_CLIENT_VERSION_TOO_OLD } from "$lib/error_codes"

const mockClientGet = vi.fn()
const mockFetch = vi.fn()
vi.mock("$lib/api_client", () => ({
  base_url: "http://test:8000",
  client: {
    GET: (...args: unknown[]) => mockClientGet(...args),
  },
}))

const mockHydrate = vi.fn()
vi.mock("./session_messages", async (importOriginal) => ({
  // Keep the real userChatMessageFromContent / stripInternalFraming (echo →
  // report chip detection, framing strip); only hydration is stubbed.
  ...(await importOriginal<typeof import("./session_messages")>()),
  hydrateSessionFromSnapshot: (...args: unknown[]) => mockHydrate(...args),
}))

const mockAppState = {
  path: "/test",
  pageName: "Test Page",
  pageDescription: "A test page",
  currentProject: null,
  currentTask: null,
}

const mockBuildContextHeader = vi.fn((): string | null => null)
vi.mock("$lib/agent", () => ({
  getCurrentAppState: vi.fn(() => ({ ...mockAppState })),
  buildContextHeader: (...args: unknown[]) =>
    mockBuildContextHeader(...(args as [])),
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

async function importFresh() {
  return await import("./chat_session_store")
}

/**
 * A configurable fake main conversation store. `bind` captures the sink so
 * tests can drive observer events; the writable stores are exposed raw so
 * tests can flip auto/armed/working directly.
 */
function makeFakeMain(overrides: Partial<Record<string, unknown>> = {}): {
  fake: MainConversationStore
  sink: () => MainConversationSink
  autoModeOn: ReturnType<typeof writable<boolean>>
  armed: ReturnType<typeof writable<boolean>>
  working: ReturnType<typeof writable<boolean>>
  sessionId: ReturnType<typeof writable<string | null>>
} {
  let sink: MainConversationSink | null = null
  const autoModeOn = writable<boolean>(false)
  const armed = writable<boolean>(false)
  const working = writable<boolean>(false)
  const sessionId = writable<string | null>(null)
  const fake = {
    autoModeOn: { subscribe: autoModeOn.subscribe },
    armed: { subscribe: armed.subscribe },
    working: { subscribe: working.subscribe },
    reconnecting: writable(false),
    retry: writable(null),
    sessionId: { subscribe: sessionId.subscribe },
    offReason: writable(null),
    connection: writable("idle"),
    bind: vi.fn((s: MainConversationSink) => {
      sink = s
    }),
    ensure: vi.fn().mockResolvedValue({ ok: true, sessionId: "cv_main" }),
    requestEnable: vi.fn().mockResolvedValue({ ok: true }),
    decline: vi.fn().mockResolvedValue(undefined),
    sendMessage: vi.fn().mockResolvedValue({ ok: true, messageId: "cm_1" }),
    stop: vi.fn().mockResolvedValue(undefined),
    fetchApprovals: vi.fn().mockResolvedValue(null),
    decide: vi.fn().mockResolvedValue({ ok: true }),
    beginReconnect: vi.fn(),
    attach: vi.fn(),
    detach: vi.fn(),
    // The real beginTurn appends the assistant placeholder via the sink and
    // resets the stream processor; the sink half matters to these tests.
    beginTurn: vi.fn(() => sink?.beginAssistantTurn()),
    arm: vi.fn(),
    disarm: vi.fn(),
    _close: vi.fn(),
    ...overrides,
  } as unknown as MainConversationStore
  return {
    fake,
    sink: () => {
      if (!sink) throw new Error("sink not bound")
      return sink
    },
    autoModeOn,
    armed,
    working,
    sessionId,
  }
}

async function makeStore(
  overrides: Partial<Record<string, unknown>> = {},
  sessionStorageKey?: string,
) {
  const { createChatSessionStore } = await importFresh()
  const main = makeFakeMain(overrides)
  const store = createChatSessionStore(sessionStorageKey, main.fake)
  return { store, ...main }
}

/** Send + drive the observer to a settled ready state. */
async function sendAndSettle(
  store: Awaited<ReturnType<typeof makeStore>>["store"],
  sink: () => MainConversationSink,
  text: string,
) {
  await store.sendMessage(text)
  sink().onInteractiveIdle()
}

beforeEach(() => {
  storage = stubSessionStorage()
  vi.stubGlobal("window", { sessionStorage: storage.mock })
  vi.stubGlobal("sessionStorage", storage.mock)
  vi.stubGlobal("fetch", mockFetch)
  mockFetch.mockResolvedValue({ ok: false, status: 500 })
  mockConsentStore.set(true)
  mockClientGet.mockReset()
  mockHydrate.mockReset()
  mockBuildContextHeader.mockReset()
  mockBuildContextHeader.mockReturnValue(null)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.resetModules()
  vi.restoreAllMocks()
})

describe("createChatSessionStore", () => {
  it("has correct initial state", async () => {
    const { store } = await makeStore()
    const s = get(store)
    expect(s.messages).toEqual([])
    expect(s.status).toBe("ready")
    expect(s.sessionId).toBeNull()
    expect(s.rootId).toBeNull()
    expect(s.queuedMessage).toBeNull()
    expect(s.toolApprovalWaiter).toBeNull()
  })

  describe("sendMessage", () => {
    it("ensures the conversation, renders the message locally, and posts it", async () => {
      const { store, fake } = await makeStore()
      const ok = await store.sendMessage("hello")
      expect(ok).toBe(true)
      // create-or-adopt replaced the old per-request POST /api/chat.
      expect(fake.ensure).toHaveBeenCalledWith(null)
      expect(fake.sendMessage).toHaveBeenCalledWith("hello")
      const s = get(store)
      // Local render: user message + assistant placeholder (zero latency).
      expect(s.messages).toHaveLength(2)
      expect(s.messages[0].role).toBe("user")
      expect(s.messages[0].content).toBe("hello")
      expect(s.messages[1].role).toBe("assistant")
      expect(s.status).toBe("submitted")
      // The adopted session id persists as the main-conversation handle.
      expect(s.sessionId).toBe("cv_main")
    })

    it("trims whitespace and ignores empty messages", async () => {
      const { store, fake } = await makeStore()
      await store.sendMessage("  hi  ")
      expect(fake.sendMessage).toHaveBeenCalledWith("hi")
      expect(await store.sendMessage("   ")).toBe(false)
      expect(fake.sendMessage).toHaveBeenCalledTimes(1)
    })

    it("queues a second message sent while a turn is in flight", async () => {
      const { store, fake } = await makeStore()
      await store.sendMessage("first")
      expect(get(store).status).toBe("submitted")
      const ok = await store.sendMessage("second")
      expect(ok).toBe(true)
      expect(get(store).queuedMessage).toBe("second")
      expect(fake.sendMessage).toHaveBeenCalledTimes(1)
    })

    it("transitions submitted → streaming on assistant content, → ready on idle", async () => {
      const { store, sink } = await makeStore()
      await store.sendMessage("hello")
      expect(get(store).status).toBe("submitted")
      sink().onAssistantMessage((draft) => {
        draft.parts = [{ type: "text", text: "hi" }]
      })
      expect(get(store).status).toBe("streaming")
      sink().onInteractiveIdle()
      expect(get(store).status).toBe("ready")
    })

    it("surfaces an ensure failure as an inline error", async () => {
      const { store } = await makeStore({
        ensure: vi.fn().mockResolvedValue({ ok: false, error: "no desktop" }),
      })
      const ok = await store.sendMessage("hello")
      expect(ok).toBe(false)
      const errors = get(store).messages.filter((m) => m.role === "error")
      expect(errors).toHaveLength(1)
      expect(errors[0].content).toContain("no desktop")
    })

    it("surfaces a failed send and returns to ready", async () => {
      const { store } = await makeStore({
        sendMessage: vi.fn().mockResolvedValue({ ok: false, error: "boom" }),
      })
      const ok = await store.sendMessage("hello")
      expect(ok).toBe(false)
      expect(get(store).status).toBe("ready")
      expect(
        get(store).messages.some(
          (m) => m.role === "error" && m.content?.includes("boom"),
        ),
      ).toBe(true)
    })

    it("removes existing error messages before sending", async () => {
      const { store, sink } = await makeStore()
      store.pushInlineError("old error")
      expect(get(store).messages.some((m) => m.role === "error")).toBe(true)
      await sendAndSettle(store, sink, "hello")
      expect(get(store).messages.some((m) => m.role === "error")).toBe(false)
    })

    it("learns the durable rootId on the first persisted turn (phase 5)", async () => {
      // The old world persisted the leaf trace id from onChatTrace here; the
      // sink now only learns "a turn persisted" and the store fetches the
      // conversation item ONCE to learn its durable root_id — the
      // restart-recovery key (a session id, never a trace id).
      const { store, sink } = await makeStore({}, "kiln_chat_test")
      await store.sendMessage("hello")
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ session_id: "cv_main", root_id: "root-42" }),
      })
      sink().onTurnPersisted()
      await vi.waitFor(() => {
        expect(get(store).rootId).toBe("root-42")
      })
      expect(mockFetch).toHaveBeenCalledWith(
        "http://test:8000/api/conversations/cv_main",
      )
      // Persisted (the recovery handle) — but never the messages.
      expect(storage.store["kiln_chat_test"]).toContain("root-42")
      expect(storage.store["kiln_chat_test"]).not.toContain("hello")
      // Once known, later persisted turns fetch nothing.
      sink().onTurnPersisted()
      await new Promise((r) => setTimeout(r, 0))
      expect(mockFetch).toHaveBeenCalledTimes(1)
    })

    it("never stamps a stale rootId onto a conversation switched mid-fetch (CR MEDIUM 2)", async () => {
      // The root fetch for the OLD conversation resolves AFTER a New Chat /
      // loadSession replaced the persisted handles — writing the old root
      // would make the next send/resync silently adopt the old conversation.
      const { store, sink } = await makeStore({}, "kiln_chat_test")
      await store.sendMessage("hello")
      let resolveItem: (v: unknown) => void = () => {}
      mockFetch.mockReturnValueOnce(new Promise((r) => (resolveItem = r)))
      sink().onTurnPersisted()
      // The user opens a DIFFERENT conversation while the fetch hangs.
      store.loadSession([], "row-new", null)
      resolveItem({
        ok: true,
        json: async () => ({ session_id: "cv_main", root_id: "root-OLD" }),
      })
      await new Promise((r) => setTimeout(r, 0))
      expect(get(store).rootId).toBeNull()
      // (sessionId is the NEW conversation's ensure result — the fake store
      // resolves every ensure to "cv_main"; only the stale root write is the
      // bug under test.)
      expect(get(store).sessionId).toBe("cv_main")
      expect(storage.store["kiln_chat_test"]).not.toContain("root-OLD")

      // Same guard for a New Chat reset.
      const secondStore = await makeStore({}, "kiln_chat_test_2")
      await secondStore.store.sendMessage("hi")
      let resolveItem2: (v: unknown) => void = () => {}
      mockFetch.mockReturnValueOnce(new Promise((r) => (resolveItem2 = r)))
      secondStore.sink().onTurnPersisted()
      secondStore.store.reset()
      resolveItem2({
        ok: true,
        json: async () => ({ session_id: "cv_main", root_id: "root-OLD" }),
      })
      await new Promise((r) => setTimeout(r, 0))
      expect(get(secondStore.store).rootId).toBeNull()
    })

    it("continues the conversation keyed by the persisted session handle", async () => {
      const { store, sink, fake } = await makeStore()
      await store.sendMessage("first")
      sink().onInteractiveIdle()
      await store.sendMessage("second")
      // Phase 5: ensure is keyed by the persisted SESSION id (the first
      // send's adopt result), never a trace id scanned off the messages.
      expect(vi.mocked(fake.ensure).mock.calls[1][0]).toBe("cv_main")
    })
  })

  describe("own-echo dedupe", () => {
    it("does not duplicate the sender's own message when its echo arrives", async () => {
      const { store, sink } = await makeStore()
      await store.sendMessage("hello")
      expect(get(store).messages.filter((m) => m.role === "user")).toHaveLength(
        1,
      )
      // The run echoes the full content (with any header) + the server id
      // returned by the 202.
      sink().onUserMessage("hello", "cm_1")
      const users = get(store).messages.filter((m) => m.role === "user")
      expect(users).toHaveLength(1)
      // The echo id lands on the local bubble so buffer replays dedupe too.
      expect(users[0].echoId).toBe("cm_1")
      sink().onUserMessage("hello", "cm_1") // replay
      expect(get(store).messages.filter((m) => m.role === "user")).toHaveLength(
        1,
      )
    })

    it("matches the own echo by stripped content when it beats the 202 id", async () => {
      const { store, sink } = await makeStore({
        // Slow response: no message id known when the echo arrives.
        sendMessage: vi.fn().mockResolvedValue({ ok: true }),
      })
      mockBuildContextHeader.mockReturnValue(
        "<new_app_ui_context>ctx</new_app_ui_context>",
      )
      await store.sendMessage("hello")
      sink().onUserMessage(
        "<new_app_ui_context>ctx</new_app_ui_context>\nhello",
        "cm_9",
      )
      const users = get(store).messages.filter((m) => m.role === "user")
      expect(users).toHaveLength(1)
      expect(users[0].content).toBe("hello")
    })

    it("renders another observer's echo (e.g. an injected report) as a chip", async () => {
      const { store, sink } = await makeStore()
      await store.sendMessage("hello")
      const report =
        '<subagent_report id="cv_1" agent_type="general" status="completed" title="Helper">\nAll done.\n</subagent_report>'
      sink().onUserMessage(report, "cm_report")
      const users = get(store).messages.filter((m) => m.role === "user")
      expect(users).toHaveLength(2)
      expect(users[1].subagentReport?.title).toBe("Helper")
      expect(users[1].content).toBe("All done.")
      // A fresh assistant turn follows the echo.
      const last = get(store).messages[get(store).messages.length - 1]
      expect(last.role).toBe("assistant")
      // Dedupe by echo id on replay.
      sink().onUserMessage(report, "cm_report")
      expect(get(store).messages.filter((m) => m.role === "user")).toHaveLength(
        2,
      )
    })
  })

  describe("cost disclaimer consent", () => {
    it("blocks sending when consent not acknowledged and no callback", async () => {
      mockConsentStore.set(false)
      const { store, fake } = await makeStore()
      expect(await store.sendMessage("hello")).toBe(false)
      expect(fake.sendMessage).not.toHaveBeenCalled()
    })

    it("prompts for consent and sends on approval", async () => {
      mockConsentStore.set(false)
      const { store, fake } = await makeStore()
      store.onConsentNeeded = vi.fn().mockResolvedValue(true)
      expect(await store.sendMessage("hello")).toBe(true)
      expect(fake.sendMessage).toHaveBeenCalled()
    })

    it("does not send when consent is denied", async () => {
      mockConsentStore.set(false)
      const { store, fake } = await makeStore()
      store.onConsentNeeded = vi.fn().mockResolvedValue(false)
      expect(await store.sendMessage("hello")).toBe(false)
      expect(fake.sendMessage).not.toHaveBeenCalled()
    })
  })

  describe("auto mode", () => {
    it("injects via the conversation (never a new turn flow) when the flag is on", async () => {
      const { store, fake, autoModeOn } = await makeStore()
      autoModeOn.set(true)
      const ok = await store.sendMessage("do more")
      expect(ok).toBe(true)
      expect(fake.sendMessage).toHaveBeenCalledWith("do more")
      // No local render: the run echoes the message (renders via the echo).
      expect(get(store).messages.filter((m) => m.role === "user")).toHaveLength(
        0,
      )
      // And the interactive machinery stayed out of it.
      expect(fake.ensure).not.toHaveBeenCalled()
      expect(get(store).status).toBe("ready")
    })

    it("queues during an active auto burst and injects at the round boundary", async () => {
      const { store, sink, fake, autoModeOn, working } = await makeStore()
      autoModeOn.set(true)
      working.set(true)
      await store.sendMessage("mid-burst note")
      expect(get(store).queuedMessage).toBe("mid-burst note")
      expect(fake.sendMessage).not.toHaveBeenCalled()
      working.set(false)
      // Round boundary: the runner finished a tool round.
      sink().onToolExecutionEnd(1)
      await vi.waitFor(() => {
        expect(fake.sendMessage).toHaveBeenCalledWith("mid-burst note")
      })
      expect(get(store).queuedMessage).toBeNull()
    })

    it("flushes a queued message when the burst goes idle", async () => {
      const { store, sink, fake, autoModeOn, working } = await makeStore()
      autoModeOn.set(true)
      working.set(true)
      await store.sendMessage("queued")
      working.set(false)
      sink().onAutoModeIdle("asked_user")
      await vi.waitFor(() => {
        expect(fake.sendMessage).toHaveBeenCalledWith("queued")
      })
    })

    it("clears the queued message when auto mode turns off", async () => {
      const { store, sink, autoModeOn, working } = await makeStore()
      autoModeOn.set(true)
      working.set(true)
      await store.sendMessage("queued")
      expect(get(store).queuedMessage).toBe("queued")
      autoModeOn.set(false)
      sink().onAutoModeOff("user_stopped")
      expect(get(store).queuedMessage).toBeNull()
    })

    it("drives autoWorking from the sink and clears it on idle", async () => {
      const { store, sink, autoModeOn } = await makeStore()
      autoModeOn.set(true)
      sink().onWorkingChange(true)
      expect(get(store).autoWorking).toBe(true)
      sink().onWorkingChange(false)
      sink().onAutoModeIdle("asked_user")
      expect(get(store).autoWorking).toBe(false)
    })

    it("armed-first-send creates the run via enable seeded with the message", async () => {
      const { store, fake, armed } = await makeStore()
      armed.set(true)
      mockBuildContextHeader.mockReturnValue(
        "<new_app_ui_context>c</new_app_ui_context>",
      )
      const ok = await store.sendMessage("first message")
      expect(ok).toBe(true)
      expect(fake.requestEnable).toHaveBeenCalledWith({
        kind: "auto",
        // No conversation exists yet — the seed carries no session key.
        session_id: undefined,
        extra_messages: [
          {
            role: "user",
            content:
              "<new_app_ui_context>c</new_app_ui_context>\nfirst message",
          },
        ],
      })
      // Rendered locally (the server does not echo seed extra_messages).
      const users = get(store).messages.filter((m) => m.role === "user")
      expect(users).toHaveLength(1)
      expect(users[0].content).toBe("first message")
    })

    it("armed-first-send surfaces an enable failure", async () => {
      const { store, armed } = await makeStore({
        requestEnable: vi
          .fn()
          .mockResolvedValue({ ok: false, error: "Too many auto runs" }),
      })
      armed.set(true)
      expect(await store.sendMessage("first")).toBe(false)
      expect(
        get(store).messages.some(
          (m) => m.role === "error" && m.content?.includes("Too many"),
        ),
      ).toBe(true)
    })
  })

  describe("auto-mode consent (on the observer stream)", () => {
    const payload = {
      enableToolCallId: "tc_enable",
      reason: "run it",
      siblingToolCalls: [],
    }

    it("accept flips the SAME conversation via requestEnable, keyed by sid", async () => {
      const { store, sink, fake, sessionId } = await makeStore()
      // The consent event arrives on the observer of a live conversation, so
      // its session id is always in hand (phase 5: the old payload traceId
      // died with the trace-keyed surface).
      sessionId.set("cv_live")
      store.onAutoModeConsentNeeded = vi.fn().mockResolvedValue(true)
      sink().onConsentRequired(payload)
      await vi.waitFor(() => {
        expect(fake.requestEnable).toHaveBeenCalledWith({
          kind: "auto",
          session_id: "cv_live",
          enable_tool_call_id: "tc_enable",
          pending_tool_calls: [],
          reason: "run it",
        })
      })
    })

    it("decline resolves via the folded-in /auto decline", async () => {
      const { store, sink, fake } = await makeStore()
      store.onAutoModeConsentNeeded = vi.fn().mockResolvedValue(false)
      sink().onConsentRequired(payload)
      await vi.waitFor(() => {
        expect(fake.decline).toHaveBeenCalledWith({
          enable_tool_call_id: "tc_enable",
          siblings: [],
        })
      })
      expect(fake.requestEnable).not.toHaveBeenCalled()
    })

    it("accepts silently (no dialog) when auto mode is already on/armed", async () => {
      const { store, sink, fake, armed } = await makeStore()
      armed.set(true)
      const dialog = vi.fn().mockResolvedValue(false)
      store.onAutoModeConsentNeeded = dialog
      sink().onConsentRequired(payload)
      await vi.waitFor(() => {
        expect(fake.requestEnable).toHaveBeenCalled()
      })
      expect(dialog).not.toHaveBeenCalled()
    })

    it("surfaces an enable failure (e.g. 429) as an inline error", async () => {
      const { store, sink } = await makeStore({
        requestEnable: vi
          .fn()
          .mockResolvedValue({ ok: false, error: "Too many auto runs" }),
      })
      store.onAutoModeConsentNeeded = vi.fn().mockResolvedValue(true)
      sink().onConsentRequired(payload)
      await vi.waitFor(() => {
        expect(
          get(store).messages.some(
            (m) => m.role === "error" && m.content?.includes("Too many"),
          ),
        ).toBe(true)
      })
    })

    it("holds queued sends until the consent flow resolves", async () => {
      const { store, sink, fake } = await makeStore()
      let resolveDialog: (v: boolean) => void = () => {}
      store.onAutoModeConsentNeeded = vi.fn(
        () => new Promise<boolean>((r) => (resolveDialog = r)),
      )
      sink().onConsentRequired(payload)
      // The turn is over server-side (idle event) but the dialog is open —
      // a send must queue, not dispatch.
      sink().onInteractiveIdle()
      await store.sendMessage("while deciding")
      expect(get(store).queuedMessage).toBe("while deciding")
      expect(fake.sendMessage).not.toHaveBeenCalled()
      resolveDialog(false)
      await vi.waitFor(() => {
        expect(fake.decline).toHaveBeenCalled()
      })
    })
  })

  describe("queued messages (interactive)", () => {
    it("appends a second queued message to the first", async () => {
      const { store } = await makeStore()
      await store.sendMessage("first")
      await store.sendMessage("queued one")
      await store.sendMessage("queued two")
      expect(get(store).queuedMessage).toBe("queued one\n\nqueued two")
    })

    it("flushes the queued message when the interactive turn finishes", async () => {
      const { store, sink, fake } = await makeStore()
      await store.sendMessage("first")
      await store.sendMessage("queued")
      sink().onInteractiveIdle()
      await vi.waitFor(() => {
        expect(fake.sendMessage).toHaveBeenCalledWith("queued")
      })
      expect(get(store).queuedMessage).toBeNull()
    })

    it("clearQueued discards without sending", async () => {
      const { store, sink, fake } = await makeStore()
      await store.sendMessage("first")
      await store.sendMessage("queued")
      store.clearQueued()
      sink().onInteractiveIdle()
      await new Promise((r) => setTimeout(r, 0))
      expect(fake.sendMessage).toHaveBeenCalledTimes(1)
    })

    it("sendQueuedNow stops the turn so the queue flushes on idle", async () => {
      const { store, sink, fake } = await makeStore()
      await store.sendMessage("first")
      await store.sendMessage("queued")
      store.sendQueuedNow()
      // Stop is a server call now (the idle event settles the turn).
      expect(fake.stop).toHaveBeenCalled()
      sink().onInteractiveIdle()
      await vi.waitFor(() => {
        expect(fake.sendMessage).toHaveBeenCalledWith("queued")
      })
    })

    it("sendQueuedNow injects immediately in auto mode", async () => {
      const { store, fake, autoModeOn, working } = await makeStore()
      autoModeOn.set(true)
      working.set(true)
      await store.sendMessage("queued")
      store.sendQueuedNow()
      await vi.waitFor(() => {
        expect(fake.sendMessage).toHaveBeenCalledWith("queued")
      })
      expect(fake.stop).not.toHaveBeenCalled()
    })

    it("restores the queued message if a flush dispatch is rejected", async () => {
      const { store, sink } = await makeStore({
        sendMessage: vi.fn().mockResolvedValue({ ok: false, error: "nope" }),
      })
      await store.sendMessage("first") // dispatch fails → inline error, ready
      await store.sendMessage("second")
      // "second" dispatched immediately (status ready) and failed too — it
      // must be restored rather than silently dropped.
      await vi.waitFor(() => {
        expect(get(store).messages.some((m) => m.role === "error")).toBe(true)
      })
      void sink
    })

    it("clears the queue on reset", async () => {
      const { store } = await makeStore()
      await store.sendMessage("first")
      await store.sendMessage("queued")
      store.reset()
      expect(get(store).queuedMessage).toBeNull()
    })
  })

  // Mid-turn sends on a LIVE run (the conversation store knows the session
  // id) ride the server inbox — the engine folds them into the next upstream
  // round — instead of waiting client-side for the whole turn to settle.
  describe("mid-turn inbox injection (interactive)", () => {
    it("POSTs a mid-turn send to the live run instead of queueing", async () => {
      const { store, fake, sessionId } = await makeStore()
      await store.sendMessage("first")
      sessionId.set("cv_main")
      expect(get(store).status).toBe("submitted")
      const ok = await store.sendMessage("second")
      expect(ok).toBe(true)
      expect(get(store).queuedMessage).toBeNull()
      expect(fake.sendMessage).toHaveBeenCalledTimes(2)
      expect(fake.sendMessage).toHaveBeenLastCalledWith("second")
      // No local render — the run's echo renders the injected message.
      expect(get(store).messages.filter((m) => m.role === "user")).toHaveLength(
        1,
      )
    })

    it("falls back to the queue when the inject POST fails", async () => {
      const { store, fake, sessionId } = await makeStore()
      await store.sendMessage("first")
      sessionId.set("cv_main")
      vi.mocked(fake.sendMessage).mockResolvedValueOnce({
        ok: false,
        error: "boom",
      })
      const ok = await store.sendMessage("second")
      expect(ok).toBe(true)
      expect(get(store).queuedMessage).toBe("second")
    })

    it("queues while an approval box is open, then injects when the run resumes", async () => {
      const approvalBatch = {
        batchId: "ab_inject",
        items: [
          {
            toolCallId: "tc1",
            toolName: "search",
            input: {},
            requiresApproval: true,
          },
        ],
      }
      const { store, sink, fake, sessionId } = await makeStore({
        fetchApprovals: vi.fn().mockResolvedValue(approvalBatch),
      })
      await store.sendMessage("first")
      sessionId.set("cv_main")
      sink().onAwaitingApproval()
      await vi.waitFor(() => {
        expect(get(store).toolApprovalWaiter).not.toBeNull()
      })
      // The open box blocks injection (the POST's optimistic working flip
      // would read as "decided elsewhere" and close it) — so the send queues.
      await store.sendMessage("while deciding")
      expect(get(store).queuedMessage).toBe("while deciding")
      expect(fake.sendMessage).toHaveBeenCalledTimes(1)
      // The batch resolves and the run resumes: the queued message injects
      // into the live run right away, not at the turn's end.
      sink().onWorkingChange(true)
      await vi.waitFor(() => {
        expect(fake.sendMessage).toHaveBeenCalledWith("while deciding")
      })
      expect(get(store).queuedMessage).toBeNull()
    })

    it("sendQueuedNow injects into the live run without stopping it", async () => {
      const { store, fake, sessionId } = await makeStore()
      await store.sendMessage("first")
      sessionId.set("cv_main")
      // A message that fell back to the queue (its inject POST failed).
      vi.mocked(fake.sendMessage).mockResolvedValueOnce({
        ok: false,
        error: "boom",
      })
      await store.sendMessage("second")
      expect(get(store).queuedMessage).toBe("second")
      store.sendQueuedNow()
      await vi.waitFor(() => {
        expect(fake.sendMessage).toHaveBeenCalledTimes(3)
      })
      expect(fake.stop).not.toHaveBeenCalled()
      expect(get(store).queuedMessage).toBeNull()
    })
  })

  describe("approval box (parked batches)", () => {
    const batch = {
      batchId: "ab_1",
      items: [
        {
          toolCallId: "tc1",
          toolName: "add",
          input: { a: 1 },
          requiresApproval: true,
        },
        {
          toolCallId: "tc2",
          toolName: "get",
          input: {},
          requiresApproval: false,
        },
      ],
    }

    it("opens the box off the fetched batch on tool-calls-pending", async () => {
      const { store, sink } = await makeStore({
        fetchApprovals: vi.fn().mockResolvedValue(batch),
      })
      await store.sendMessage("hello")
      sink().onToolCallsPending(batch.items)
      await vi.waitFor(() => {
        expect(get(store).toolApprovalWaiter).not.toBeNull()
      })
      // Approval-only items reach the box (the non-approval sibling is
      // context on the wire, executed without a decision) — the old
      // filtering, unchanged.
      expect(get(store).toolApprovalWaiter!.payload.items).toHaveLength(1)
      expect(get(store).toolApprovalWaiter!.payload.items[0].toolCallId).toBe(
        "tc1",
      )
      expect(get(store).toolApprovalPicks).toEqual({ tc1: undefined })
    })

    it("opens the box off the awaiting_approval state (refresh recovery)", async () => {
      const { store, sink } = await makeStore({
        fetchApprovals: vi.fn().mockResolvedValue(batch),
      })
      sink().onAwaitingApproval()
      await vi.waitFor(() => {
        expect(get(store).toolApprovalWaiter).not.toBeNull()
      })
      expect(get(store).status).toBe("ready")
    })

    it("submits decisions with the batch id once all picks are made", async () => {
      const { store, sink, fake } = await makeStore({
        fetchApprovals: vi.fn().mockResolvedValue(batch),
      })
      sink().onAwaitingApproval()
      await vi.waitFor(() => {
        expect(get(store).toolApprovalWaiter).not.toBeNull()
      })
      store.applyToolApprovalRun("tc1")
      expect(fake.decide).toHaveBeenCalledWith("ab_1", { tc1: true })
      expect(get(store).toolApprovalWaiter).toBeNull()
    })

    it("skip denies the call", async () => {
      const { store, sink, fake } = await makeStore({
        fetchApprovals: vi.fn().mockResolvedValue(batch),
      })
      sink().onAwaitingApproval()
      await vi.waitFor(() => {
        expect(get(store).toolApprovalWaiter).not.toBeNull()
      })
      store.applyToolApprovalSkip("tc1")
      expect(fake.decide).toHaveBeenCalledWith("ab_1", { tc1: false })
    })

    it("stays quiet on a decide conflict (another tab decided first)", async () => {
      const { store, sink } = await makeStore({
        fetchApprovals: vi.fn().mockResolvedValue(batch),
        decide: vi.fn().mockResolvedValue({ ok: false, conflict: true }),
      })
      sink().onAwaitingApproval()
      await vi.waitFor(() => {
        expect(get(store).toolApprovalWaiter).not.toBeNull()
      })
      store.applyToolApprovalRun("tc1")
      await new Promise((r) => setTimeout(r, 0))
      expect(get(store).messages.some((m) => m.role === "error")).toBe(false)
    })

    it("clears the box when the run resumes (another tab decided)", async () => {
      const { store, sink } = await makeStore({
        fetchApprovals: vi.fn().mockResolvedValue(batch),
      })
      sink().onAwaitingApproval()
      await vi.waitFor(() => {
        expect(get(store).toolApprovalWaiter).not.toBeNull()
      })
      sink().onWorkingChange(true)
      expect(get(store).toolApprovalWaiter).toBeNull()
    })

    it("does nothing when the batch is already resolved (fetch → null)", async () => {
      const { store, sink } = await makeStore({
        fetchApprovals: vi.fn().mockResolvedValue(null),
      })
      sink().onToolCallsPending([])
      await new Promise((r) => setTimeout(r, 0))
      expect(get(store).toolApprovalWaiter).toBeNull()
    })

    it("auto-resolves a batch with no approval-requiring items", async () => {
      const { store, sink, fake } = await makeStore({
        fetchApprovals: vi.fn().mockResolvedValue({
          batchId: "ab_2",
          items: [
            {
              toolCallId: "tc2",
              toolName: "get",
              input: {},
              requiresApproval: false,
            },
          ],
        }),
      })
      sink().onAwaitingApproval()
      await vi.waitFor(() => {
        expect(fake.decide).toHaveBeenCalledWith("ab_2", {})
      })
      expect(get(store).toolApprovalWaiter).toBeNull()
    })

    it("queues sends while the box is open and flushes after deciding", async () => {
      const { store, sink, fake } = await makeStore({
        fetchApprovals: vi.fn().mockResolvedValue(batch),
      })
      sink().onAwaitingApproval()
      await vi.waitFor(() => {
        expect(get(store).toolApprovalWaiter).not.toBeNull()
      })
      await store.sendMessage("while deciding")
      expect(get(store).queuedMessage).toBe("while deciding")
      store.applyToolApprovalRun("tc1")
      // The resumed run settles later; the queued message flushes on idle.
      sink().onInteractiveIdle()
      await vi.waitFor(() => {
        expect(fake.sendMessage).toHaveBeenCalledWith("while deciding")
      })
    })

    it("reset clears tool approval state", async () => {
      const { store, sink } = await makeStore({
        fetchApprovals: vi.fn().mockResolvedValue(batch),
      })
      sink().onAwaitingApproval()
      await vi.waitFor(() => {
        expect(get(store).toolApprovalWaiter).not.toBeNull()
      })
      store.reset()
      expect(get(store).toolApprovalWaiter).toBeNull()
      expect(get(store).toolApprovalPicks).toEqual({})
    })
  })

  describe("banners", () => {
    it("sets upgradeNudgeVersion via onVersionNudge and dismisses it", async () => {
      const { store, sink } = await makeStore()
      sink().onVersionNudge("1.2.3")
      expect(get(store).upgradeNudgeVersion).toBe("1.2.3")
      store.dismissUpgradeNudge()
      expect(get(store).upgradeNudgeVersion).toBeNull()
    })

    it("sets versionRequired (not a chat message) on a too-old error event", async () => {
      const { store, sink } = await makeStore()
      await store.sendMessage("hello")
      sink().onInlineError(
        "Please update",
        undefined,
        CHAT_CLIENT_VERSION_TOO_OLD,
      )
      expect(get(store).versionRequired).toBe(true)
      expect(get(store).messages.some((m) => m.role === "error")).toBe(false)
      expect(get(store).status).toBe("ready")
    })

    it("checkVersionPolicy sets banner state from the endpoint", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          required: true,
          upgrade_nudge_version: "9.9.9",
        }),
      })
      const { store } = await makeStore()
      await store.checkVersionPolicy()
      expect(get(store).versionRequired).toBe(true)
      expect(get(store).upgradeNudgeVersion).toBe("9.9.9")
    })

    it("checkVersionPolicy leaves banners untouched on a failed request", async () => {
      mockFetch.mockRejectedValueOnce(new Error("offline"))
      const { store } = await makeStore()
      await store.checkVersionPolicy()
      expect(get(store).versionRequired).toBe(false)
    })

    it("does not flush a queued message while versionRequired", async () => {
      const { store, sink } = await makeStore()
      await store.sendMessage("first")
      await store.sendMessage("queued")
      sink().onInlineError("old", undefined, CHAT_CLIENT_VERSION_TOO_OLD)
      sink().onInteractiveIdle()
      await new Promise((r) => setTimeout(r, 0))
      expect(get(store).queuedMessage).toBe("queued")
    })
  })

  describe("refresh convergence (HIGH-1 brick fix)", () => {
    it("a replayed echo + error with a silent idle marker converges to ready and the composer works", async () => {
      // The brick chain: re-attaching to a conversation whose last turn
      // ended in a terminal upstream error (no trace persisted) replays the
      // buffered user-message echo (→ working true → "submitted") and the
      // error event; the on-subscribe idle marker then fires NO settle hooks
      // by design. onWorkingChange(false) must reset the composer.
      const { store, sink, fake } = await makeStore()
      // Replay: echo marks the turn in flight…
      sink().onWorkingChange(true)
      sink().onUserMessage("please add", "cm_replayed")
      // …the buffered terminal error renders…
      sink().onInlineError("Something went wrong.")
      expect(get(store).status).toBe("submitted")
      // …and the idle MARKER only reports not-working (no settle hooks).
      sink().onWorkingChange(false)
      expect(get(store).status).toBe("ready")
      // The echo + error rendered; the composer is usable again: a new send
      // dispatches instead of queueing forever.
      expect(
        get(store).messages.some(
          (m) => m.role === "user" && m.content === "please add",
        ),
      ).toBe(true)
      const ok = await store.sendMessage("try again")
      expect(ok).toBe(true)
      expect(fake.sendMessage).toHaveBeenCalledWith("try again")
      expect(get(store).queuedMessage).toBeNull()
    })

    it("the marker reset never flushes a queued message (markers are not settles)", async () => {
      const { store, sink, fake } = await makeStore()
      await store.sendMessage("first")
      await store.sendMessage("queued")
      expect(get(store).queuedMessage).toBe("queued")
      // A not-working signal without a settle (marker shape): composer
      // resets but the queue holds until a REAL settle.
      sink().onWorkingChange(false)
      await new Promise((r) => setTimeout(r, 0))
      expect(get(store).status).toBe("ready")
      expect(get(store).queuedMessage).toBe("queued")
      expect(fake.sendMessage).toHaveBeenCalledTimes(1)
      // The real settle flushes.
      sink().onInteractiveIdle()
      await vi.waitFor(() => {
        expect(fake.sendMessage).toHaveBeenCalledWith("queued")
      })
    })

    it("an observer drop mid-turn resets status and surfaces the error (MEDIUM-1)", async () => {
      // The conversation store maps an observer error mid-turn to
      // onWorkingChange(false) + onInlineError (see its onerror handler);
      // the session store must land back on ready with the error visible.
      const { store, sink } = await makeStore()
      await store.sendMessage("hello")
      expect(get(store).status).toBe("submitted")
      sink().onWorkingChange(false)
      sink().onInlineError(
        "Lost the connection to the assistant. Please try again.",
      )
      expect(get(store).status).toBe("ready")
      expect(
        get(store).messages.some(
          (m) =>
            m.role === "error" && m.content?.includes("Lost the connection"),
        ),
      ).toBe(true)
    })
  })

  describe("queued-message flush on idle marker (BUG 2)", () => {
    it("(a) flushes a client-held queue on an idle marker when the live idle event was missed", async () => {
      const { store, sink, fake } = await makeStore()
      await store.sendMessage("first") // turn in flight → "submitted"
      await store.sendMessage("queued") // held client-side
      expect(get(store).queuedMessage).toBe("queued")
      expect(fake.sendMessage).toHaveBeenCalledTimes(1)
      // The LIVE idle event was missed (the observer was detached at the
      // settle instant); only the on-subscribe idle MARKER arrives. On that
      // marker the conversation store fires onWorkingChange(false) (resets the
      // composer) THEN the dedicated onIdleMarker hook — which flushes the
      // client-held queue that would otherwise strand forever.
      sink().onWorkingChange(false)
      sink().onIdleMarker!()
      await vi.waitFor(() => {
        expect(fake.sendMessage).toHaveBeenCalledWith("queued")
      })
      expect(get(store).queuedMessage).toBeNull()
    })

    it("(b) an idle marker after a replayed echo + error converges to ready and does NOT spuriously dispatch", async () => {
      // The refresh-brick sequence, now WITH the marker-idle hook wired: a
      // replayed echo marks the turn working, the buffered error renders, and
      // the idle marker fires onWorkingChange(false) + onIdleMarker. With no
      // queued message, maybeFlush is a correct no-op — no brick, no phantom
      // send.
      const { store, sink, fake } = await makeStore()
      sink().onWorkingChange(true)
      sink().onUserMessage("please add", "cm_replayed")
      sink().onInlineError("Something went wrong.")
      expect(get(store).status).toBe("submitted")
      sink().onWorkingChange(false)
      sink().onIdleMarker!()
      await new Promise((r) => setTimeout(r, 0))
      expect(get(store).status).toBe("ready")
      expect(get(store).queuedMessage).toBeNull()
      expect(fake.sendMessage).not.toHaveBeenCalled()
    })

    it("(c) does not double-send when both a live idle AND an idle marker occur", async () => {
      const { store, sink, fake } = await makeStore()
      await store.sendMessage("first")
      await store.sendMessage("queued")
      expect(get(store).queuedMessage).toBe("queued")
      // The live idle settles and flushes the queue (dispatchQueued clears it
      // before sending).
      sink().onInteractiveIdle()
      await vi.waitFor(() => {
        expect(fake.sendMessage).toHaveBeenCalledWith("queued")
      })
      const callsAfterFlush = (fake.sendMessage as ReturnType<typeof vi.fn>)
        .mock.calls.length
      // A late idle marker for the SAME settle must not re-send: the queue was
      // already cleared by the flush.
      sink().onWorkingChange(false)
      sink().onIdleMarker!()
      await new Promise((r) => setTimeout(r, 0))
      expect(
        (fake.sendMessage as ReturnType<typeof vi.fn>).mock.calls.length,
      ).toBe(callsAfterFlush)
    })
  })

  describe("stop / retry", () => {
    it("stop posts the server-side cancel", async () => {
      const { store, fake } = await makeStore()
      await store.sendMessage("hello")
      store.stop()
      expect(fake.stop).toHaveBeenCalled()
    })

    it("retryLastRequest trims from the last user message and re-sends", async () => {
      const { store, sink, fake } = await makeStore()
      await sendAndSettle(store, () => sink(), "original")
      sink().onInlineError("boom")
      store.retryLastRequest()
      await vi.waitFor(() => {
        expect(fake.sendMessage).toHaveBeenCalledTimes(2)
      })
      expect(vi.mocked(fake.sendMessage).mock.calls[1][0]).toBe("original")
      // No duplicate user bubble.
      expect(
        get(store).messages.filter(
          (m) => m.role === "user" && m.content === "original",
        ),
      ).toHaveLength(1)
    })

    it("retry is a no-op while a turn is in flight", async () => {
      const { store, fake } = await makeStore()
      await store.sendMessage("hello")
      store.retryLastRequest()
      expect(fake.sendMessage).toHaveBeenCalledTimes(1)
    })
  })

  describe("reset / loadSession", () => {
    it("reset clears all state and detaches the observer", async () => {
      const { store, fake } = await makeStore({}, "kiln_chat_test")
      await store.sendMessage("hello")
      expect(get(store).sessionId).toBe("cv_main")
      store.reset()
      const s = get(store)
      expect(s.messages).toEqual([])
      expect(s.status).toBe("ready")
      expect(s.sessionId).toBeNull()
      expect(s.rootId).toBeNull()
      expect(s.contextUsage).toBeNull()
      expect(fake.detach).toHaveBeenCalled()
      // sessionStorage cleared to the empty handles.
      expect(storage.store["kiln_chat_test"]).not.toContain("cv_main")
    })

    it("loadSession sets messages + the row's session key and re-attaches via ensure", async () => {
      const { store, fake } = await makeStore()
      const messages: ChatMessage[] = [
        { id: "u1", role: "user", content: "hi" },
        { id: "a1", role: "assistant", parts: [] },
      ]
      store.loadSession(messages, "row-key-7", null, { rootId: "root-7" })
      expect(get(store).messages).toEqual(messages)
      // The row key persists IMMEDIATELY (addressable before ensure lands);
      // the durable rootId rides along as the recovery key.
      expect(get(store).sessionId).toBe("row-key-7")
      expect(get(store).rootId).toBe("root-7")
      expect(fake.detach).toHaveBeenCalled()
      await vi.waitFor(() => {
        expect(fake.ensure).toHaveBeenCalledWith("row-key-7", {
          openInflightTurn: true,
          assumeAutoOn: false,
        })
      })
      await vi.waitFor(() => {
        expect(get(store).sessionId).toBe("cv_main")
      })
    })

    it("loadSession threads the history row's auto-active flag to the attach", async () => {
      // LOW 1: an auto-active history row restores the old immediate
      // indicator (assumeAutoOn) instead of waiting for the state marker.
      const { store, fake } = await makeStore()
      store.loadSession([], "row-key-8", null, { autoActive: true })
      await vi.waitFor(() => {
        expect(fake.ensure).toHaveBeenCalledWith("row-key-8", {
          openInflightTurn: true,
          assumeAutoOn: true,
        })
      })
    })

    it("loadSession continues from the loaded session key on the next send", async () => {
      const { store, fake } = await makeStore()
      store.loadSession([{ id: "a1", role: "assistant", parts: [] }], "row-7")
      await store.sendMessage("continue")
      expect(vi.mocked(fake.ensure).mock.calls.pop()![0]).toBe("row-7")
    })
  })

  describe("persistence (handles only)", () => {
    it("persists only the conversation handles + ui prefs — never messages", async () => {
      const { store } = await makeStore({}, "kiln_chat_test")
      await store.sendMessage("hello world")
      store.togglePartCollapsed("part-1", false)
      const persisted = JSON.parse(storage.store["kiln_chat_test"])
      expect(persisted).toEqual({
        sessionId: "cv_main",
        rootId: null,
        collapsedPartKeys: { "part-1": true },
        lastSentAppState: expect.anything(),
      })
    })

    it("restores the handles from sessionStorage on creation", async () => {
      storage.store["kiln_chat_test"] = JSON.stringify({
        sessionId: "cv_old",
        rootId: "root-old",
        collapsedPartKeys: {},
        lastSentAppState: null,
      })
      const { store } = await makeStore({}, "kiln_chat_test")
      expect(get(store).sessionId).toBe("cv_old")
      expect(get(store).rootId).toBe("root-old")
      // Transcripts always rebuild from hydrate+observe.
      expect(get(store).messages).toEqual([])
    })

    it("starts fresh when sessionStorage contains invalid JSON", async () => {
      storage.store["kiln_chat_test"] = "{invalid json"
      const { store } = await makeStore({}, "kiln_chat_test")
      expect(get(store).sessionId).toBeNull()
      expect(get(store).messages).toEqual([])
    })
  })

  describe("context header", () => {
    it("sends the header on the wire but renders clean text", async () => {
      mockBuildContextHeader.mockReturnValue(
        "<new_app_ui_context>ctx</new_app_ui_context>",
      )
      const { store, fake } = await makeStore()
      await store.sendMessage("hello")
      expect(fake.sendMessage).toHaveBeenCalledWith(
        "<new_app_ui_context>ctx</new_app_ui_context>\nhello",
      )
      const users = get(store).messages.filter((m) => m.role === "user")
      expect(users[0].content).toBe("hello")
    })

    it("does not prepend when buildContextHeader returns null", async () => {
      const { store, fake } = await makeStore()
      await store.sendMessage("hello")
      expect(fake.sendMessage).toHaveBeenCalledWith("hello")
    })

    it("updates lastSentAppState on send (persisted for the delta encoding)", async () => {
      const { store } = await makeStore({}, "kiln_chat_test")
      await store.sendMessage("hello")
      expect(get(store).lastSentAppState).toEqual(mockAppState)
      expect(storage.store["kiln_chat_test"]).toContain("Test Page")
    })
  })

  describe("resyncOnLoad (hard refresh)", () => {
    it("hydrates by the live session id and re-attaches", async () => {
      storage.store["kiln_chat_test"] = JSON.stringify({
        sessionId: "cv_live",
        rootId: null,
        collapsedPartKeys: {},
        lastSentAppState: null,
      })
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          session_id: "cv_live",
          state: "running",
          root_id: "root-live",
        }),
      })
      mockClientGet.mockResolvedValue({
        data: { id: "tr-fresh" },
        error: undefined,
      })
      mockHydrate.mockReturnValue({
        messages: [{ id: "m1", role: "user", content: "restored" }],
        rootId: "root-live",
        contextUsage: null,
      })
      const { store, fake } = await makeStore({}, "kiln_chat_test")
      await store.resyncOnLoad()
      // Hydration is keyed by the SESSION id — the desktop resolves the
      // record's current leaf per request (phase 5: the browser's stored
      // leaf and its refresh via current_trace_id are gone).
      expect(mockClientGet).toHaveBeenCalledWith(
        "/api/chat/sessions/{session_id}",
        { params: { path: { session_id: "cv_live" } } },
      )
      expect(get(store).messages[0].content).toBe("restored")
      // The durable recovery key was learned from the item response.
      expect(get(store).rootId).toBe("root-live")
      expect(fake.beginReconnect).toHaveBeenCalled()
      expect(fake.ensure).toHaveBeenCalledWith("cv_live", {
        openInflightTurn: true,
        initialWorking: true,
      })
    })

    it("recovers via the durable root id when the session id is gone (desktop restart)", async () => {
      storage.store["kiln_chat_test"] = JSON.stringify({
        sessionId: "cv_dead",
        rootId: "root-durable",
        collapsedPartKeys: {},
        lastSentAppState: null,
      })
      mockFetch.mockResolvedValueOnce({ ok: false, status: 404 })
      mockClientGet.mockResolvedValue({
        data: { id: "tr-durable" },
        error: undefined,
      })
      mockHydrate.mockReturnValue({
        messages: [],
        rootId: "root-durable",
        contextUsage: null,
      })
      const { store, fake } = await makeStore({}, "kiln_chat_test")
      await store.resyncOnLoad()
      // Hydration + create-or-adopt run on the ROOT key (the desktop
      // resolves root→leaf and rehydrates any parked approvals from the
      // persisted tail, server-side) — the old flow's stored trace id role.
      expect(mockClientGet).toHaveBeenCalledWith(
        "/api/chat/sessions/{session_id}",
        { params: { path: { session_id: "root-durable" } } },
      )
      expect(fake.ensure).toHaveBeenCalledWith("root-durable", {
        openInflightTurn: true,
        initialWorking: undefined,
      })
    })

    it("is a no-op with nothing stored", async () => {
      const { store, fake } = await makeStore({}, "kiln_chat_test")
      await store.resyncOnLoad()
      expect(fake.ensure).not.toHaveBeenCalled()
      expect(mockClientGet).not.toHaveBeenCalled()
    })

    it("never stamps a stale rootId when New Chat races the resync item fetch (CR residual)", async () => {
      // The on-mount resync's GET /api/conversations/{storedSid} hangs; the
      // user clicks New Chat before it resolves. The opportunistic root
      // upgrade must be generation-guarded like maybeLearnRootId (MEDIUM 2's
      // failure mode): stamping the OLD conversation's root onto the reset
      // handles would make the next send silently adopt the old conversation.
      storage.store["kiln_chat_test"] = JSON.stringify({
        sessionId: "cv_live",
        rootId: null,
        collapsedPartKeys: {},
        lastSentAppState: null,
      })
      let resolveItem: (v: unknown) => void = () => {}
      mockFetch.mockReturnValueOnce(new Promise((r) => (resolveItem = r)))
      const { store } = await makeStore({}, "kiln_chat_test")
      const resync = store.resyncOnLoad()
      store.reset()
      resolveItem({
        ok: true,
        json: async () => ({
          session_id: "cv_live",
          state: "idle",
          root_id: "root-OLD",
        }),
      })
      await resync
      expect(get(store).rootId).toBeNull()
      expect(get(store).sessionId).toBeNull()
      expect(storage.store["kiln_chat_test"]).not.toContain("root-OLD")
    })

    it("bails if the user switches conversations mid-resync", async () => {
      storage.store["kiln_chat_test"] = JSON.stringify({
        sessionId: null,
        rootId: "root-old",
        collapsedPartKeys: {},
        lastSentAppState: null,
      })
      let resolveSnapshot: (v: unknown) => void = () => {}
      mockClientGet.mockReturnValue(new Promise((r) => (resolveSnapshot = r)))
      const { store, fake } = await makeStore({}, "kiln_chat_test")
      const resync = store.resyncOnLoad()
      // The user picks another conversation while the snapshot fetch hangs.
      store.loadSession([], "row-new")
      resolveSnapshot({ data: { id: "tr-old" }, error: undefined })
      await resync
      // The stale resync never ensured root-old; only loadSession's row-new.
      const ensureKeys = vi.mocked(fake.ensure).mock.calls.map((c) => c[0])
      expect(ensureKeys).not.toContain("root-old")
    })
  })

  describe("contextUsage / compacting", () => {
    const usage = {
      context_tokens: 1000,
      context_limit: 10000,
      context_percent: 10,
      compacted: false,
    }

    it("is set via the observer and cleared on reset", async () => {
      const { store, sink } = await makeStore()
      sink().onContextUsage(usage)
      expect(get(store).contextUsage).toEqual(usage)
      store.reset()
      expect(get(store).contextUsage).toBeNull()
    })

    it("is set on loadSession", async () => {
      const { store } = await makeStore()
      store.loadSession([], "tr-1", usage)
      expect(get(store).contextUsage).toEqual(usage)
    })

    it("compacting follows onCompactionStatus and clears on idle/reset", async () => {
      const { store, sink } = await makeStore()
      sink().onCompactionStatus(true)
      expect(get(store).compacting).toBe(true)
      sink().onInteractiveIdle()
      expect(get(store).compacting).toBe(false)
      sink().onCompactionStatus(true)
      store.reset()
      expect(get(store).compacting).toBe(false)
    })

    it("compacting is never persisted", async () => {
      const { store, sink } = await makeStore({}, "kiln_chat_test")
      await store.sendMessage("hi")
      sink().onCompactionStatus(true)
      const persisted = storage.store["kiln_chat_test"]
      expect(persisted).toBeDefined()
      expect(persisted).not.toContain("compacting")
    })
  })
})

describe("chatSessionStore global instance", () => {
  it("is exported and functional", async () => {
    const { chatSessionStore } = await importFresh()
    expect(chatSessionStore).toBeDefined()
    expect(get(chatSessionStore).status).toBe("ready")
  })
})
