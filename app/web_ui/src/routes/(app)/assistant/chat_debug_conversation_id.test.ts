// @vitest-environment jsdom
//
// The copy-conversation-id widget in the chat footer. Svelte 4 onMount
// callbacks do not run under vitest, so these tests set the debug-status store
// directly; load_chat_debug_status has its own unit tests.
import { describe, it, expect, afterEach, beforeEach, vi } from "vitest"
import { render, cleanup, fireEvent, waitFor } from "@testing-library/svelte"
import { writable, type Readable } from "svelte/store"
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

vi.mock("$lib/chat/conversation_store", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("$lib/chat/conversation_store")>()
  const { writable } = await import("svelte/store")
  return {
    ...actual,
    main_conversation_store: {
      autoModeOn: writable(false),
      armed: writable(false),
      working: writable(false),
      reconnecting: writable(false),
      retry: writable(null),
      sessionId: writable("cv_debug123"),
      offReason: writable(null),
      connection: writable("idle"),
      bind: vi.fn(),
      detach: vi.fn(),
      requestEnable: vi.fn().mockResolvedValue({ ok: true }),
      decline: vi.fn().mockResolvedValue(undefined),
      sendMessage: vi.fn().mockResolvedValue({ ok: true }),
      stop: vi.fn().mockResolvedValue(undefined),
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

async function loadChat(devTools: boolean) {
  vi.resetModules()
  vi.doMock("$lib/utils/dev_tools", () => ({ dev_tools_enabled: devTools }))
  const { chat_debug_log_enabled } = await import("$lib/chat/chat_debug_status")
  const Chat = (await import("./chat.svelte")).default
  return { Chat, chat_debug_log_enabled }
}

function makeFakeStore(
  overrides: Partial<ChatSessionState> = {},
): ChatSessionStore {
  const state = writable<ChatSessionState>({
    messages: [],
    collapsedPartKeys: {},
    lastSentAppState: null,
    contextUsage: null,
    status: "ready",
    sessionId: null,
    rootId: null,
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
  })
  const noop = () => {}
  return {
    subscribe: (state as Readable<ChatSessionState>).subscribe,
    sendMessage: vi.fn().mockResolvedValue(true),
    sendQueuedNow: noop,
    clearQueued: noop,
    stop: noop,
    retryLastRequest: noop,
    reset: noop,
    loadSession: noop,
    resyncOnLoad: vi.fn().mockResolvedValue(undefined),
    checkVersionPolicy: vi.fn().mockResolvedValue(undefined),
    togglePartCollapsed: noop,
    pushInlineError: noop,
    applyToolApprovalRun: noop,
    applyToolApprovalSkip: noop,
    onConsentNeeded: null,
    onAutoModeConsentNeeded: null,
  } as unknown as ChatSessionStore
}

const COPY_LABEL = "Copy conversation id"

let writeText: ReturnType<typeof vi.fn>

beforeEach(() => {
  writeText = vi.fn().mockResolvedValue(undefined)
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText },
    configurable: true,
  })
})

afterEach(() => {
  cleanup()
})

describe("chat.svelte copy-conversation-id widget", () => {
  it("shows the conversation id and copies it on click", async () => {
    const { Chat, chat_debug_log_enabled } = await loadChat(true)
    chat_debug_log_enabled.set(true)

    const { getByLabelText } = render(Chat, {
      props: { store: makeFakeStore() },
    })
    const button = getByLabelText(COPY_LABEL)
    expect(button.textContent?.trim()).toBe("cv_debug123")

    await fireEvent.click(button)
    expect(writeText).toHaveBeenCalledWith("cv_debug123")
    await waitFor(() => expect(button.textContent?.trim()).toBe("copied"))
  })

  it("stays hidden while the debug log is off", async () => {
    const { Chat, chat_debug_log_enabled } = await loadChat(true)
    chat_debug_log_enabled.set(false)

    const { queryByLabelText } = render(Chat, {
      props: { store: makeFakeStore() },
    })
    expect(queryByLabelText(COPY_LABEL)).toBeNull()
  })

  it("stays hidden without dev tools", async () => {
    const { Chat, chat_debug_log_enabled } = await loadChat(false)
    chat_debug_log_enabled.set(true)

    const { queryByLabelText } = render(Chat, {
      props: { store: makeFakeStore() },
    })
    expect(queryByLabelText(COPY_LABEL)).toBeNull()
  })
})

describe("chat.svelte context usage gauge", () => {
  const contextUsage = {
    context_tokens: 50_000,
    context_limit: 200_000,
    context_percent: 25,
    compacted: false,
  }

  it("shows the gauge with dev tools", async () => {
    const { Chat } = await loadChat(true)
    const { queryByTestId } = render(Chat, {
      props: { store: makeFakeStore({ contextUsage }) },
    })
    expect(queryByTestId("context-usage-gauge")).not.toBeNull()
  })

  it("hides the gauge without dev tools", async () => {
    const { Chat } = await loadChat(false)
    const { queryByTestId } = render(Chat, {
      props: { store: makeFakeStore({ contextUsage }) },
    })
    expect(queryByTestId("context-usage-gauge")).toBeNull()
  })
})
