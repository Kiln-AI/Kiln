// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest"
import { get } from "svelte/store"
import {
  createSubagentStore,
  isTerminalSubagentStatus,
  type SubAgentItem,
  type SubagentStore,
} from "./subagent_store"

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
  overrides: Partial<SubAgentItem> = {},
): SubAgentItem {
  return {
    subagent_id: id,
    name: `Agent ${id}`,
    agent_type: "general",
    status: "running",
    current_trace_id: `trace-${id}`,
    parent_trace_id_at_spawn: "parent-1",
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

describe("subagent_store", () => {
  let store: SubagentStore

  beforeEach(() => {
    // @ts-expect-error install fake on global
    globalThis.EventSource = FakeEventSource
    FakeEventSource.reset()
    store = createSubagentStore()
  })

  afterEach(() => {
    store.reset()
    store.disconnect()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  describe("syncForConversation", () => {
    it("fetches the children for the parent trace and replaces the list", async () => {
      const fetchMock = vi
        .fn()
        .mockResolvedValue(jsonResponse([child("sa_1"), child("sa_2")]))
      vi.stubGlobal("fetch", fetchMock)

      await store.syncForConversation("trace-leaf")

      expect(fetchMock).toHaveBeenCalledWith(
        "http://localhost:8757/api/chat/subagents?parent_trace_id=trace-leaf",
      )
      expect(get(store.children).map((c) => c.subagent_id)).toEqual([
        "sa_1",
        "sa_2",
      ])
    })

    it("dedupes by trace id (no refetch for the same value)", async () => {
      const fetchMock = vi.fn().mockResolvedValue(jsonResponse([child("sa_1")]))
      vi.stubGlobal("fetch", fetchMock)

      await store.syncForConversation("trace-leaf")
      await store.syncForConversation("trace-leaf")

      expect(fetchMock).toHaveBeenCalledTimes(1)
    })

    it("clears the list (and the selection) for a null trace", async () => {
      const fetchMock = vi.fn().mockResolvedValue(jsonResponse([child("sa_1")]))
      vi.stubGlobal("fetch", fetchMock)

      await store.syncForConversation("trace-leaf")
      store.select("sa_1")
      await store.syncForConversation(null)

      expect(get(store.children)).toEqual([])
      expect(get(store.selectedId)).toBeNull()
    })

    it("clears the selection when the new list lacks the selected child", async () => {
      // Route by URL: select() also starts an observation (session hydration +
      // events stream), which must not race the list fetches out of order.
      const fetchMock = vi.fn().mockImplementation((url: string) => {
        const u = String(url)
        if (u.includes("parent_trace_id=trace-a")) {
          return Promise.resolve(jsonResponse([child("sa_1")]))
        }
        if (u.includes("parent_trace_id=trace-b")) {
          return Promise.resolve(jsonResponse([child("sa_other")]))
        }
        if (u.includes("/api/chat/sessions/")) {
          return Promise.resolve(
            jsonResponse({ id: "trace-sa_1", task_run: { trace: [] } }),
          )
        }
        return Promise.resolve(sseResponse([]))
      })
      vi.stubGlobal("fetch", fetchMock)

      await store.syncForConversation("trace-a")
      store.select("sa_1")
      await store.syncForConversation("trace-b")

      expect(get(store.children).map((c) => c.subagent_id)).toEqual([
        "sa_other",
      ])
      expect(get(store.selectedId)).toBeNull()
    })
  })

  describe("status firehose", () => {
    it("connects to the firehose and updates a known child from status events", async () => {
      const fetchMock = vi.fn().mockResolvedValue(jsonResponse([child("sa_1")]))
      vi.stubGlobal("fetch", fetchMock)
      await store.syncForConversation("trace-leaf")

      store.connect()
      const source = FakeEventSource.latest()
      expect(source.url).toBe("http://localhost:8757/api/chat/subagents/events")
      source.open()
      expect(get(store.connection)).toBe("open")

      source.message({
        type: "kiln-subagent-status",
        subagent_id: "sa_1",
        name: "Agent sa_1",
        agent_type: "general",
        status: "completed",
        trace_id: "trace-new-leaf",
        report_available: true,
      })

      const updated = get(store.children)[0]
      expect(updated.status).toBe("completed")
      expect(updated.current_trace_id).toBe("trace-new-leaf")
      expect(updated.report_available).toBe(true)
    })

    it("re-fetches the list when a status event arrives for an unknown child", async () => {
      const fetchMock = vi
        .fn()
        .mockResolvedValueOnce(jsonResponse([]))
        .mockResolvedValueOnce(jsonResponse([child("sa_new")]))
      vi.stubGlobal("fetch", fetchMock)
      await store.syncForConversation("trace-leaf")

      store.connect()
      FakeEventSource.latest().message({
        type: "kiln-subagent-status",
        subagent_id: "sa_new",
        status: "running",
      })
      await flush()

      expect(fetchMock).toHaveBeenCalledTimes(2)
      expect(fetchMock.mock.calls[1][0]).toBe(
        "http://localhost:8757/api/chat/subagents?parent_trace_id=trace-leaf",
      )
      expect(get(store.children).map((c) => c.subagent_id)).toEqual(["sa_new"])
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

    it("hydrates persisted history, then renders the replayed turn into a fresh message", async () => {
      routeFetch({
        "http://localhost:8757/api/chat/subagents?": () =>
          jsonResponse([child("sa_1")]),
        "http://localhost:8757/api/chat/sessions/trace-sa_1": () =>
          jsonResponse({
            id: "trace-sa_1",
            task_run: {
              trace: [
                { role: "user", content: "briefing" },
                { role: "assistant", content: "persisted turn" },
              ],
            },
          }),
        "http://localhost:8757/api/chat/subagents/sa_1/events": () =>
          sseResponse([
            { type: "text-start", id: "t1" },
            { type: "text-delta", delta: "live tail" },
            {
              type: "kiln-subagent-status",
              subagent_id: "sa_1",
              status: "running",
            },
          ]),
      })
      await store.syncForConversation("trace-leaf")

      store.select("sa_1")
      expect(get(store.selectedId)).toBe("sa_1")
      await flush()

      const transcript = get(store.transcripts).get("sa_1") ?? []
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

    it("strips steer framing from replayed user-message echoes", async () => {
      routeFetch({
        "http://localhost:8757/api/chat/subagents?": () =>
          jsonResponse([child("sa_1")]),
        "http://localhost:8757/api/chat/sessions/trace-sa_1": () =>
          jsonResponse({ id: "trace-sa_1", task_run: { trace: [] } }),
        "http://localhost:8757/api/chat/subagents/sa_1/events": () =>
          sseResponse([
            {
              type: "user-message",
              content:
                "<system-reminder>steer framing</system-reminder>\n\nfocus on evals",
              id: "echo-1",
            },
          ]),
      })
      await store.syncForConversation("trace-leaf")

      store.select("sa_1")
      await flush()

      const transcript = get(store.transcripts).get("sa_1") ?? []
      expect(transcript[0].content).toBe("focus on evals")
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
        "http://localhost:8757/api/chat/subagents?": () =>
          jsonResponse([child("sa_1")]),
        "http://localhost:8757/api/chat/sessions/trace-sa_1": () =>
          jsonResponse({ id: "trace-sa_1", task_run: { trace: [] } }),
        "http://localhost:8757/api/chat/subagents/sa_1/events": () =>
          ({
            ok: true,
            status: 200,
            body: { getReader: () => reader },
          }) as unknown as Response,
      })
      await store.syncForConversation("trace-leaf")

      store.select("sa_1")
      await flush()

      push({ type: "kiln-tool-execution-start", tool_count: 1 })
      push({ type: "kiln-chat-retry", attempt: 1, max_attempts: 3 })
      await flush()

      const state = get(store.runtime).get("sa_1")
      expect(state?.showActivityIndicator).toBe(true)
      expect(state?.retry).toEqual({ attempt: 1, max: 3 })

      end()
      await flush()

      // The live-only affordances die with the stream.
      expect(get(store.runtime).has("sa_1")).toBe(false)
    })

    it("appends user-message echoes and dedupes them by echo id", async () => {
      routeFetch({
        "http://localhost:8757/api/chat/subagents?": () =>
          jsonResponse([child("sa_1")]),
        "http://localhost:8757/api/chat/sessions/trace-sa_1": () =>
          jsonResponse({ id: "trace-sa_1", task_run: { trace: [] } }),
        "http://localhost:8757/api/chat/subagents/sa_1/events": () =>
          sseResponse([
            { type: "user-message", content: "steer left", id: "echo-1" },
            { type: "user-message", content: "steer left", id: "echo-1" },
            { type: "text-delta", delta: "ok, steering" },
          ]),
      })
      await store.syncForConversation("trace-leaf")

      store.select("sa_1")
      await flush()

      const transcript = get(store.transcripts).get("sa_1") ?? []
      expect(transcript.map((m) => m.role)).toEqual(["user", "assistant"])
      expect(transcript[0].content).toBe("steer left")
      expect(transcript[0].echoId).toBe("echo-1")
      expect(transcript[1].parts).toEqual([
        { type: "text", text: "ok, steering" },
      ])
    })

    it("updates the child from the on-subscribe status marker", async () => {
      routeFetch({
        "http://localhost:8757/api/chat/subagents?": () =>
          jsonResponse([child("sa_1")]),
        "http://localhost:8757/api/chat/sessions/trace-sa_1": () =>
          jsonResponse({ id: "trace-sa_1", task_run: { trace: [] } }),
        "http://localhost:8757/api/chat/subagents/sa_1/events": () =>
          sseResponse([
            {
              type: "kiln-subagent-status",
              subagent_id: "sa_1",
              status: "completed",
              report_available: true,
            },
          ]),
      })
      await store.syncForConversation("trace-leaf")

      store.select("sa_1")
      await flush()

      expect(get(store.children)[0].status).toBe("completed")
      expect(get(store.children)[0].report_available).toBe(true)
    })

    it("selecting an unknown id or null is safe bookkeeping", async () => {
      const fetchMock = vi.fn().mockResolvedValue(jsonResponse([]))
      vi.stubGlobal("fetch", fetchMock)
      await store.syncForConversation("trace-leaf")

      store.select("sa_missing")
      await flush()
      expect(get(store.selectedId)).toBe("sa_missing")
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

      await store.stop("sa_1")

      expect(fetchMock).toHaveBeenCalledWith(
        "http://localhost:8757/api/chat/subagents/sa_1/stop",
        { method: "POST" },
      )
    })

    it("sendMessage POSTs the content and reports ok", async () => {
      const fetchMock = vi
        .fn()
        .mockResolvedValue({ ok: true, status: 202 } as Response)
      vi.stubGlobal("fetch", fetchMock)

      const result = await store.sendMessage("sa_1", "keep going")

      expect(result.ok).toBe(true)
      const [url, init] = fetchMock.mock.calls[0]
      expect(url).toBe("http://localhost:8757/api/chat/subagents/sa_1/message")
      expect(JSON.parse((init as RequestInit).body as string)).toEqual({
        content: "keep going",
      })
    })

    it("surfaces a friendly error (and refreshes the list) on 409", async () => {
      const fetchMock = vi
        .fn()
        .mockResolvedValueOnce(jsonResponse([child("sa_1")]))
        .mockResolvedValueOnce({ ok: false, status: 409 } as Response)
        .mockResolvedValueOnce(
          jsonResponse([child("sa_1", { status: "completed" })]),
        )
      vi.stubGlobal("fetch", fetchMock)
      await store.syncForConversation("trace-leaf")

      const result = await store.sendMessage("sa_1", "too late")
      await flush()

      expect(result.ok).toBe(false)
      expect(result.error).toContain("already finished")
      const transcript = get(store.transcripts).get("sa_1") ?? []
      expect(transcript[transcript.length - 1]).toMatchObject({
        role: "error",
        content: expect.stringContaining("already finished"),
      })
      // The terminal status was re-fetched.
      expect(get(store.children)[0].status).toBe("completed")
    })

    it("reports a non-409 failure with the server detail", async () => {
      const fetchMock = vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: () => Promise.resolve({ detail: "Sub-agent not found: sa_1" }),
      } as unknown as Response)
      vi.stubGlobal("fetch", fetchMock)

      const result = await store.sendMessage("sa_1", "hello?")

      expect(result.ok).toBe(false)
      expect(result.error).toBe("Sub-agent not found: sa_1")
    })
  })

  describe("reset", () => {
    it("clears children, transcripts and selection, and re-arms sync", async () => {
      const fetchMock = vi.fn().mockResolvedValue(jsonResponse([child("sa_1")]))
      vi.stubGlobal("fetch", fetchMock)
      await store.syncForConversation("trace-leaf")
      store.select("sa_1")

      store.reset()

      expect(get(store.children)).toEqual([])
      expect(get(store.selectedId)).toBeNull()
      expect(get(store.transcripts).size).toBe(0)
      // The same trace can be re-synced after a reset (dedupe was cleared).
      await store.syncForConversation("trace-leaf")
      expect(get(store.children).map((c) => c.subagent_id)).toEqual(["sa_1"])
    })
  })
})

describe("isTerminalSubagentStatus", () => {
  it("classifies statuses", () => {
    expect(isTerminalSubagentStatus("running")).toBe(false)
    for (const status of ["completed", "failed", "stopped", "timeout"]) {
      expect(isTerminalSubagentStatus(status)).toBe(true)
    }
  })
})
