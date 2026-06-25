// @vitest-environment jsdom
//
// Integration test (Phase 5): the "Summarizing earlier messages…" compaction
// indicator must be visible during the PRE-INFERENCE window — i.e. when the
// store's ``compacting`` flag is true even though there is NO assistant message
// yet (the last message is the just-sent user message) and the assistant
// activity/streaming flags are not set. A live-testing regression found the
// indicator never rendered because every per-message mount was gated behind an
// existing assistant bubble; this test renders the real ``chat.svelte`` against
// that exact state to guard the standalone activity row.
import { describe, it, expect, afterEach, vi } from "vitest"
import { render, cleanup } from "@testing-library/svelte"
import { writable, type Readable } from "svelte/store"
import type { ChatMessage, ContextUsage } from "$lib/chat/streaming_chat"
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

// chat.svelte reads several readable stores off the auto_run_store singleton at
// component init; provide inert ones so the component mounts in isolation.
vi.mock("$lib/chat/auto_run_store", () => ({
  auto_run_store: {
    autoModeOn: writable(false),
    armed: writable(false),
    working: writable(false),
    reconnecting: writable(false),
    runId: writable(null),
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
  },
}))

vi.mock("$lib/stores", () => ({
  chat_cost_disclaimer_acknowledged: writable(true),
  projects: writable([]),
  current_project: writable(null),
}))

const Chat = (await import("./chat.svelte")).default

afterEach(() => {
  cleanup()
})

const SUMMARIZING = /Summarizing earlier messages to free up context/i

function baseState(
  overrides: Partial<ChatSessionState> = {},
): ChatSessionState {
  return {
    messages: [],
    collapsedPartKeys: {},
    lastSentAppState: null,
    contextUsage: null as ContextUsage | null,
    status: "submitted",
    abortController: null,
    toolApprovalWaiter: null,
    toolApprovalPicks: {},
    toolExecuting: false,
    showActivityIndicator: false,
    compacting: false,
    autoWorking: false,
    ...overrides,
  }
}

// A minimal store satisfying ``ChatSessionStore`` with only the surface
// ``chat.svelte`` touches during render. The state writable is returned so the
// test can flip ``compacting`` / push content and observe the DOM.
function makeFakeStore(initial: ChatSessionState): {
  store: ChatSessionStore
  state: ReturnType<typeof writable<ChatSessionState>>
} {
  const state = writable<ChatSessionState>(initial)
  const noop = () => {}
  const store = {
    subscribe: (state as Readable<ChatSessionState>).subscribe,
    sendMessage: vi.fn().mockResolvedValue(true),
    stop: noop,
    retryLastRequest: noop,
    reset: noop,
    loadSession: noop,
    resyncOnLoad: vi.fn().mockResolvedValue(undefined),
    togglePartCollapsed: noop,
    pushInlineError: noop,
    applyToolApprovalRun: noop,
    applyToolApprovalSkip: noop,
    onConsentNeeded: null,
    onAutoModeConsentNeeded: null,
  } as unknown as ChatSessionStore
  return { store, state }
}

describe("chat.svelte compaction indicator (Phase 5 integration)", () => {
  const userMsg: ChatMessage = {
    id: "u1",
    role: "user",
    content: "hello",
  }

  it("renders the summarizing indicator when compacting with NO assistant message", () => {
    // The exact pre-inference state: a sent user message, an active turn
    // (status submitted), compacting=true, and crucially NO assistant bubble
    // and no activity flags set.
    const { store } = makeFakeStore(
      baseState({ messages: [userMsg], compacting: true }),
    )
    const { getByText } = render(Chat, { props: { store } })
    expect(getByText(SUMMARIZING)).toBeTruthy()
  })

  it("clears the indicator once an assistant message with content arrives", async () => {
    const { store, state } = makeFakeStore(
      baseState({ messages: [userMsg], compacting: true }),
    )
    const { queryByText } = render(Chat, { props: { store } })
    expect(queryByText(SUMMARIZING)).toBeTruthy()

    // The store clears ``compacting`` when real assistant content streams.
    state.set(
      baseState({
        messages: [
          userMsg,
          {
            id: "a1",
            role: "assistant",
            parts: [{ type: "text", text: "response" }],
          },
        ],
        status: "streaming",
        compacting: false,
      }),
    )
    await Promise.resolve()
    expect(queryByText(SUMMARIZING)).toBeNull()
  })

  it("does not render the indicator when not compacting", () => {
    const { store } = makeFakeStore(
      baseState({ messages: [userMsg], compacting: false }),
    )
    const { queryByText } = render(Chat, { props: { store } })
    expect(queryByText(SUMMARIZING)).toBeNull()
  })
})
