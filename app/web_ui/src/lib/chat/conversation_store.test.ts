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
