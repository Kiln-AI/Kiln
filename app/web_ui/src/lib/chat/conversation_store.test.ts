// @vitest-environment jsdom
//
// Port of subagent_store.test.ts (deleted in phase 2 with the store it
// covered): the same behavior contracts, asserted against the unified
// conversation store — new endpoints (/api/conversations), new vocabulary
// (session ids, RunState strings, conversation-state events).
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest"
import { get } from "svelte/store"
import {
  createConversationStore,
  isTerminalState,
  shouldCollapseChildTabs,
  visibleChildTabs,
  CHILD_TAB_OVERFLOW_LIMIT,
  type ConversationItem,
  type ConversationStore,
} from "./conversation_store"

vi.mock("$lib/api_client", () => ({
  base_url: "http://localhost:8757",
}))

// A controllable fake EventSource installed on globalThis (same pattern as
// auto_run_store.test.ts). Records the construction URL and close() calls;
// tests drive message/open/error.
class FakeEventSource {
  static instances: FakeEventSource[] = []
  url: string
  closed = false
  onopen: ((this: EventSource, ev: Event) => void) | null = null
  onmessage: ((this: EventSource, ev: MessageEvent) => void) | null = null
  onerror: ((this: EventSource, ev: Event) => void) | null = null

  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
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

function child(
  id: string,
  overrides: Partial<ConversationItem> = {},
): ConversationItem {
  return {
    session_id: id,
    kind: "subagent",
    state: "running",
    name: `Agent ${id}`,
    agent_type: "general",
    parent_session_id: "trace:parent-1",
    current_trace_id: `trace-${id}`,
    auto_flag: false,
    rounds_used: 0,
    report_available: false,
    report_delivered: false,
    ...overrides,
  }
}

function jsonResponse(data: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: () => Promise.resolve(data),
  } as unknown as Response
}

function sseResponse(events: unknown[]): Response {
  const chunks = events.map((e) => `data: ${JSON.stringify(e)}\n`)
  const encoder = new TextEncoder()
  let i = 0
  const reader = {
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
  return {
    ok: true,
    status: 200,
    body: { getReader: () => reader },
  } as unknown as Response
}

const flush = () => new Promise<void>((resolve) => setTimeout(resolve, 0))

describe("conversation_store", () => {
  let store: ConversationStore

  beforeEach(() => {
    // @ts-expect-error install fake on global
    globalThis.EventSource = FakeEventSource
    FakeEventSource.reset()
    store = createConversationStore()
  })

  afterEach(() => {
    store.reset()
    store.disconnect()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  describe("syncForConversation", () => {
    it("fetches the children for the parent handle and replaces the list", async () => {
      const fetchMock = vi
        .fn()
        .mockResolvedValue(jsonResponse([child("cv_1"), child("cv_2")]))
      vi.stubGlobal("fetch", fetchMock)

      await store.syncForConversation("trace-leaf")

      expect(fetchMock).toHaveBeenCalledWith(
        "http://localhost:8757/api/conversations?parent=trace-leaf",
      )
      expect(get(store.children).map((c) => c.session_id)).toEqual([
        "cv_1",
        "cv_2",
      ])
    })

    it("dedupes by parent handle (no refetch for the same value)", async () => {
      const fetchMock = vi.fn().mockResolvedValue(jsonResponse([child("cv_1")]))
      vi.stubGlobal("fetch", fetchMock)

      await store.syncForConversation("trace-leaf")
      await store.syncForConversation("trace-leaf")

      expect(fetchMock).toHaveBeenCalledTimes(1)
    })

    it("clears the list (and the selection) for a null parent", async () => {
      const fetchMock = vi.fn().mockResolvedValue(jsonResponse([child("cv_1")]))
      vi.stubGlobal("fetch", fetchMock)

      await store.syncForConversation("trace-leaf")
      store.select("cv_1")
      await store.syncForConversation(null)

      expect(get(store.children)).toEqual([])
      expect(get(store.selectedId)).toBeNull()
    })

    it("clears the selection when the new list lacks the selected child", async () => {
      // Route by URL: select() also starts an observation (item re-fetch +
      // session hydration + events stream), which must not race the list
      // fetches out of order.
      const fetchMock = vi.fn().mockImplementation((url: string) => {
        const u = String(url)
        if (u.includes("parent=trace-a")) {
          return Promise.resolve(jsonResponse([child("cv_1")]))
        }
        if (u.includes("parent=trace-b")) {
          return Promise.resolve(jsonResponse([child("cv_other")]))
        }
        if (u.includes("/api/chat/sessions/")) {
          return Promise.resolve(
            jsonResponse({ id: "trace-cv_1", task_run: { trace: [] } }),
          )
        }
        if (u.endsWith("/api/conversations/cv_1")) {
          return Promise.resolve(jsonResponse(child("cv_1")))
        }
        return Promise.resolve(sseResponse([]))
      })
      vi.stubGlobal("fetch", fetchMock)

      await store.syncForConversation("trace-a")
      store.select("cv_1")
      await store.syncForConversation("trace-b")

      expect(get(store.children).map((c) => c.session_id)).toEqual(["cv_other"])
      expect(get(store.selectedId)).toBeNull()
    })
  })

  describe("state firehose", () => {
    it("connects to the firehose and updates a known child from state events", async () => {
      const fetchMock = vi.fn().mockResolvedValue(jsonResponse([child("cv_1")]))
      vi.stubGlobal("fetch", fetchMock)
      await store.syncForConversation("trace-leaf")

      store.connect()
      const source = FakeEventSource.latest()
      expect(source.url).toBe("http://localhost:8757/api/conversations/events")
      source.open()
      expect(get(store.connection)).toBe("open")

      source.message({
        type: "conversation-state",
        session_id: "cv_1",
        kind: "subagent",
        state: "completed",
        auto_flag: false,
        name: "Agent cv_1",
        report_available: true,
      })

      const updated = get(store.children)[0]
      expect(updated.state).toBe("completed")
      expect(updated.report_available).toBe(true)
    })

    it("ignores state events for non-subagent kinds", async () => {
      // Phase 3-4 forward-compat: parent conversations will share the
      // firehose; their state changes must never disturb the children strip.
      const fetchMock = vi.fn().mockResolvedValue(jsonResponse([child("cv_1")]))
      vi.stubGlobal("fetch", fetchMock)
      await store.syncForConversation("trace-leaf")

      store.connect()
      FakeEventSource.latest().message({
        type: "conversation-state",
        session_id: "cv_parent",
        kind: "auto",
        state: "running",
        auto_flag: true,
      })
      await flush()

      // No refetch for the unknown non-child, and the list is untouched.
      expect(fetchMock).toHaveBeenCalledTimes(1)
      expect(get(store.children).map((c) => c.session_id)).toEqual(["cv_1"])
    })

    it("re-fetches the list when a state event arrives for an unknown child", async () => {
      const fetchMock = vi
        .fn()
        .mockResolvedValueOnce(jsonResponse([]))
        .mockResolvedValueOnce(jsonResponse([child("cv_new")]))
      vi.stubGlobal("fetch", fetchMock)
      await store.syncForConversation("trace-leaf")

      store.connect()
      FakeEventSource.latest().message({
        type: "conversation-state",
        session_id: "cv_new",
        kind: "subagent",
        state: "running",
        auto_flag: false,
      })
      await flush()

      expect(fetchMock).toHaveBeenCalledTimes(2)
      expect(fetchMock.mock.calls[1][0]).toBe(
        "http://localhost:8757/api/conversations?parent=trace-leaf",
      )
      expect(get(store.children).map((c) => c.session_id)).toEqual(["cv_new"])
    })

    it("reconnects after an error while active", async () => {
      vi.useFakeTimers()
      try {
        store.connect()
        const first = FakeEventSource.latest()
        first.onerror?.call(first as unknown as EventSource, new Event("error"))
        expect(get(store.connection)).toBe("errored")
        vi.advanceTimersByTime(2000)
        expect(FakeEventSource.instances.length).toBe(2)
      } finally {
        vi.useRealTimers()
      }
    })

    it("does not reconnect after disconnect", () => {
      vi.useFakeTimers()
      try {
        store.connect()
        const source = FakeEventSource.latest()
        store.disconnect()
        expect(source.closed).toBe(true)
        source.onerror?.call(
          source as unknown as EventSource,
          new Event("error"),
        )
        vi.advanceTimersByTime(5000)
        expect(FakeEventSource.instances.length).toBe(1)
        expect(get(store.connection)).toBe("idle")
      } finally {
        vi.useRealTimers()
      }
    })
  })

  describe("select / observe", () => {
    function routeFetch(routes: Record<string, () => Response>) {
      const fetchMock = vi.fn().mockImplementation((url: string) => {
        // Insertion order = priority; register more-specific prefixes first
        // (the /events route before the bare item route).
        for (const [prefix, make] of Object.entries(routes)) {
          if (String(url).startsWith(prefix)) {
            return Promise.resolve(make())
          }
        }
        return Promise.reject(new Error(`Unmatched fetch: ${url}`))
      })
      vi.stubGlobal("fetch", fetchMock)
      return fetchMock
    }

    // The standard observe() routes: list, item re-fetch, hydration, events.
    function observeRoutes(events: unknown[], overrides = {}) {
      return {
        "http://localhost:8757/api/conversations?": () =>
          jsonResponse([child("cv_1")]),
        "http://localhost:8757/api/conversations/cv_1/events": () =>
          sseResponse(events),
        "http://localhost:8757/api/conversations/cv_1": () =>
          jsonResponse(child("cv_1", overrides)),
        "http://localhost:8757/api/chat/sessions/trace-cv_1": () =>
          jsonResponse({ id: "trace-cv_1", task_run: { trace: [] } }),
      }
    }

    it("hydrates persisted history, then renders the replayed turn into a fresh message", async () => {
      routeFetch({
        "http://localhost:8757/api/conversations?": () =>
          jsonResponse([child("cv_1")]),
        "http://localhost:8757/api/conversations/cv_1/events": () =>
          sseResponse([
            { type: "text-start", id: "t1" },
            { type: "text-delta", delta: "live tail" },
            {
              type: "conversation-state",
              session_id: "cv_1",
              kind: "subagent",
              state: "running",
              auto_flag: false,
            },
          ]),
        "http://localhost:8757/api/conversations/cv_1": () =>
          jsonResponse(child("cv_1")),
        "http://localhost:8757/api/chat/sessions/trace-cv_1": () =>
          jsonResponse({
            id: "trace-cv_1",
            task_run: {
              trace: [
                { role: "user", content: "briefing" },
                { role: "assistant", content: "persisted turn" },
              ],
            },
          }),
      })
      await store.syncForConversation("trace-leaf")

      store.select("cv_1")
      expect(get(store.selectedId)).toBe("cv_1")
      await flush()

      const transcript = get(store.transcripts).get("cv_1") ?? []
      expect(transcript.map((m) => m.role)).toEqual([
        "user",
        "assistant",
        "assistant",
      ])
      // The hydrated turn is untouched; the replay landed in a fresh message.
      expect(transcript[1].parts).toEqual([
        { type: "text", text: "persisted turn" },
      ])
      expect(transcript[2].parts).toEqual([{ type: "text", text: "live tail" }])
    })

    it("hydrates from the RE-FETCHED item's fresh leaf, not the stale list entry", async () => {
      // conversation-state events carry no trace ids, so the list's
      // current_trace_id can go stale between syncs; observe() re-fetches the
      // item and must hydrate from ITS leaf.
      const hydrated: string[] = []
      routeFetch({
        "http://localhost:8757/api/conversations?": () =>
          jsonResponse([child("cv_1", { current_trace_id: "trace-stale" })]),
        "http://localhost:8757/api/conversations/cv_1/events": () =>
          sseResponse([]),
        "http://localhost:8757/api/conversations/cv_1": () =>
          jsonResponse(child("cv_1", { current_trace_id: "trace-fresh" })),
        "http://localhost:8757/api/chat/sessions/": () => {
          hydrated.push("hit")
          return jsonResponse({ id: "trace-fresh", task_run: { trace: [] } })
        },
      })
      const fetchMock = vi.mocked(globalThis.fetch)
      await store.syncForConversation("trace-leaf")

      store.select("cv_1")
      await flush()

      const sessionCalls = fetchMock.mock.calls
        .map((c) => String(c[0]))
        .filter((u) => u.includes("/api/chat/sessions/"))
      expect(sessionCalls).toEqual([
        "http://localhost:8757/api/chat/sessions/trace-fresh",
      ])
      // The list entry was refreshed from the item fetch.
      expect(get(store.children)[0].current_trace_id).toBe("trace-fresh")
    })

    it("strips steer framing from replayed user-message echoes", async () => {
      routeFetch(
        observeRoutes([
          {
            type: "user-message",
            content:
              "<system-reminder>steer framing</system-reminder>\n\nfocus on evals",
            id: "echo-1",
          },
        ]),
      )
      await store.syncForConversation("trace-leaf")

      store.select("cv_1")
      await flush()

      const transcript = get(store.transcripts).get("cv_1") ?? []
      expect(transcript[0].content).toBe("focus on evals")
    })

    it("appends the kickoff echo as the briefing bubble when hydration is empty", async () => {
      routeFetch(
        observeRoutes([
          {
            type: "user-message",
            content: "Agent cv_1 — your assignment:\n\nDo the thing.",
            id: "kickoff-cv_1",
          },
          { type: "text-delta", delta: "on it" },
        ]),
      )
      await store.syncForConversation("trace-leaf")

      store.select("cv_1")
      await flush()

      const transcript = get(store.transcripts).get("cv_1") ?? []
      expect(transcript.map((m) => m.role)).toEqual(["user", "assistant"])
      expect(transcript[0].content).toBe(
        "Agent cv_1 — your assignment:\n\nDo the thing.",
      )
      expect(transcript[0].echoId).toBe("kickoff-cv_1")
      expect(transcript[1].parts).toEqual([{ type: "text", text: "on it" }])
    })

    it("skips a replayed kickoff echo when hydration already seeded the briefing", async () => {
      routeFetch({
        "http://localhost:8757/api/conversations?": () =>
          jsonResponse([child("cv_1")]),
        "http://localhost:8757/api/conversations/cv_1/events": () =>
          sseResponse([
            {
              type: "user-message",
              content: "Agent cv_1 — your assignment:\n\nDo the thing.",
              id: "kickoff-cv_1",
            },
            { type: "text-delta", delta: "second round" },
          ]),
        "http://localhost:8757/api/conversations/cv_1": () =>
          jsonResponse(child("cv_1")),
        "http://localhost:8757/api/chat/sessions/trace-cv_1": () =>
          jsonResponse({
            id: "trace-cv_1",
            task_run: {
              trace: [
                {
                  role: "user",
                  content: "Agent cv_1 — your assignment:\n\nDo the thing.",
                },
                { role: "assistant", content: "first round" },
              ],
            },
          }),
      })
      await store.syncForConversation("trace-leaf")

      store.select("cv_1")
      await flush()

      const transcript = get(store.transcripts).get("cv_1") ?? []
      // Exactly ONE briefing bubble (the hydrated one, no echoId), then the
      // hydrated round and the replayed live round in a fresh message.
      expect(transcript.map((m) => m.role)).toEqual([
        "user",
        "assistant",
        "assistant",
      ])
      expect(transcript.filter((m) => m.role === "user")).toHaveLength(1)
      expect(transcript[0].echoId).toBeUndefined()
      expect(transcript[2].parts).toEqual([
        { type: "text", text: "second round" },
      ])
    })

    it("mirrors activity/retry runtime state live, cleared when the stream ends", async () => {
      // A pushable SSE body so runtime state can be asserted mid-stream.
      const encoder = new TextEncoder()
      type Chunk = { done: boolean; value?: Uint8Array }
      const queue: Chunk[] = []
      let resolveNext: ((chunk: Chunk) => void) | null = null
      const deliver = (chunk: Chunk) => {
        if (resolveNext) {
          const r = resolveNext
          resolveNext = null
          r(chunk)
        } else {
          queue.push(chunk)
        }
      }
      const push = (event: unknown) =>
        deliver({
          done: false,
          value: encoder.encode(`data: ${JSON.stringify(event)}\n`),
        })
      const end = () => deliver({ done: true })
      const reader = {
        read: () =>
          new Promise<Chunk>((resolve) => {
            if (queue.length > 0) {
              resolve(queue.shift() as Chunk)
            } else {
              resolveNext = resolve
            }
          }),
      } as unknown as ReadableStreamDefaultReader<Uint8Array>

      routeFetch({
        "http://localhost:8757/api/conversations?": () =>
          jsonResponse([child("cv_1")]),
        "http://localhost:8757/api/conversations/cv_1/events": () =>
          ({
            ok: true,
            status: 200,
            body: { getReader: () => reader },
          }) as unknown as Response,
        "http://localhost:8757/api/conversations/cv_1": () =>
          jsonResponse(child("cv_1")),
        "http://localhost:8757/api/chat/sessions/trace-cv_1": () =>
          jsonResponse({ id: "trace-cv_1", task_run: { trace: [] } }),
      })
      await store.syncForConversation("trace-leaf")

      store.select("cv_1")
      await flush()

      push({ type: "kiln-tool-execution-start", tool_count: 1 })
      push({ type: "kiln-chat-retry", attempt: 1, max_attempts: 3 })
      await flush()

      const state = get(store.runtime).get("cv_1")
      expect(state?.showActivityIndicator).toBe(true)
      expect(state?.retry).toEqual({ attempt: 1, max: 3 })

      end()
      await flush()

      // The live-only affordances die with the stream.
      expect(get(store.runtime).has("cv_1")).toBe(false)
    })

    it("appends user-message echoes and dedupes them by echo id", async () => {
      routeFetch(
        observeRoutes([
          { type: "user-message", content: "steer left", id: "echo-1" },
          { type: "user-message", content: "steer left", id: "echo-1" },
          { type: "text-delta", delta: "ok, steering" },
        ]),
      )
      await store.syncForConversation("trace-leaf")

      store.select("cv_1")
      await flush()

      const transcript = get(store.transcripts).get("cv_1") ?? []
      expect(transcript.map((m) => m.role)).toEqual(["user", "assistant"])
      expect(transcript[0].content).toBe("steer left")
      expect(transcript[0].echoId).toBe("echo-1")
      expect(transcript[1].parts).toEqual([
        { type: "text", text: "ok, steering" },
      ])
    })

    it("updates the child from the on-subscribe state marker", async () => {
      routeFetch(
        observeRoutes([
          {
            type: "conversation-state",
            session_id: "cv_1",
            kind: "subagent",
            state: "completed",
            auto_flag: false,
            report_available: true,
          },
        ]),
      )
      await store.syncForConversation("trace-leaf")

      store.select("cv_1")
      await flush()

      expect(get(store.children)[0].state).toBe("completed")
      expect(get(store.children)[0].report_available).toBe(true)
    })

    it("selecting an unknown id or null is safe bookkeeping", async () => {
      const fetchMock = vi.fn().mockResolvedValue(jsonResponse([]))
      vi.stubGlobal("fetch", fetchMock)
      await store.syncForConversation("trace-leaf")

      store.select("cv_missing")
      await flush()
      expect(get(store.selectedId)).toBe("cv_missing")
      // No observation started for an unknown child (only the list fetch ran).
      expect(fetchMock).toHaveBeenCalledTimes(1)

      store.select(null)
      expect(get(store.selectedId)).toBeNull()
    })
  })

  describe("stop / sendMessage", () => {
    it("stop POSTs to the stop endpoint", async () => {
      const fetchMock = vi
        .fn()
        .mockResolvedValue({ ok: true, status: 202 } as Response)
      vi.stubGlobal("fetch", fetchMock)

      await store.stop("cv_1")

      expect(fetchMock).toHaveBeenCalledWith(
        "http://localhost:8757/api/conversations/cv_1/stop",
        { method: "POST" },
      )
    })

    it("sendMessage POSTs the content and reports ok", async () => {
      const fetchMock = vi
        .fn()
        .mockResolvedValue({ ok: true, status: 202 } as Response)
      vi.stubGlobal("fetch", fetchMock)

      const result = await store.sendMessage("cv_1", "keep going")

      expect(result.ok).toBe(true)
      const [url, init] = fetchMock.mock.calls[0]
      expect(url).toBe("http://localhost:8757/api/conversations/cv_1/messages")
      expect(JSON.parse((init as RequestInit).body as string)).toEqual({
        content: "keep going",
      })
    })

    it("surfaces a friendly error (and refreshes the list) on 409", async () => {
      const fetchMock = vi
        .fn()
        .mockResolvedValueOnce(jsonResponse([child("cv_1")]))
        .mockResolvedValueOnce({ ok: false, status: 409 } as Response)
        .mockResolvedValueOnce(
          jsonResponse([child("cv_1", { state: "completed" })]),
        )
      vi.stubGlobal("fetch", fetchMock)
      await store.syncForConversation("trace-leaf")

      const result = await store.sendMessage("cv_1", "too late")
      await flush()

      expect(result.ok).toBe(false)
      expect(result.error).toContain("already finished")
      const transcript = get(store.transcripts).get("cv_1") ?? []
      expect(transcript[transcript.length - 1]).toMatchObject({
        role: "error",
        content: expect.stringContaining("already finished"),
      })
      // The terminal state was re-fetched.
      expect(get(store.children)[0].state).toBe("completed")
    })

    it("reports a non-409 failure with the server detail", async () => {
      const fetchMock = vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: () => Promise.resolve({ detail: "Conversation not found: cv_1" }),
      } as unknown as Response)
      vi.stubGlobal("fetch", fetchMock)

      const result = await store.sendMessage("cv_1", "hello?")

      expect(result.ok).toBe(false)
      expect(result.error).toBe("Conversation not found: cv_1")
    })
  })

  describe("reset", () => {
    it("clears children, transcripts and selection, and re-arms sync", async () => {
      const fetchMock = vi.fn().mockResolvedValue(jsonResponse([child("cv_1")]))
      vi.stubGlobal("fetch", fetchMock)
      await store.syncForConversation("trace-leaf")
      store.select("cv_1")

      store.reset()

      expect(get(store.children)).toEqual([])
      expect(get(store.selectedId)).toBeNull()
      expect(get(store.transcripts).size).toBe(0)
      // The same parent can be re-synced after a reset (dedupe was cleared).
      await store.syncForConversation("trace-leaf")
      expect(get(store.children).map((c) => c.session_id)).toEqual(["cv_1"])
    })
  })
})

describe("isTerminalState", () => {
  it("classifies states", () => {
    expect(isTerminalState("running")).toBe(false)
    expect(isTerminalState("idle")).toBe(false)
    expect(isTerminalState("awaiting_approval")).toBe(false)
    for (const state of ["completed", "failed", "stopped", "timeout"]) {
      expect(isTerminalState(state)).toBe(true)
    }
  })
})

describe("visibleChildTabs", () => {
  it("shows live children and hides terminal ones", () => {
    const list = [
      child("cv_run"),
      child("cv_done", { state: "completed" }),
      child("cv_fail", { state: "failed" }),
      child("cv_stop", { state: "stopped" }),
      child("cv_time", { state: "timeout" }),
    ]
    expect(visibleChildTabs(list, null).map((c) => c.session_id)).toEqual([
      "cv_run",
    ])
  })

  it("keeps the selected child visible even when terminal", () => {
    const list = [child("cv_run"), child("cv_done", { state: "completed" })]
    expect(visibleChildTabs(list, "cv_done").map((c) => c.session_id)).toEqual([
      "cv_run",
      "cv_done",
    ])
    // Selecting away drops the terminal tab (pure derivation, no tombstoning).
    expect(visibleChildTabs(list, null).map((c) => c.session_id)).toEqual([
      "cv_run",
    ])
  })

  it("a revived child's tab reappears automatically", () => {
    const terminal = [child("cv_1", { state: "failed" })]
    expect(visibleChildTabs(terminal, null)).toEqual([])
    const revived = [child("cv_1", { state: "running" })]
    expect(visibleChildTabs(revived, null).map((c) => c.session_id)).toEqual([
      "cv_1",
    ])
  })

  it("returns empty when everything is terminal and nothing is selected", () => {
    const list = [
      child("cv_a", { state: "completed" }),
      child("cv_b", { state: "stopped" }),
    ]
    expect(visibleChildTabs(list, null)).toEqual([])
  })
})

describe("shouldCollapseChildTabs", () => {
  it("collapses only above the overflow limit", () => {
    expect(CHILD_TAB_OVERFLOW_LIMIT).toBe(3)
    const atLimit = [child("cv_1"), child("cv_2"), child("cv_3")]
    expect(shouldCollapseChildTabs(atLimit)).toBe(false)
    const overLimit = [...atLimit, child("cv_4")]
    expect(shouldCollapseChildTabs(overLimit)).toBe(true)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// Port of auto_run_store.test.ts (deleted in phase 3 with the store it
// covered, which was folded into conversation_store.ts): the same behavior
// contracts, asserted against the auto conversation store — new endpoints
// (/api/conversations) and the unified `conversation-state` vocabulary
// replacing auto-mode-on/off/idle/state. Event translation used throughout:
//
//   auto-mode-on{run_id}          → conversation-state{state:"running", auto_flag:true}
//   auto-mode-idle{reason}        → conversation-state{state:"idle", auto_flag:true, idle_reason}
//   auto-mode-off{reason}         → conversation-state{auto_flag:false, idle_reason}
//   auto-mode-state{working}      → the same conversation-state marker
// ─────────────────────────────────────────────────────────────────────────────

import {
  createAutoConversationStore,
  type AutoConversationSink,
  type AutoConversationStore,
} from "./conversation_store"
import type {
  ChatMessage,
  ContextUsage,
  ToolCallsPendingItem,
} from "./streaming_chat"

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

function makeAutoSink(): { sink: AutoConversationSink; calls: SinkCalls } {
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
  const sink: AutoConversationSink = {
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

// State-event builders for the unified vocabulary (see the translation table
// in the section header).
function stateRunning(sid: string) {
  return {
    type: "conversation-state",
    session_id: sid,
    kind: "auto",
    state: "running",
    auto_flag: true,
  }
}

function stateIdle(sid: string, reason: string) {
  return {
    type: "conversation-state",
    session_id: sid,
    kind: "auto",
    state: "idle",
    auto_flag: true,
    idle_reason: reason,
  }
}

function stateOff(sid: string, reason: string | null) {
  return {
    type: "conversation-state",
    session_id: sid,
    kind: "auto",
    state: "idle",
    auto_flag: false,
    ...(reason === null ? {} : { idle_reason: reason }),
  }
}

describe("auto_conversation_store", () => {
  let store: AutoConversationStore
  let calls: SinkCalls

  beforeEach(() => {
    // @ts-expect-error install fake on global
    globalThis.EventSource = FakeEventSource
    FakeEventSource.reset()
    store = createAutoConversationStore()
    const made = makeAutoSink()
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
      json: () => Promise.resolve({ session_id: "cv_1" }),
    })
    vi.stubGlobal("fetch", fetchMock)

    // Consent path (an enable_tool_call_id is present): a burst starts
    // immediately, so a fresh assistant turn is opened to render it.
    const result = await store.requestEnable({
      trace_id: "t1",
      enable_tool_call_id: "call_enable",
    })
    expect(result.ok).toBe(true)

    // Enable POST went out with the seed body to the create endpoint.
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe("http://localhost:8757/api/conversations")
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      trace_id: "t1",
      enable_tool_call_id: "call_enable",
    })

    // A fresh assistant turn was started and the events stream opened.
    expect(calls.beginAssistantTurn).toBe(1)
    const source = FakeEventSource.latest()
    expect(source.url).toBe(
      "http://localhost:8757/api/conversations/cv_1/events",
    )

    // The running state confirms the on state from the desktop-owned run.
    source.message(stateRunning("cv_1"))
    expect(get(store.autoModeOn)).toBe(true)
    expect(get(store.sessionId)).toBe("cv_1")

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
      json: () => Promise.resolve({ session_id: "cv_arm" }),
    })
    vi.stubGlobal("fetch", fetchMock)

    // Manual enable only arms the conversation: the server creates the
    // record IDLE("armed") without an empty upstream burst, so there's no
    // immediate assistant turn to open — the indicator just turns on.
    const result = await store.requestEnable({ trace_id: "t1" })
    expect(result.ok).toBe(true)
    expect(calls.beginAssistantTurn).toBe(0)

    // The events stream still opens so the indicator + future bursts render.
    const source = FakeEventSource.latest()
    expect(source.url).toBe(
      "http://localhost:8757/api/conversations/cv_arm/events",
    )
    // The on-subscribe conversation-state marker lands on flag-on/idle
    // (the old world buffered on→idle markers for the same effect).
    source.message(stateIdle("cv_arm", "armed"))
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
      json: () => Promise.resolve({ session_id: "cv_new" }),
    })
    vi.stubGlobal("fetch", fetchMock)
    // The conversation was armed client-side (brand-new chat, no trace_id).
    store.arm()
    expect(get(store.armed)).toBe(true)

    // The first send creates the conversation via enable with extra_messages
    // + no trace_id.
    const result = await store.requestEnable({
      extra_messages: [{ role: "user", content: "do the thing" }],
    })
    expect(result.ok).toBe(true)

    // The enable POST carried the first message and NO trace_id.
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe("http://localhost:8757/api/conversations")
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      extra_messages: [{ role: "user", content: "do the thing" }],
    })

    // A burst starts immediately (extra_messages), so an assistant turn
    // opened, the events stream attached, and the client-armed flag cleared
    // (the real desktop-owned conversation now owns the on-state).
    expect(calls.beginAssistantTurn).toBe(1)
    expect(get(store.armed)).toBe(false)
    const source = FakeEventSource.latest()
    expect(source.url).toBe(
      "http://localhost:8757/api/conversations/cv_new/events",
    )
    source.message(stateRunning("cv_new"))
    expect(get(store.autoModeOn)).toBe(true)
    expect(get(store.sessionId)).toBe("cv_new")
  })

  it("tool-calls-pending on the observer stream hands off to the approval sink (graceful stop)", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ session_id: "cv_stop" }),
    })
    vi.stubGlobal("fetch", fetchMock)
    await store.requestEnable({
      trace_id: "t1",
      enable_tool_call_id: "call_enable",
    })
    const source = FakeEventSource.latest()
    source.message(stateRunning("cv_stop"))

    // Graceful stop: the run surfaces the final turn's client tool calls.
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
    // Working sub-state cleared; the tool-calls-pending event is NOT
    // forwarded to the processor as a normal chat event.
    expect(get(store.working)).toBe(false)

    // The accompanying flag-off state clears the indicator (normal mode).
    source.message(stateOff("cv_stop", "user_stopped"))
    expect(get(store.autoModeOn)).toBe(false)
    expect(calls.offReasons).toContain("user_stopped")
  })

  it("a flag-off state clears everything and closes the stream", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ session_id: "cv_2" }),
    })
    vi.stubGlobal("fetch", fetchMock)
    await store.requestEnable({ trace_id: "t" })
    const source = FakeEventSource.latest()
    source.message(stateRunning("cv_2"))
    expect(get(store.autoModeOn)).toBe(true)

    source.message(stateOff("cv_2", "user_disabled"))
    expect(get(store.autoModeOn)).toBe(false)
    expect(get(store.sessionId)).toBeNull()
    expect(get(store.offReason)).toBe("user_disabled")
    expect(source.closed).toBe(true)
    expect(calls.offReasons).toEqual(["user_disabled"])
  })

  it("stop posts to the conversation's stop endpoint without flipping state locally", async () => {
    const enableFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ session_id: "cv_3" }),
    })
    vi.stubGlobal("fetch", enableFetch)
    await store.requestEnable({ trace_id: "t" })
    FakeEventSource.latest().message(stateRunning("cv_3"))

    const stopFetch = vi.fn().mockResolvedValue({ ok: true })
    vi.stubGlobal("fetch", stopFetch)
    await store.stop()

    expect(stopFetch).toHaveBeenCalledTimes(1)
    expect(stopFetch.mock.calls[0][0]).toBe(
      "http://localhost:8757/api/conversations/cv_3/stop",
    )
    // State stays "on" until the authoritative flag-off state arrives.
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
    expect(url).toBe("http://localhost:8757/api/conversations/auto/decline")
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
    store.attach("cv_re")
    const source = FakeEventSource.latest()
    expect(source.url).toBe(
      "http://localhost:8757/api/conversations/cv_re/events",
    )
    expect(get(store.autoModeOn)).toBe(true)
    expect(get(store.sessionId)).toBe("cv_re")

    // Replayed buffer (in-progress turn) arrives before live events.
    source.open()
    source.message(stateRunning("cv_re"))
    source.message({ type: "text-start", id: "x" })
    source.message({ type: "text-delta", delta: "buffered" })
    source.message({ type: "text-delta", delta: " + live" })

    const last = calls.assistantUpdates[calls.assistantUpdates.length - 1]
    expect(last.parts?.[0]).toEqual({ type: "text", text: "buffered + live" })
  })

  it("events 404 / connection failure falls back to off without throwing", () => {
    store.attach("cv_gone")
    const source = FakeEventSource.latest()
    expect(get(store.autoModeOn)).toBe(true)

    // EventSource errors before opening (events 404 → unknown/GC'd record).
    expect(() => source.fail()).not.toThrow()
    expect(get(store.autoModeOn)).toBe(false)
    expect(get(store.sessionId)).toBeNull()
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
    store.attach("cv_nav")
    const source = FakeEventSource.latest()
    source.message(stateRunning("cv_nav"))
    expect(get(store.autoModeOn)).toBe(true)

    store.detach()
    expect(get(store.autoModeOn)).toBe(false)
    expect(get(store.sessionId)).toBeNull()
    expect(source.closed).toBe(true)
    // Navigation, not an off-event: the sink is not told the run ended.
    expect(calls.offReasons).toEqual([])
  })

  it("an idle state keeps the flag ON and only clears the working sub-state", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ session_id: "cv_idle" }),
    })
    vi.stubGlobal("fetch", fetchMock)
    await store.requestEnable({ trace_id: "t" })
    const source = FakeEventSource.latest()
    source.message(stateRunning("cv_idle"))
    expect(get(store.autoModeOn)).toBe(true)
    expect(get(store.working)).toBe(true)

    source.message(stateIdle("cv_idle", "asked_user"))
    // Flag persists; only working clears. Stream stays open.
    expect(get(store.autoModeOn)).toBe(true)
    expect(get(store.working)).toBe(false)
    expect(get(store.sessionId)).toBe("cv_idle")
    expect(source.closed).toBe(false)
    expect(calls.idleReasons).toEqual(["asked_user"])
    // Idle is NOT an off-event: the conversation flag is unchanged.
    expect(calls.offReasons).toEqual([])
    // working timeline: on (enable attach) → on (running state) → off (idle).
    expect(calls.working).toEqual([true, true, false])
  })

  it("kiln-chat-retry surfaces retrying progress and clears on the next event", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ session_id: "cv_retry" }),
    })
    vi.stubGlobal("fetch", fetchMock)
    await store.requestEnable({ trace_id: "t" })
    const source = FakeEventSource.latest()
    source.message(stateRunning("cv_retry"))

    source.message({
      type: "kiln-chat-retry",
      run_id: "cv_retry",
      attempt: 3,
      max_attempts: 10,
      status_code: 503,
    })
    // Retry affordance set; the burst still reads as working, stream open.
    expect(get(store.retry)).toEqual({ attempt: 3, max: 10 })
    expect(get(store.working)).toBe(true)
    expect(source.closed).toBe(false)

    // A second retry updates the counter.
    source.message({
      type: "kiln-chat-retry",
      run_id: "cv_retry",
      attempt: 4,
      max_attempts: 10,
    })
    expect(get(store.retry)).toEqual({ attempt: 4, max: 10 })

    // The next non-retry event (here the burst settling idle) clears it.
    source.message(stateIdle("cv_retry", "asked_user"))
    expect(get(store.retry)).toBe(null)
  })

  it("only a flag-off state clears the indicator after an idle burst", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ session_id: "cv_io" }),
    })
    vi.stubGlobal("fetch", fetchMock)
    await store.requestEnable({ trace_id: "t" })
    const source = FakeEventSource.latest()
    source.message(stateRunning("cv_io"))
    source.message(stateIdle("cv_io", "done"))
    expect(get(store.autoModeOn)).toBe(true)

    source.message(stateOff("cv_io", "user_stopped"))
    expect(get(store.autoModeOn)).toBe(false)
    expect(get(store.working)).toBe(false)
    expect(get(store.sessionId)).toBeNull()
    expect(source.closed).toBe(true)
    expect(calls.offReasons).toEqual(["user_stopped"])
  })

  it("sendMessage injects via /messages, never posting stop", async () => {
    const enableFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ session_id: "cv_inj" }),
    })
    vi.stubGlobal("fetch", enableFetch)
    await store.requestEnable({ trace_id: "t" })
    FakeEventSource.latest().message(stateRunning("cv_inj"))

    const messageFetch = vi.fn().mockResolvedValue({ ok: true })
    vi.stubGlobal("fetch", messageFetch)
    const result = await store.sendMessage("keep going")

    expect(result.ok).toBe(true)
    expect(messageFetch).toHaveBeenCalledTimes(1)
    const [url, init] = messageFetch.mock.calls[0]
    expect(url).toBe("http://localhost:8757/api/conversations/cv_inj/messages")
    expect((init as RequestInit).method).toBe("POST")
    // No trace_id rides the inject anymore: the desktop supervisor's own
    // leaf is authoritative for the idle re-arm.
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      content: "keep going",
    })
    // Inject never stops: no /stop call, flag stays on, working set.
    expect(
      messageFetch.mock.calls.some((c) => String(c[0]).endsWith("/stop")),
    ).toBe(false)
    expect(get(store.autoModeOn)).toBe(true)
    expect(get(store.working)).toBe(true)
  })

  it("sendMessage with no active conversation returns an error and posts nothing", async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal("fetch", fetchMock)
    const result = await store.sendMessage("hi")
    expect(result.ok).toBe(false)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("a user-message echo renders a fresh user turn and marks working", () => {
    store.attach("cv_echo")
    const source = FakeEventSource.latest()
    source.message(stateRunning("cv_echo"))
    // Simulate going idle then injecting: the echo arrives on the stream.
    source.message(stateIdle("cv_echo", "done"))
    expect(get(store.working)).toBe(false)

    source.message({ type: "user-message", content: "do the next thing" })
    expect(calls.userMessages).toEqual(["do the next thing"])
    expect(get(store.working)).toBe(true)
    expect(get(store.autoModeOn)).toBe(true)
  })

  it("resets accumulated parts on a user-message echo so the prior round isn't duplicated into the new turn", () => {
    store.attach("cv_dup")
    const source = FakeEventSource.latest()
    source.message(stateRunning("cv_dup"))

    // Round 1 renders some assistant text into the current turn.
    source.message({ type: "text-start" })
    source.message({ type: "text-delta", delta: "Round one." })
    source.message({ type: "text-end" })

    // An injected user message opens a fresh assistant turn.
    source.message({ type: "user-message", content: "hi there" })

    // Round 2 renders into the new turn.
    source.message({ type: "text-start" })
    source.message({ type: "text-delta", delta: "Round two." })
    source.message({ type: "text-end" })

    const last = calls.assistantUpdates[calls.assistantUpdates.length - 1]
    const text = (last.parts ?? [])
      .filter((p): p is { type: "text"; text: string } => p.type === "text")
      .map((p) => p.text)
      .join("")
    // Without the processor reset, round one's text would be re-flushed into
    // the new turn alongside round two's.
    expect(text).toBe("Round two.")
    expect(text).not.toContain("Round one")
  })

  it("opens a fresh assistant turn for the in-flight round on re-attach (openInflightTurn)", () => {
    // Re-attach with openInflightTurn: the replayed in-flight round must
    // render into its OWN turn instead of overwriting the last hydrated
    // bubble.
    store.attach("cv_reattach", true, true)
    const source = FakeEventSource.latest()
    // No turn opened until the in-flight round actually produces content.
    expect(calls.beginAssistantTurn).toBe(0)
    source.message({ type: "text-start" })
    source.message({ type: "text-delta", delta: "in-flight" })
    expect(calls.beginAssistantTurn).toBe(1)
  })

  it("the attach-time idle marker updates state without signaling the idle sink", () => {
    // The first conversation-state event after attach is the bus's
    // on-subscribe MARKER — a snapshot of where the run already is, not a
    // burst-settled transition. It must reflect flag/working (indicator,
    // "waiting for you") WITHOUT firing sink.onAutoModeIdle, which is the
    // session store's settle hook and flushes queued messages — the old
    // auto-mode-state marker never fired it.
    store.attach("cv_marker", false, true)
    const source = FakeEventSource.latest()
    source.message(stateIdle("cv_marker", "asked_user"))
    expect(get(store.autoModeOn)).toBe(true)
    expect(get(store.working)).toBe(false)
    expect(calls.idleReasons).toEqual([])

    // A later REAL settle transition on the same stream does signal.
    source.message(stateRunning("cv_marker"))
    source.message(stateIdle("cv_marker", "done"))
    expect(calls.idleReasons).toEqual(["done"])
  })

  it("a running attach marker consumes the marker slot so the next idle signals", () => {
    // Attaching mid-burst: the marker is state=running (the old
    // auto-mode-state{working:true}); the burst settling afterwards is a
    // real transition and must fire the idle sink exactly once.
    store.attach("cv_marker_run")
    const source = FakeEventSource.latest()
    source.message(stateRunning("cv_marker_run"))
    expect(calls.idleReasons).toEqual([])
    source.message(stateIdle("cv_marker_run", "asked_user"))
    expect(calls.idleReasons).toEqual(["asked_user"])
  })

  it("does not open an in-flight turn on re-attach to an idle conversation (no content)", () => {
    store.attach("cv_idle_reattach", false, true)
    const source = FakeEventSource.latest()
    source.message(stateIdle("cv_idle_reattach", "done"))
    expect(calls.beginAssistantTurn).toBe(0)
  })

  it("does not open an extra in-flight turn on the initial attach (openInflightTurn omitted)", () => {
    store.attach("cv_initial")
    const source = FakeEventSource.latest()
    source.message({ type: "text-delta", delta: "hi" })
    expect(calls.beginAssistantTurn).toBe(0)
  })

  it("an injected-message echo consumes the pending in-flight turn (no double turn)", () => {
    store.attach("cv_echo_consume", true, true)
    const source = FakeEventSource.latest()
    // The echo opens its own turn (via the sink); the subsequent in-flight
    // content must NOT also trigger the pending fresh turn.
    source.message({ type: "user-message", content: "hi", id: "cm_1" })
    source.message({ type: "text-delta", delta: "resp" })
    // The fake sink's onUserMessage doesn't call beginAssistantTurn, so the
    // only way beginAssistantTurn fires here is the (unwanted) pending
    // in-flight turn.
    expect(calls.beginAssistantTurn).toBe(0)
  })

  it("resolve returns {session_id, current_trace_id, state} for a live conversation", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          session_id: "cv_r",
          current_trace_id: "t_now",
          state: "running",
          auto_flag: true,
        }),
    })
    vi.stubGlobal("fetch", fetchMock)

    const result = await store.resolve("t_stale")
    expect(result).toEqual({
      session_id: "cv_r",
      current_trace_id: "t_now",
      state: "running",
      auto_flag: true,
    })
    const [url] = fetchMock.mock.calls[0]
    expect(url).toBe(
      "http://localhost:8757/api/conversations/resolve?trace_id=t_stale",
    )
  })

  it("resolve returns null on 404 (no live auto conversation)", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: () => Promise.resolve({ detail: "no active conversation" }),
    })
    vi.stubGlobal("fetch", fetchMock)
    expect(await store.resolve("t_stale")).toBeNull()
  })

  it("resolve returns null on network error", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error("boom"))
    vi.stubGlobal("fetch", fetchMock)
    expect(await store.resolve("t")).toBeNull()
  })

  // ── Reconnecting affordance + on-attach liveness ────────────────────────────

  it("beginReconnect sets the reconnecting affordance; attach clears it on open", () => {
    expect(get(store.reconnecting)).toBe(false)
    store.beginReconnect()
    expect(get(store.reconnecting)).toBe(true)

    store.attach("cv_rc")
    // Still reconnecting through the connecting window (no stream yet).
    expect(get(store.reconnecting)).toBe(true)

    const source = FakeEventSource.latest()
    source.open()
    // Attach established → the affordance clears (can't get stuck on).
    expect(get(store.reconnecting)).toBe(false)
  })

  it("attach clears reconnecting on the first event even without onopen", () => {
    store.beginReconnect()
    store.attach("cv_rc2")
    expect(get(store.reconnecting)).toBe(true)

    const source = FakeEventSource.latest()
    source.message(stateRunning("cv_rc2"))
    expect(get(store.reconnecting)).toBe(false)
  })

  it("attach with initialWorking drives the thinking indicator immediately", () => {
    // A RUNNING conversation (from the resolve state) shows working before
    // any event.
    store.beginReconnect()
    store.attach("cv_work", true)
    expect(get(store.working)).toBe(true)
    expect(get(store.autoModeOn)).toBe(true)

    // An IDLE one (initialWorking=false) shows the idle indicator.
    store.detach()
    store.beginReconnect()
    store.attach("cv_wait", false)
    expect(get(store.working)).toBe(false)
    expect(get(store.autoModeOn)).toBe(true)
  })

  it("the on-subscribe state marker sets working + flag and clears reconnecting", () => {
    store.beginReconnect()
    store.attach("cv_state")
    const source = FakeEventSource.latest()

    // Working snapshot (the old auto-mode-state{working:true}) → thinking
    // indicator on, reconnecting cleared.
    source.message(stateRunning("cv_state"))
    expect(get(store.autoModeOn)).toBe(true)
    expect(get(store.working)).toBe(true)
    expect(get(store.reconnecting)).toBe(false)

    // Idle snapshot → working off, flag stays on.
    source.message(stateIdle("cv_state", "asked_user"))
    expect(get(store.working)).toBe(false)
    expect(get(store.autoModeOn)).toBe(true)
  })

  it("reconnecting clears on error (404) so the affordance can't get stuck", () => {
    store.beginReconnect()
    store.attach("cv_rc_gone")
    expect(get(store.reconnecting)).toBe(true)

    const source = FakeEventSource.latest()
    source.fail() // events 404 / connection failure before opening
    expect(get(store.reconnecting)).toBe(false)
    expect(get(store.autoModeOn)).toBe(false)
  })

  it("reconnecting clears on a flag-off state and on detach", () => {
    store.beginReconnect()
    store.attach("cv_rc_off")
    const source = FakeEventSource.latest()
    source.message(stateOff("cv_rc_off", "user_stopped"))
    expect(get(store.reconnecting)).toBe(false)

    store.beginReconnect()
    expect(get(store.reconnecting)).toBe(true)
    store.detach()
    expect(get(store.reconnecting)).toBe(false)
  })

  it("ignores conversation-state events for other kinds (defense in depth)", () => {
    // A subagent state event must never flip the auto indicator — the auto
    // observer stream shouldn't carry one, but guard against multiplexing.
    store.attach("cv_kind")
    const source = FakeEventSource.latest()
    source.message(stateRunning("cv_kind"))
    expect(get(store.working)).toBe(true)
    source.message({
      type: "conversation-state",
      session_id: "cv_other",
      kind: "subagent",
      state: "completed",
      auto_flag: false,
    })
    // Claimed (not forwarded to the processor) but ignored: still on/working.
    expect(get(store.autoModeOn)).toBe(true)
    expect(get(store.working)).toBe(true)
  })

  it("is a pure observer: an off event never posts stop", async () => {
    const enableFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ session_id: "cv_4" }),
    })
    vi.stubGlobal("fetch", enableFetch)
    await store.requestEnable({ trace_id: "t" })

    const postSpy = vi.fn().mockResolvedValue({ ok: true })
    vi.stubGlobal("fetch", postSpy)

    const source = FakeEventSource.latest()
    source.message(stateRunning("cv_4"))
    source.message(stateOff("cv_4", "user_stopped"))

    expect(postSpy).not.toHaveBeenCalled()
  })
})
