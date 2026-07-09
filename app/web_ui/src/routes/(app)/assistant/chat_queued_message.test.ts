// @vitest-environment jsdom
//
// Integration test for the queued-message composer behavior: a message typed
// while a turn is in flight is held above the composer (not blocked), with
// send-now / edit / discard controls, and the textarea stays usable so the next
// message can be queued. Renders the real ``chat.svelte`` against a fake store.
import { describe, it, expect, afterEach, vi } from "vitest"
import { render, cleanup, fireEvent } from "@testing-library/svelte"
import { writable, type Readable } from "svelte/store"
import type { ContextUsage } from "$lib/chat/streaming_chat"
import type {
  ChatSessionState,
  ChatSessionStore,
} from "$lib/chat/chat_session_store"

vi.mock("posthog-js", () => ({
  default: { capture: vi.fn() },
}))

vi.mock("$lib/api_client", () => ({
  base_url: "http://localhost:8757",
  client: { GET: vi.fn(), POST: vi.fn() },
}))

// chat.svelte reads several readable stores off the auto conversation store
// singleton at component init (folded into conversation_store.ts in phase 3);
// provide inert ones so the component mounts in isolation, keeping the rest
// of the module (conversation_store, tab helpers) real.
vi.mock("$lib/chat/conversation_store", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("$lib/chat/conversation_store")>()
  return {
    ...actual,
    auto_conversation_store: {
      autoModeOn: writable(false),
      armed: writable(false),
      working: writable(false),
      reconnecting: writable(false),
      retry: writable(null),
      sessionId: writable(null),
      offReason: writable(null),
      connection: writable("idle"),
      bind: vi.fn(),
      detach: vi.fn(),
      requestEnable: vi.fn().mockResolvedValue({ ok: true }),
      decline: vi.fn().mockResolvedValue(undefined),
      sendMessage: vi.fn().mockResolvedValue({ ok: true }),
      stop: vi.fn().mockResolvedValue(undefined),
      resolve: vi.fn().mockResolvedValue(null),
      beginReconnect: vi.fn(),
      attach: vi.fn(),
      arm: vi.fn(),
      disarm: vi.fn(),
      _close: vi.fn(),
    },
  }
})

vi.mock("$lib/stores", () => ({
  chat_cost_disclaimer_acknowledged: writable(true),
  projects: writable([]),
  current_project: writable(null),
}))

const Chat = (await import("./chat.svelte")).default

afterEach(() => {
  cleanup()
})

function baseState(
  overrides: Partial<ChatSessionState> = {},
): ChatSessionState {
  return {
    messages: [],
    collapsedPartKeys: {},
    lastSentAppState: null,
    contextUsage: null as ContextUsage | null,
    status: "ready",
    abortController: null,
    toolApprovalWaiter: null,
    toolApprovalPicks: {},
    toolExecuting: false,
    showActivityIndicator: false,
    compacting: false,
    autoWorking: false,
    retry: null,
    upgradeNudgeVersion: null,
    versionRequired: false,
    queuedMessage: null,
    ...overrides,
  }
}

function makeFakeStore(initial: ChatSessionState) {
  const state = writable<ChatSessionState>(initial)
  const noop = () => {}
  const sendMessage = vi.fn().mockResolvedValue(true)
  const sendQueuedNow = vi.fn()
  const clearQueued = vi.fn()
  const store = {
    subscribe: (state as Readable<ChatSessionState>).subscribe,
    sendMessage,
    sendQueuedNow,
    clearQueued,
    stop: noop,
    retryLastRequest: noop,
    reset: noop,
    loadSession: noop,
    resyncOnLoad: vi.fn().mockResolvedValue(undefined),
    togglePartCollapsed: noop,
    pushInlineError: noop,
    applyToolApprovalRun: noop,
    applyToolApprovalSkip: noop,
    dismissUpgradeNudge: noop,
    checkVersionPolicy: vi.fn().mockResolvedValue(undefined),
    onConsentNeeded: null,
    onAutoModeConsentNeeded: null,
  } as unknown as ChatSessionStore
  return { store, state, sendMessage, sendQueuedNow, clearQueued }
}

describe("chat.svelte queued message composer", () => {
  it("shows the queued message banner with the queued text", () => {
    const { store } = makeFakeStore(
      baseState({ status: "submitted", queuedMessage: "hold this for me" }),
    )
    const { getByText, getByLabelText } = render(Chat, { props: { store } })
    expect(getByText("hold this for me")).toBeTruthy()
    expect(getByLabelText("Send queued message now")).toBeTruthy()
    expect(getByLabelText("Edit queued message")).toBeTruthy()
    expect(getByLabelText("Discard queued message")).toBeTruthy()
  })

  it("does not show the banner when nothing is queued", () => {
    const { store } = makeFakeStore(baseState({ status: "submitted" }))
    const { queryByLabelText } = render(Chat, { props: { store } })
    expect(queryByLabelText("Send queued message now")).toBeNull()
  })

  it("calls sendQueuedNow when the send-now button is clicked", async () => {
    const { store, sendQueuedNow } = makeFakeStore(
      baseState({ status: "submitted", queuedMessage: "go now" }),
    )
    const { getByLabelText } = render(Chat, { props: { store } })
    await fireEvent.click(getByLabelText("Send queued message now"))
    expect(sendQueuedNow).toHaveBeenCalledTimes(1)
  })

  it("calls clearQueued when the discard button is clicked", async () => {
    const { store, clearQueued } = makeFakeStore(
      baseState({ status: "submitted", queuedMessage: "never mind" }),
    )
    const { getByLabelText } = render(Chat, { props: { store } })
    await fireEvent.click(getByLabelText("Discard queued message"))
    expect(clearQueued).toHaveBeenCalledTimes(1)
  })

  it("moves the queued text into the composer when edit is clicked", async () => {
    const { store, clearQueued } = makeFakeStore(
      baseState({ status: "submitted", queuedMessage: "let me fix this" }),
    )
    const { getByLabelText } = render(Chat, { props: { store } })
    await fireEvent.click(getByLabelText("Edit queued message"))
    const textarea = getByLabelText("Chat message") as HTMLTextAreaElement
    expect(textarea.value).toBe("let me fix this")
    expect(clearQueued).toHaveBeenCalledTimes(1)
  })

  it("keeps the composer enabled while a turn is in flight so messages can queue", () => {
    const { store } = makeFakeStore(baseState({ status: "streaming" }))
    const { getByLabelText } = render(Chat, { props: { store } })
    const textarea = getByLabelText("Chat message") as HTMLTextAreaElement
    expect(textarea.disabled).toBe(false)
  })

  it("disables the composer only when a newer client version is required", () => {
    const { store } = makeFakeStore(
      baseState({ status: "ready", versionRequired: true }),
    )
    const { getByLabelText } = render(Chat, { props: { store } })
    const textarea = getByLabelText("Chat message") as HTMLTextAreaElement
    expect(textarea.disabled).toBe(true)
  })
})
