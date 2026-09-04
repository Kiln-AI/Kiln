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
        // Bounded fetch: a hung response must not pin the reconcile loop.
        expect.objectContaining({ signal: expect.anything() }),
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

    it("adds an unknown child directly from a lineage-carrying event, with no fetch", async () => {
      const fetchMock = vi.fn().mockResolvedValue(jsonResponse([]))
      vi.stubGlobal("fetch", fetchMock)
      await store.syncForConversation("cv_parent")

      store.connect()
      FakeEventSource.latest().message({
        type: "conversation-state",
        session_id: "cv_new",
        kind: "subagent",
        state: "running",
        auto_flag: false,
        name: "Agent cv_new",
        agent_type: "general",
        parent_session_id: "cv_parent",
      })
      await flush()

      // Attributed straight from the event: only the initial sync fetched —
      // no list re-fetch competing for connection-pool slots.
      expect(fetchMock).toHaveBeenCalledTimes(1)
      expect(get(store.children)).toMatchObject([
        {
          session_id: "cv_new",
          kind: "subagent",
          state: "running",
          name: "Agent cv_new",
          agent_type: "general",
          parent_session_id: "cv_parent",
          report_available: false,
        },
      ])
    })

    it("backfills a null agent_type from a later state event, never overwriting a known one", async () => {
      // A child added from an event predating the agent_type field carries
      // null identity; the next state event patches it in. Identity is
      // immutable, so an established value is never replaced.
      const fetchMock = vi.fn().mockResolvedValue(jsonResponse([]))
      vi.stubGlobal("fetch", fetchMock)
      await store.syncForConversation("cv_parent")

      store.connect()
      const source = FakeEventSource.latest()
      source.message({
        type: "conversation-state",
        session_id: "cv_new",
        kind: "subagent",
        state: "running",
        auto_flag: false,
        parent_session_id: "cv_parent",
      })
      expect(get(store.children)[0].agent_type).toBeNull()

      source.message({
        type: "conversation-state",
        session_id: "cv_new",
        kind: "subagent",
        state: "running",
        auto_flag: false,
        agent_type: "general",
        parent_session_id: "cv_parent",
      })
      expect(get(store.children)[0].agent_type).toBe("general")

      source.message({
        type: "conversation-state",
        session_id: "cv_new",
        kind: "subagent",
        state: "completed",
        auto_flag: false,
        agent_type: "other",
        parent_session_id: "cv_parent",
      })
      expect(get(store.children)[0].agent_type).toBe("general")
    })

    it("ignores a lineage-carrying event for another conversation's child (no fetch)", async () => {
      const fetchMock = vi.fn().mockResolvedValue(jsonResponse([]))
      vi.stubGlobal("fetch", fetchMock)
      await store.syncForConversation("cv_parent")

      store.connect()
      FakeEventSource.latest().message({
        type: "conversation-state",
        session_id: "cv_foreign",
        kind: "subagent",
        state: "running",
        auto_flag: false,
        parent_session_id: "cv_other_parent",
      })
      await flush()

      expect(fetchMock).toHaveBeenCalledTimes(1)
      expect(get(store.children)).toEqual([])
    })

    it("falls back to a list re-fetch for an unknown child WITHOUT lineage (older desktop)", async () => {
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

    it("reconciles children on a timer so a missed running child appears", async () => {
      // Old-desktop-compat / freak-loss safety net: direct attribution from
      // lineage-carrying events is the primary path now, but while the
      // firehose is connected and a parent is set a low-frequency reconcile
      // still re-fetches the list, so a child that slipped through every
      // event path converges without a manual refresh.
      vi.useFakeTimers()
      try {
        const fetchMock = vi
          .fn()
          .mockResolvedValueOnce(jsonResponse([])) // initial sync: empty
          .mockResolvedValue(jsonResponse([child("cv_late")])) // reconcile ticks
        vi.stubGlobal("fetch", fetchMock)

        await store.syncForConversation("trace-leaf")
        store.connect()
        expect(get(store.children)).toEqual([])

        await vi.advanceTimersByTimeAsync(20_000)

        expect(get(store.children).map((c) => c.session_id)).toEqual([
          "cv_late",
        ])
      } finally {
        vi.useRealTimers()
      }
    })

    it("stops reconciling after disconnect", async () => {
      vi.useFakeTimers()
      try {
        const fetchMock = vi.fn().mockResolvedValue(jsonResponse([]))
        vi.stubGlobal("fetch", fetchMock)

        await store.syncForConversation("trace-leaf")
        store.connect()
        await vi.advanceTimersByTimeAsync(20_000) // one reconcile fetch
        const callsAfterOneTick = fetchMock.mock.calls.length
        expect(callsAfterOneTick).toBeGreaterThan(1)

        store.disconnect()
        await vi.advanceTimersByTimeAsync(80_000) // several intervals

        // No further reconcile fetches once the firehose is disconnected.
        expect(fetchMock.mock.calls.length).toBe(callsAfterOneTick)
      } finally {
        vi.useRealTimers()
      }
    })

    it("does not reconcile when no parent is set", async () => {
      // Connected but with no conversation attached: nothing to reconcile, so
      // the timer must never fire a fetch (no thrashing on a blank page).
      vi.useFakeTimers()
      try {
        const fetchMock = vi.fn().mockResolvedValue(jsonResponse([]))
        vi.stubGlobal("fetch", fetchMock)

        store.connect()
        await vi.advanceTimersByTimeAsync(80_000)

        expect(fetchMock).not.toHaveBeenCalled()
      } finally {
        vi.useRealTimers()
      }
    })
  })

  describe("children fetch resilience", () => {
    it("a failed same-parent re-fetch keeps the current children (no flicker)", async () => {
      vi.useFakeTimers()
      try {
        const fetchMock = vi
          .fn()
          .mockResolvedValueOnce(jsonResponse([child("cv_1")]))
          .mockRejectedValue(new DOMException("timeout", "TimeoutError"))
        vi.stubGlobal("fetch", fetchMock)

        await store.syncForConversation("trace-leaf")
        store.connect()
        expect(get(store.children).map((c) => c.session_id)).toEqual(["cv_1"])

        await vi.advanceTimersByTimeAsync(20_000) // reconcile tick fails

        // A timeout/blip must not yank running tabs away.
        expect(get(store.children).map((c) => c.session_id)).toEqual(["cv_1"])
      } finally {
        vi.useRealTimers()
      }
    })

    it("a failed fetch releases the in-flight flag so the next reconcile retries", async () => {
      // The regression this guards: reconcile ticks are skipped while a fetch
      // is pending, so a fetch that never settles would blind the strip
      // forever. The fetch is now bounded (AbortSignal.timeout) — the
      // rejection must release the flag and the NEXT tick must fetch again.
      vi.useFakeTimers()
      try {
        const fetchMock = vi
          .fn()
          .mockResolvedValueOnce(jsonResponse([])) // initial sync
          .mockRejectedValueOnce(new DOMException("timeout", "TimeoutError"))
          .mockResolvedValue(jsonResponse([child("cv_recovered")]))
        vi.stubGlobal("fetch", fetchMock)

        await store.syncForConversation("trace-leaf")
        store.connect()

        await vi.advanceTimersByTimeAsync(20_000) // tick 1: times out
        expect(get(store.children)).toEqual([])
        await vi.advanceTimersByTimeAsync(20_000) // tick 2: recovers

        expect(get(store.children).map((c) => c.session_id)).toEqual([
          "cv_recovered",
        ])
        expect(fetchMock.mock.calls.length).toBe(3)
      } finally {
        vi.useRealTimers()
      }
    })

    it("a stale in-flight list fetch does not clobber a child added meanwhile from a state event", async () => {
      // Direct attribution doesn't supersede an in-flight fetch: a list
      // computed BEFORE a spawn can land AFTER the spawn's event already
      // added the tab. The success path must merge the event-added child in —
      // clobbering would blank its tab until the next reconcile and, if
      // selected, abort its observation and yank the selection.
      let resolveList!: (r: Response) => void
      const fetchMock = vi.fn().mockImplementation((url: string) => {
        if (String(url).includes("/api/conversations?")) {
          return new Promise<Response>((resolve) => (resolveList = resolve))
        }
        // The selected child's hydration/events: hang, irrelevant here.
        return new Promise<never>(() => {})
      })
      vi.stubGlobal("fetch", fetchMock)

      const sync = store.syncForConversation("cv_parent")
      store.connect()
      FakeEventSource.latest().message({
        type: "conversation-state",
        session_id: "cv_new",
        kind: "subagent",
        state: "running",
        auto_flag: false,
        parent_session_id: "cv_parent",
      })
      expect(get(store.children).map((c) => c.session_id)).toEqual(["cv_new"])
      store.select("cv_new")

      // The pre-spawn list (fetched before cv_new existed) lands late.
      resolveList(
        jsonResponse([child("cv_old", { parent_session_id: "cv_parent" })]),
      )
      await sync

      expect(get(store.children).map((c) => c.session_id)).toEqual([
        "cv_old",
        "cv_new",
      ])
      // The event-added tab kept its selection (and thus its observation).
      expect(get(store.selectedId)).toBe("cv_new")
    })

    it("a child that settles inside the stale-fetch window survives the fetch with selection intact", async () => {
      // The shield deliberately ignores terminal state: this child was added
      // AFTER the stale fetch started, so the fetch's answer says nothing
      // about it — settling meanwhile must not let the stale fetch yank the
      // transcript and selection while the user reads the failure output.
      let resolveList!: (r: Response) => void
      const fetchMock = vi.fn().mockImplementation((url: string) => {
        if (String(url).includes("/api/conversations?")) {
          return new Promise<Response>((resolve) => (resolveList = resolve))
        }
        // The selected child's hydration/events: hang, irrelevant here.
        return new Promise<never>(() => {})
      })
      vi.stubGlobal("fetch", fetchMock)

      const sync = store.syncForConversation("cv_parent")
      store.connect()
      FakeEventSource.latest().message({
        type: "conversation-state",
        session_id: "cv_flash",
        kind: "subagent",
        state: "running",
        auto_flag: false,
        parent_session_id: "cv_parent",
      })
      store.select("cv_flash")
      // The child settles (terminal) before the pre-spawn list lands.
      FakeEventSource.latest().message({
        type: "conversation-state",
        session_id: "cv_flash",
        kind: "subagent",
        state: "failed",
        auto_flag: false,
        parent_session_id: "cv_parent",
      })
      expect(get(store.children)[0]?.state).toBe("failed")

      // The pre-spawn list (computed before cv_flash existed) lands late.
      resolveList(jsonResponse([]))
      await sync

      expect(get(store.children).map((c) => c.session_id)).toEqual(["cv_flash"])
      expect(get(store.children)[0]?.state).toBe("failed")
      expect(get(store.selectedId)).toBe("cv_flash")
    })

    it("a stale successful fetch does not revert a terminal child to running", async () => {
      // Terminal is monotone: a reconcile row computed before the child
      // settled still says "running" — applying it verbatim would resurrect
      // the tab's live state (and drop the report affordance) for up to a
      // reconcile interval. The event-carried fields must win.
      vi.useFakeTimers()
      try {
        let resolveList!: (r: Response) => void
        const fetchMock = vi
          .fn()
          .mockResolvedValueOnce(
            jsonResponse([child("cv_1", { parent_session_id: "cv_parent" })]),
          )
          .mockImplementationOnce(
            () => new Promise<Response>((resolve) => (resolveList = resolve)),
          )
        vi.stubGlobal("fetch", fetchMock)

        await store.syncForConversation("cv_parent")
        store.connect()
        expect(get(store.children)[0]?.state).toBe("running")

        // Reconcile tick starts the (soon-stale) fetch…
        await vi.advanceTimersByTimeAsync(20_000)
        // …then the child settles via a live state event while it's pending.
        FakeEventSource.latest().message({
          type: "conversation-state",
          session_id: "cv_1",
          kind: "subagent",
          state: "completed",
          auto_flag: false,
          parent_session_id: "cv_parent",
          report_available: true,
        })
        expect(get(store.children)[0]?.state).toBe("completed")

        // The stale row (computed before the settle) lands: still "running".
        resolveList(
          jsonResponse([child("cv_1", { parent_session_id: "cv_parent" })]),
        )
        await vi.advanceTimersByTimeAsync(1)

        const merged = get(store.children)[0]
        expect(merged?.state).toBe("completed")
        expect(merged?.report_available).toBe(true)
      } finally {
        vi.useRealTimers()
      }
    })

    it("a fetch started AFTER the event-add that lacks the child drops it (no ghost tab)", async () => {
      // Counterpart to the stale-fetch shield above: the shield is scoped to
      // fetches that started BEFORE the child was added (they couldn't have
      // known it). A fetch that started after the add and still lacks the
      // child is authoritative absence — e.g. a desktop restart emptied the
      // in-memory registry, so no terminal event will ever arrive. Without
      // the started-at check every reconcile would re-shield the ghost
      // "running" tab forever.
      vi.useFakeTimers()
      try {
        const fetchMock = vi.fn().mockResolvedValue(jsonResponse([]))
        vi.stubGlobal("fetch", fetchMock)
        await store.syncForConversation("cv_parent")

        store.connect()
        FakeEventSource.latest().message({
          type: "conversation-state",
          session_id: "cv_ghost",
          kind: "subagent",
          state: "running",
          auto_flag: false,
          parent_session_id: "cv_parent",
        })
        expect(get(store.children).map((c) => c.session_id)).toEqual([
          "cv_ghost",
        ])

        // Reconcile tick: this fetch starts 20s after the add and the server
        // (restarted, registry empty) doesn't know the child.
        await vi.advanceTimersByTimeAsync(20_000)
        expect(get(store.children)).toEqual([])

        // And it STAYS gone on subsequent ticks (no re-shield loop).
        await vi.advanceTimersByTimeAsync(20_000)
        expect(get(store.children)).toEqual([])
      } finally {
        vi.useRealTimers()
      }
    })

    it("a failed cross-parent fetch clears the previous parent's children", async () => {
      const fetchMock = vi
        .fn()
        .mockResolvedValueOnce(jsonResponse([child("cv_1")]))
        .mockRejectedValue(new Error("unreachable"))
      vi.stubGlobal("fetch", fetchMock)

      await store.syncForConversation("parent-a")
      expect(get(store.children).map((c) => c.session_id)).toEqual(["cv_1"])

      await store.syncForConversation("parent-b")

      // Another conversation's children must never linger under this one.
      expect(get(store.children)).toEqual([])
    })

    it("a failed cross-parent fetch keeps the NEW parent's children added from events meanwhile", async () => {
      // Switch A→B whose first fetch fails: A's children must clear, but a
      // B-child attributed from a state event during the fetch window is
      // event-proven — a fetch FAILURE is not authoritative and must not
      // wipe it.
      let rejectList!: (e: Error) => void
      const fetchMock = vi
        .fn()
        .mockResolvedValueOnce(
          jsonResponse([child("cv_a", { parent_session_id: "parent-a" })]),
        )
        .mockImplementationOnce(
          () => new Promise<Response>((_, reject) => (rejectList = reject)),
        )
      vi.stubGlobal("fetch", fetchMock)

      await store.syncForConversation("parent-a")
      expect(get(store.children).map((c) => c.session_id)).toEqual(["cv_a"])

      const sync = store.syncForConversation("parent-b")
      store.connect()
      FakeEventSource.latest().message({
        type: "conversation-state",
        session_id: "cv_b",
        kind: "subagent",
        state: "running",
        auto_flag: false,
        parent_session_id: "parent-b",
      })
      rejectList(new Error("unreachable"))
      await sync

      expect(get(store.children).map((c) => c.session_id)).toEqual(["cv_b"])
    })

    it("reconnects when the firehose connect wedges before open", async () => {
      vi.useFakeTimers()
      try {
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse([])))
        store.connect()
        const wedged = FakeEventSource.latest()
        expect(get(store.connection)).toBe("connecting")

        // Neither onopen nor onerror ever fires (server stalled before
        // headers): the watchdog must give up and schedule a reconnect.
        await vi.advanceTimersByTimeAsync(15000)
        expect(wedged.closed).toBe(true)
        expect(get(store.connection)).toBe("errored")

        await vi.advanceTimersByTimeAsync(2000) // RECONNECT_DELAY_MS
        expect(FakeEventSource.latest()).not.toBe(wedged)
      } finally {
        vi.useRealTimers()
      }
    })

    it("the connect watchdog does not kill a firehose that opened", async () => {
      vi.useFakeTimers()
      try {
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse([])))
        store.connect()
        const source = FakeEventSource.latest()
        source.open()
        expect(get(store.connection)).toBe("open")

        await vi.advanceTimersByTimeAsync(60000)

        expect(source.closed).toBe(false)
        expect(get(store.connection)).toBe("open")
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
        "http://localhost:8757/api/chat/sessions/cv_1": () =>
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
        "http://localhost:8757/api/chat/sessions/cv_1": () =>
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

    it("hydrates by SESSION id — the desktop resolves the fresh leaf per request", async () => {
      // Phase 5: current_trace_id (and the pre-hydration item re-fetch that
      // kept it fresh) are gone — hydration fetches /api/chat/sessions/{sid}
      // and the DESKTOP resolves the record's current leaf, so a stale list
      // entry can no longer hydrate a stale snapshot.
      routeFetch({
        "http://localhost:8757/api/conversations?": () =>
          jsonResponse([child("cv_1")]),
        "http://localhost:8757/api/conversations/cv_1/events": () =>
          sseResponse([]),
        "http://localhost:8757/api/chat/sessions/cv_1": () =>
          jsonResponse({ id: "trace-fresh", task_run: { trace: [] } }),
      })
      const fetchMock = vi.mocked(globalThis.fetch)
      await store.syncForConversation("trace-leaf")

      store.select("cv_1")
      await flush()

      const sessionCalls = fetchMock.mock.calls
        .map((c) => String(c[0]))
        .filter((u) => u.includes("/api/chat/sessions/"))
      expect(sessionCalls).toEqual([
        "http://localhost:8757/api/chat/sessions/cv_1",
      ])
      // No item fetch rides observe() anymore (its only job was the leaf).
      const itemCalls = fetchMock.mock.calls
        .map((c) => String(c[0]))
        .filter((u) => u.endsWith("/api/conversations/cv_1"))
      expect(itemCalls).toEqual([])
    })

    it("a failed re-hydration on re-select keeps the transcript from the previous observation", async () => {
      // select() keeps a deselected child's transcript for instant repaint
      // and re-hydrates on re-select; a hydration blip (network throw or a
      // non-404 error status) must not blank what was deliberately kept.
      let hydrationResult: "ok" | "network" | "http500" = "ok"
      const fetchMock = vi.fn().mockImplementation((url: string) => {
        const u = String(url)
        if (u.includes("/api/conversations?")) {
          return Promise.resolve(jsonResponse([child("cv_1")]))
        }
        if (u.includes("/api/conversations/cv_1/events")) {
          return Promise.resolve(sseResponse([]))
        }
        if (u.includes("/api/chat/sessions/cv_1")) {
          if (hydrationResult === "network") {
            return Promise.reject(new Error("network down"))
          }
          if (hydrationResult === "http500") {
            return Promise.resolve({
              ok: false,
              status: 500,
            } as unknown as Response)
          }
          return Promise.resolve(
            jsonResponse({
              id: "trace-cv_1",
              task_run: {
                trace: [
                  { role: "user", content: "briefing" },
                  { role: "assistant", content: "persisted turn" },
                ],
              },
            }),
          )
        }
        return Promise.reject(new Error(`Unmatched fetch: ${u}`))
      })
      vi.stubGlobal("fetch", fetchMock)
      await store.syncForConversation("trace-leaf")

      store.select("cv_1")
      await flush()
      expect(
        (get(store.transcripts).get("cv_1") ?? []).map((m) => m.role),
      ).toEqual(["user", "assistant"])

      // Switch away (stream torn down, transcript kept), then back with the
      // hydration endpoint throwing.
      store.select(null)
      hydrationResult = "network"
      store.select("cv_1")
      await flush()
      expect(
        (get(store.transcripts).get("cv_1") ?? []).map((m) => m.role),
      ).toEqual(["user", "assistant"])

      // Same for an error status (a 404 stays authoritative: not covered
      // here — "nothing persisted" makes the empty transcript the truth).
      store.select(null)
      hydrationResult = "http500"
      store.select("cv_1")
      await flush()
      expect(
        (get(store.transcripts).get("cv_1") ?? []).map((m) => m.role),
      ).toEqual(["user", "assistant"])
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
        "http://localhost:8757/api/chat/sessions/cv_1": () =>
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
        "http://localhost:8757/api/chat/sessions/cv_1": () =>
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

      // The live-only affordances die with the stream; the entry survives
      // (reset) so a persistent field like contextUsage isn't lost.
      const cleared = get(store.runtime).get("cv_1")
      expect(cleared?.showActivityIndicator).toBe(false)
      expect(cleared?.retry).toBeNull()
    })

    it("seeds the child's context usage from its hydrated snapshot", async () => {
      routeFetch({
        "http://localhost:8757/api/conversations?": () =>
          jsonResponse([child("cv_1")]),
        "http://localhost:8757/api/conversations/cv_1/events": () =>
          sseResponse([]),
        "http://localhost:8757/api/chat/sessions/cv_1": () =>
          jsonResponse({
            id: "trace-cv_1",
            task_run: { trace: [] },
            context_usage: {
              context_tokens: 1000,
              context_limit: 4000,
              context_percent: 25,
              compacted: false,
            },
          }),
      })
      await store.syncForConversation("trace-leaf")

      store.select("cv_1")
      await flush()

      expect(get(store.runtime).get("cv_1")?.contextUsage).toEqual({
        context_tokens: 1000,
        context_limit: 4000,
        context_percent: 25,
        compacted: false,
      })
    })

    it("updates the child's context usage from live kiln_chat_trace events and keeps it after the stream ends", async () => {
      routeFetch(
        observeRoutes([
          {
            type: "kiln_chat_trace",
            trace_id: "trace-live",
            context_usage: {
              context_tokens: 2000,
              context_limit: 4000,
              context_percent: 50,
              compacted: true,
            },
          },
        ]),
      )
      await store.syncForConversation("trace-leaf")

      store.select("cv_1")
      await flush()

      // The sse stream has ended (observation cleaned up); the usage stays.
      expect(get(store.runtime).get("cv_1")?.contextUsage).toEqual({
        context_tokens: 2000,
        context_limit: 4000,
        context_percent: 50,
        compacted: true,
      })
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

    // A never-ending events body + per-child signal capture, so observer
    // stream lifetime can be asserted across tab switches.
    function hangingObserverRoutes(signals: Map<string, AbortSignal>) {
      const hangingBody = {
        getReader: () => ({
          read: () => new Promise<never>(() => {}),
        }),
      }
      const fetchMock = vi
        .fn()
        .mockImplementation((url: string, init?: RequestInit) => {
          const u = String(url)
          if (u.includes("/api/conversations?")) {
            return Promise.resolve(jsonResponse([child("cv_1"), child("cv_2")]))
          }
          const events = u.match(/\/api\/conversations\/(cv_\d+)\/events/)
          if (events) {
            signals.set(events[1], init?.signal as AbortSignal)
            return Promise.resolve({
              ok: true,
              status: 200,
              body: hangingBody,
            } as unknown as Response)
          }
          if (u.includes("/api/chat/sessions/")) {
            return Promise.resolve(
              jsonResponse({ id: "trace", task_run: { trace: [] } }),
            )
          }
          return Promise.reject(new Error(`Unmatched fetch: ${u}`))
        })
      vi.stubGlobal("fetch", fetchMock)
      return fetchMock
    }

    it("only the selected child keeps a live observer stream (switch tears the old one down)", async () => {
      // Every open child stream holds one of the browser's few per-origin
      // connections; the firehose covers status for unselected tabs, so a
      // deselected child's stream must close.
      const signals = new Map<string, AbortSignal>()
      hangingObserverRoutes(signals)
      await store.syncForConversation("trace-leaf")

      store.select("cv_1")
      await flush()
      expect(signals.get("cv_1")?.aborted).toBe(false)

      store.select("cv_2")
      await flush()
      expect(signals.get("cv_1")?.aborted).toBe(true)
      expect(signals.get("cv_2")?.aborted).toBe(false)
      // The deselected child's transcript survives for an instant repaint.
      expect(get(store.transcripts).has("cv_1")).toBe(true)
    })

    it("selecting back to the main agent (null) closes the child's observer", async () => {
      const signals = new Map<string, AbortSignal>()
      hangingObserverRoutes(signals)
      await store.syncForConversation("trace-leaf")

      store.select("cv_1")
      await flush()
      expect(signals.get("cv_1")?.aborted).toBe(false)

      store.select(null)
      expect(signals.get("cv_1")?.aborted).toBe(true)
    })

    it("re-selecting the same child does not tear down its stream", async () => {
      const signals = new Map<string, AbortSignal>()
      const fetchMock = hangingObserverRoutes(signals)
      await store.syncForConversation("trace-leaf")

      store.select("cv_1")
      await flush()
      const callsAfterFirst = fetchMock.mock.calls.length

      store.select("cv_1")
      await flush()
      expect(signals.get("cv_1")?.aborted).toBe(false)
      // observe() is idempotent while active: no re-hydration, no new stream.
      expect(fetchMock.mock.calls.length).toBe(callsAfterFirst)
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
// Main conversation store — the phase-4 generalization of the auto store
// (itself the phase-3 port of auto_run_store.test.ts). The same behavior
// contracts hold; new interactive behaviors are covered alongside: ensure
// (create-or-adopt), the interactive idle transition, approvals fetch/decide,
// the consent event on the observer, and the off-transition no longer
// closing the stream (an off-auto conversation IS the same live interactive
// conversation). Event translation used throughout:
//
//   auto-mode-on{run_id}          → conversation-state{state:"running", auto_flag:true}
//   auto-mode-idle{reason}        → conversation-state{state:"idle", auto_flag:true, idle_reason}
//   auto-mode-off{reason}         → conversation-state{auto_flag:false, idle_reason}
//   old interactive stream end    → conversation-state{state:"idle", auto_flag:false}
// ─────────────────────────────────────────────────────────────────────────────

import {
  createMainConversationStore,
  type MainConversationSink,
  type MainConversationStore,
} from "./conversation_store"
import type {
  AutoModeConsentRequiredPayload,
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
  interactiveIdles: number
  idleMarkers: number
  awaitingApprovals: number
  pendingToolCalls: ToolCallsPendingItem[][]
  consentPayloads: AutoModeConsentRequiredPayload[]
  versionNudges: string[]
  contextUsages: ContextUsage[]
  compactionStatuses: boolean[]
}

function makeMainSink(): { sink: MainConversationSink; calls: SinkCalls } {
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
    interactiveIdles: 0,
    idleMarkers: 0,
    awaitingApprovals: 0,
    pendingToolCalls: [],
    consentPayloads: [],
    versionNudges: [],
    contextUsages: [],
    compactionStatuses: [],
  }
  const sink: MainConversationSink = {
    beginAssistantTurn: () => {
      calls.beginAssistantTurn += 1
    },
    onAssistantMessage: (update) => {
      const draft: ChatMessage = { id: "a", role: "assistant", parts: [] }
      update(draft)
      calls.assistantUpdates.push(draft)
    },
    // Phase 5: the sink no longer receives trace ids — only the fact that a
    // turn persisted (used by the session store's root_id learn).
    onTurnPersisted: () => calls.traces.push("persisted"),
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
    onInteractiveIdle: () => {
      calls.interactiveIdles += 1
    },
    onIdleMarker: () => {
      calls.idleMarkers += 1
    },
    onAwaitingApproval: () => {
      calls.awaitingApprovals += 1
    },
    onToolCallsPending: (items) => calls.pendingToolCalls.push(items),
    onConsentRequired: (p) => calls.consentPayloads.push(p),
    onVersionNudge: (v) => calls.versionNudges.push(v),
  }
  return { sink, calls }
}

// State-event builders for the unified vocabulary (see the translation table
// in the section header).
function stateRunning(sid: string, kind = "auto") {
  return {
    type: "conversation-state",
    session_id: sid,
    kind,
    state: "running",
    auto_flag: kind === "auto",
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

function stateInteractiveIdle(sid: string, reason?: string) {
  // An interactive record's settle: kind interactive, flag off. It may carry
  // an idle_reason (the engine records the auto vocabulary uniformly) which
  // the store must NOT surface (the phase-1 rendering rule).
  return {
    type: "conversation-state",
    session_id: sid,
    kind: "interactive",
    state: "idle",
    auto_flag: false,
    ...(reason ? { idle_reason: reason } : {}),
  }
}

describe("main_conversation_store", () => {
  let store: MainConversationStore
  let calls: SinkCalls

  beforeEach(() => {
    // @ts-expect-error install fake on global
    globalThis.EventSource = FakeEventSource
    FakeEventSource.reset()
    store = createMainConversationStore()
    const made = makeMainSink()
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
      kind: "auto",
      session_id: "cv_1",
      enable_tool_call_id: "call_enable",
    })
    expect(result.ok).toBe(true)

    // Enable POST went out with the seed body to the create endpoint —
    // keyed by SESSION id since phase 5 (browsers never hold trace ids).
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe("http://localhost:8757/api/conversations")
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      kind: "auto",
      session_id: "cv_1",
      enable_tool_call_id: "call_enable",
    })

    // A fresh assistant turn was started and the events stream opened.
    expect(calls.beginAssistantTurn).toBe(1)
    const source = FakeEventSource.latest()
    expect(source.url).toBe(
      "http://localhost:8757/api/conversations/cv_1/events",
    )
    // The enable attach reflects the on-state immediately (assumeAutoOn).
    expect(get(store.autoModeOn)).toBe(true)

    // The running state confirms it from the desktop-owned run.
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

    // Manual enable only arms the conversation: the server flips the record
    // IDLE("armed") without an empty upstream burst, so there's no immediate
    // assistant turn to open — the indicator just turns on.
    const result = await store.requestEnable({
      kind: "auto",
      session_id: "cv_arm",
    })
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

  it("requestEnable on the already-observed conversation flips in place (no re-attach)", async () => {
    // Phase 4: consent accept flips the SAME record the main observer is
    // already attached to — re-attaching would replay the buffer into a
    // transcript that already shows it.
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ session_id: "cv_flip" }),
    })
    vi.stubGlobal("fetch", fetchMock)
    store.attach("cv_flip")
    expect(FakeEventSource.instances.length).toBe(1)
    expect(get(store.autoModeOn)).toBe(false)

    const result = await store.requestEnable({
      kind: "auto",
      session_id: "cv_flip",
      enable_tool_call_id: "call_enable",
    })
    expect(result.ok).toBe(true)
    // The already-open stream carries the burst: a fresh turn was opened
    // BEFORE the POST (no byte can race into the previous bubble), the
    // on-state reflected, and NO second EventSource was created.
    expect(calls.beginAssistantTurn).toBe(1)
    expect(get(store.autoModeOn)).toBe(true)
    expect(get(store.working)).toBe(true)
    expect(FakeEventSource.instances.length).toBe(1)
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

  it("no-session enable (Revision R2) seeds the first message, begins a turn, attaches, clears armed", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ session_id: "cv_new" }),
    })
    vi.stubGlobal("fetch", fetchMock)
    // The conversation was armed client-side (brand-new chat, no record).
    store.arm()
    expect(get(store.armed)).toBe(true)

    // The first send creates the conversation via enable with extra_messages
    // + no session_id.
    const result = await store.requestEnable({
      kind: "auto",
      extra_messages: [{ role: "user", content: "do the thing" }],
    })
    expect(result.ok).toBe(true)

    // The enable POST carried the first message and NO session_id.
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe("http://localhost:8757/api/conversations")
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      kind: "auto",
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

  it("ensure creates-or-adopts the interactive conversation and attaches", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ session_id: "cv_int" }),
    })
    vi.stubGlobal("fetch", fetchMock)

    const result = await store.ensure("tr-leaf")
    expect(result).toEqual({ ok: true, sessionId: "cv_int" })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe("http://localhost:8757/api/conversations")
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      kind: "interactive",
      session_id: "tr-leaf",
    })
    // Attached — but the auto indicator stays OFF for an interactive attach
    // (the marker is the source of truth, not the attach).
    const source = FakeEventSource.latest()
    expect(source.url).toBe(
      "http://localhost:8757/api/conversations/cv_int/events",
    )
    expect(get(store.autoModeOn)).toBe(false)
    expect(get(store.sessionId)).toBe("cv_int")

    // Idempotent while attached: no second create POST.
    const again = await store.ensure("tr-leaf")
    expect(again).toEqual({ ok: true, sessionId: "cv_int" })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it("ensure with assumeAutoOn turns the indicator on immediately (auto-row restore)", async () => {
    // LOW 1: the history restore of an auto-active row keeps the old
    // attach's instant indicator instead of waiting for the state marker.
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ session_id: "cv_auto_row" }),
    })
    vi.stubGlobal("fetch", fetchMock)
    const result = await store.ensure("tr-auto", {
      openInflightTurn: true,
      assumeAutoOn: true,
    })
    expect(result.ok).toBe(true)
    expect(get(store.autoModeOn)).toBe(true)
    // A later off marker still drives the off transition (flagSeenOn was
    // primed by the optimistic attach, like the old terminal off marker).
    FakeEventSource.latest().message(stateOff("cv_auto_row", "user_stopped"))
    expect(get(store.autoModeOn)).toBe(false)
    expect(calls.offReasons).toEqual(["user_stopped"])
  })

  it("a replayed echo + error with a silent idle marker leaves working=false and fires no settle hooks (HIGH-1)", async () => {
    // Re-attach to a conversation whose last turn ended in a terminal
    // upstream error: the buffer (never reset — no trace persisted) replays
    // the user-message echo and the error event, then the on-subscribe
    // marker reports idle. The marker must clear working WITHOUT firing the
    // settle hooks (which flush queued messages).
    store.attach("cv_err", undefined, true)
    const source = FakeEventSource.latest()
    // Buffer replay: the echo of the failed turn's message…
    source.message({ type: "user-message", content: "please add", id: "cm_x" })
    expect(get(store.working)).toBe(true)
    // …the terminal error the engine emitted…
    source.message({ type: "error", message: "Something went wrong." })
    expect(calls.errors).toEqual(["Something went wrong."])
    // …then the on-subscribe idle marker (interactive kind, flag off).
    source.message(stateInteractiveIdle("cv_err", "error"))
    expect(get(store.working)).toBe(false)
    // Markers fire NO settle hooks — the composer reset is
    // onWorkingChange(false)'s job in the session store.
    expect(calls.interactiveIdles).toBe(0)
    expect(calls.idleReasons).toEqual([])
    // The working timeline told the session store to reset: … true → false.
    expect(calls.working[calls.working.length - 1]).toBe(false)
  })

  describe("FR5: observer drop → no fake off, bounded re-attach", () => {
    beforeEach(() => {
      vi.useFakeTimers()
    })
    afterEach(() => {
      vi.useRealTimers()
    })

    const EVENTS_URL = (sid: string) =>
      `http://localhost:8757/api/conversations/${sid}/events`

    it("an AUTO drop keeps flag/offReason and schedules a 2s re-attach", () => {
      store.attach("cv_auto_drop", undefined, false, true)
      const first = FakeEventSource.latest()
      first.open()
      first.message(stateRunning("cv_auto_drop"))
      expect(get(store.autoModeOn)).toBe(true)

      first.fail()
      // A connection fact, never a run fact: no off transition, no fake off.
      expect(get(store.autoModeOn)).toBe(true)
      expect(calls.offReasons).toEqual([])
      expect(get(store.offReason)).toBeNull()
      expect(get(store.connection)).toBe("closed")
      expect(get(store.reconnecting)).toBe(true)
      // No inline error yet — the bounded re-attach owns recovery.
      expect(calls.errors).toEqual([])
      // The working affordance resets (composer unstuck) without any settle.
      expect(get(store.working)).toBe(false)

      // 2s later a fresh observer attaches to the SAME events URL, carrying
      // the current flag (assumeAutoOn) so the indicator never flickers.
      vi.advanceTimersByTime(2000)
      const second = FakeEventSource.latest()
      expect(second).not.toBe(first)
      expect(second.url).toBe(EVENTS_URL("cv_auto_drop"))
      expect(get(store.autoModeOn)).toBe(true)
      second.open()
      expect(get(store.connection)).toBe("open")
      expect(get(store.reconnecting)).toBe(false)
    })

    it("re-attaches at 2s/5s/10s then surfaces ONE inline error, flag still on", () => {
      store.attach("cv_bounded", undefined, false, true)
      FakeEventSource.latest().open()
      FakeEventSource.latest().message(stateRunning("cv_bounded"))
      const baseline = FakeEventSource.instances.length

      // Attempt 1 after 2s.
      FakeEventSource.latest().fail()
      vi.advanceTimersByTime(1999)
      expect(FakeEventSource.instances.length).toBe(baseline)
      vi.advanceTimersByTime(1)
      expect(FakeEventSource.instances.length).toBe(baseline + 1)

      // Attempt 2 after 5s (not sooner).
      FakeEventSource.latest().fail()
      vi.advanceTimersByTime(4999)
      expect(FakeEventSource.instances.length).toBe(baseline + 1)
      vi.advanceTimersByTime(1)
      expect(FakeEventSource.instances.length).toBe(baseline + 2)

      // Attempt 3 after 10s.
      FakeEventSource.latest().fail()
      vi.advanceTimersByTime(10000)
      expect(FakeEventSource.instances.length).toBe(baseline + 3)

      // Budget exhausted: give up with ONE inline error; the flag holds
      // (the run is desktop-owned — the next send/ensure re-attaches).
      FakeEventSource.latest().fail()
      expect(calls.errors).toEqual([
        "Lost the connection to the assistant. Please try again.",
      ])
      expect(get(store.reconnecting)).toBe(false)
      expect(get(store.autoModeOn)).toBe(true)
      expect(calls.offReasons).toEqual([])
      expect(get(store.sessionId)).toBe("cv_bounded")
      vi.advanceTimersByTime(60_000)
      expect(FakeEventSource.instances.length).toBe(baseline + 3)
    })

    it("a successful re-attach (first event delivered) resets the attempt budget", () => {
      store.attach("cv_reset", undefined, false, true)
      FakeEventSource.latest().open()
      FakeEventSource.latest().fail()
      vi.advanceTimersByTime(2000)
      const second = FakeEventSource.latest()
      // Established again — the stream DELIVERED an event, not merely
      // opened: a later drop starts a FRESH bounded cycle.
      second.open()
      second.message(stateRunning("cv_reset"))
      second.fail()
      const count = FakeEventSource.instances.length
      // Back at the first backoff step (2s), not the second (5s).
      vi.advanceTimersByTime(2000)
      expect(FakeEventSource.instances.length).toBe(count + 1)
      expect(calls.errors).toEqual([])
    })

    it("a flapping stream (opens, then drops before any event) still exhausts the budget", () => {
      store.attach("cv_flap", undefined, false, true)
      FakeEventSource.latest().open()
      FakeEventSource.latest().message(stateRunning("cv_flap"))
      const baseline = FakeEventSource.instances.length

      // Every re-attach OPENS but delivers nothing before dropping — onopen
      // alone must not refill the budget, or this flaps forever.
      FakeEventSource.latest().fail()
      for (const delay of [2000, 5000, 10000]) {
        vi.advanceTimersByTime(delay)
        const source = FakeEventSource.latest()
        source.open()
        source.fail()
      }
      expect(FakeEventSource.instances.length).toBe(baseline + 3)
      expect(calls.errors).toEqual([
        "Lost the connection to the assistant. Please try again.",
      ])
      expect(get(store.reconnecting)).toBe(false)
      vi.advanceTimersByTime(60_000)
      expect(FakeEventSource.instances.length).toBe(baseline + 3)
    })

    it("a direct attach() starts a fresh budget (spent attempts don't leak across streams)", () => {
      // Burn two attempts on the first conversation's stream…
      store.attach("cv_spend", undefined, false, true)
      FakeEventSource.latest().open()
      FakeEventSource.latest().message(stateRunning("cv_spend"))
      FakeEventSource.latest().fail()
      vi.advanceTimersByTime(2000)
      FakeEventSource.latest().open()
      FakeEventSource.latest().fail()

      // …then attach directly to a DIFFERENT conversation: the budget is
      // per-stream, so its first drop re-attaches at the first backoff step
      // with the full three attempts ahead of it.
      store.attach("cv_fresh", undefined, false, true)
      const fresh = FakeEventSource.latest()
      expect(fresh.url).toBe(EVENTS_URL("cv_fresh"))
      fresh.open()
      fresh.fail()
      const count = FakeEventSource.instances.length
      vi.advanceTimersByTime(2000)
      expect(FakeEventSource.instances.length).toBe(count + 1)
      expect(FakeEventSource.latest().url).toBe(EVENTS_URL("cv_fresh"))
      expect(calls.errors).toEqual([])
    })

    it("detach during the backoff window cancels the pending re-attach", () => {
      store.attach("cv_cancel", undefined, false, true)
      FakeEventSource.latest().open()
      FakeEventSource.latest().fail()
      expect(get(store.reconnecting)).toBe(true)
      const count = FakeEventSource.instances.length
      store.detach()
      expect(get(store.reconnecting)).toBe(false)
      vi.advanceTimersByTime(60_000)
      expect(FakeEventSource.instances.length).toBe(count)
      expect(calls.errors).toEqual([])
    })

    it("a mid-turn INTERACTIVE drop re-attaches; an idle drop stays silent", () => {
      // Mid-turn: a turn was visibly in flight, so the connection still
      // matters — reconnect instead of the old immediate inline error.
      store.attach("cv_int_drop")
      let source = FakeEventSource.latest()
      source.open()
      source.message(stateRunning("cv_int_drop", "interactive"))
      expect(get(store.working)).toBe(true)
      source.fail()
      expect(calls.errors).toEqual([])
      expect(get(store.working)).toBe(false)
      expect(get(store.reconnecting)).toBe(true)
      const count = FakeEventSource.instances.length
      vi.advanceTimersByTime(2000)
      expect(FakeEventSource.instances.length).toBe(count + 1)
      // The session id survives throughout (manual paths keep working).
      expect(get(store.sessionId)).toBe("cv_int_drop")

      // Idle drop: no request was in flight (the old world showed nothing
      // either) — no re-attach, no error; the next send/ensure recovers.
      store.detach()
      store.attach("cv_idle_drop")
      source = FakeEventSource.latest()
      source.open()
      source.message(stateInteractiveIdle("cv_idle_drop"))
      const idleCount = FakeEventSource.instances.length
      source.fail()
      expect(get(store.reconnecting)).toBe(false)
      vi.advanceTimersByTime(60_000)
      expect(FakeEventSource.instances.length).toBe(idleCount)
      expect(calls.errors).toEqual([])
      expect(get(store.connection)).toBe("closed")
    })

    it("an interactive mid-turn drop chains 2s/5s/10s then surfaces ONE inline error", () => {
      // Each scheduled re-attach resets `working`, so the chain must carry
      // on via the unsettled attempt count (reattachAttempt > 0), not the
      // working flag — otherwise the interactive chain dies silently after
      // one attempt with no inline error ever surfacing.
      store.attach("cv_int_chain")
      FakeEventSource.latest().open()
      FakeEventSource.latest().message(
        stateRunning("cv_int_chain", "interactive"),
      )
      const baseline = FakeEventSource.instances.length

      FakeEventSource.latest().fail()
      for (const [i, delay] of [2000, 5000, 10000].entries()) {
        expect(calls.errors).toEqual([])
        expect(get(store.reconnecting)).toBe(true)
        vi.advanceTimersByTime(delay)
        expect(FakeEventSource.instances.length).toBe(baseline + i + 1)
        const source = FakeEventSource.latest()
        source.open()
        source.fail()
      }

      // Budget exhausted: exactly ONE inline error, then the manual paths
      // own recovery (no further scheduled attempts).
      expect(calls.errors).toEqual([
        "Lost the connection to the assistant. Please try again.",
      ])
      expect(get(store.reconnecting)).toBe(false)
      expect(get(store.sessionId)).toBe("cv_int_chain")
      vi.advanceTimersByTime(60_000)
      expect(FakeEventSource.instances.length).toBe(baseline + 3)

      // The chain state doesn't strand: after a direct re-attach delivers
      // an event, a later IDLE drop is silent again.
      store.attach("cv_int_chain")
      const fresh = FakeEventSource.latest()
      fresh.open()
      fresh.message(stateInteractiveIdle("cv_int_chain"))
      const count = FakeEventSource.instances.length
      fresh.fail()
      expect(get(store.reconnecting)).toBe(false)
      vi.advanceTimersByTime(60_000)
      expect(FakeEventSource.instances.length).toBe(count)
      expect(calls.errors.length).toBe(1)
    })

    it("stop while 'connection lost' one-shot re-attaches so the off transition renders", async () => {
      // Exhaust the FR5 chain on an auto conversation: connection "closed",
      // no timer pending, flag still on ("connection lost" limbo).
      store.attach("cv_stop_lost", undefined, false, true)
      FakeEventSource.latest().open()
      FakeEventSource.latest().message(stateRunning("cv_stop_lost"))
      FakeEventSource.latest().fail()
      for (const delay of [2000, 5000, 10000]) {
        vi.advanceTimersByTime(delay)
        const source = FakeEventSource.latest()
        source.open()
        source.fail()
      }
      expect(get(store.connection)).toBe("closed")
      expect(get(store.autoModeOn)).toBe(true)
      const count = FakeEventSource.instances.length

      const stopFetch = vi.fn().mockResolvedValue({ ok: true })
      vi.stubGlobal("fetch", stopFetch)
      await store.stop()
      expect(stopFetch).toHaveBeenCalledTimes(1)

      // A fresh observer opens immediately (no backoff wait); its
      // on-subscribe marker delivers the authoritative flag-off, which the
      // attach's flagSeenOn (assumeAutoOn) renders as a real off transition.
      expect(FakeEventSource.instances.length).toBe(count + 1)
      const fresh = FakeEventSource.latest()
      fresh.open()
      fresh.message(stateOff("cv_stop_lost", "user_stopped"))
      expect(get(store.autoModeOn)).toBe(false)
      expect(get(store.offReason)).toBe("user_stopped")
      expect(calls.offReasons).toEqual(["user_stopped"])
      expect(get(store.working)).toBe(false)
    })
  })

  it("an interactive turn: running → idle fires onInteractiveIdle with NO reason exposure", async () => {
    store.attach("cv_turn")
    const source = FakeEventSource.latest()
    // Marker (snapshot): idle interactive — silent (not a settle).
    source.message(stateInteractiveIdle("cv_turn"))
    expect(calls.interactiveIdles).toBe(0)

    // A turn starts and settles: exactly one settle signal — the
    // INTERACTIVE hook, never onAutoModeIdle, and the engine's uniformly
    // recorded idle_reason ("asked_user") is deliberately NOT forwarded
    // (the phase-1 rendering rule: interactive conversations never render
    // idle_reason).
    source.message(stateRunning("cv_turn", "interactive"))
    expect(get(store.working)).toBe(true)
    source.message(stateInteractiveIdle("cv_turn", "asked_user"))
    expect(get(store.working)).toBe(false)
    expect(calls.interactiveIdles).toBe(1)
    expect(calls.idleReasons).toEqual([])
    expect(calls.offReasons).toEqual([])
  })

  it("an idle interactive ATTACH MARKER fires onIdleMarker, not the settle hook (BUG 2)", () => {
    // The LIVE idle event can be missed when the observer is detached at the
    // settle instant; on (re)subscribe only the on-subscribe idle marker
    // arrives. The settle hook stays silent (a marker is not a settle) but the
    // dedicated flush-only onIdleMarker fires so a client-held queued message
    // can still be flushed instead of stranding forever.
    store.attach("cv_marker")
    const source = FakeEventSource.latest()
    source.message(stateInteractiveIdle("cv_marker"))
    expect(calls.interactiveIdles).toBe(0)
    expect(calls.idleMarkers).toBe(1)
    expect(get(store.working)).toBe(false)
  })

  it("a LIVE interactive idle fires the settle hook, never the marker hook (BUG 2)", () => {
    store.attach("cv_live")
    const source = FakeEventSource.latest()
    // The first event consumes the attach-marker slot; the idle that follows
    // is a genuine live settle.
    source.message(stateRunning("cv_live", "interactive"))
    source.message(stateInteractiveIdle("cv_live"))
    expect(calls.interactiveIdles).toBe(1)
    expect(calls.idleMarkers).toBe(0)
  })

  it("an auto (flag-on) idle ATTACH MARKER fires the flush-only onIdleMarker too", () => {
    // A message queued mid-burst can strand when the observer drops and the
    // burst settles during the outage: the re-attach marker arrives as
    // idle+flag-on and no live onAutoModeIdle ever fires. The flush-only
    // hook covers that path; the settle hooks stay marker-silent (a marker
    // is not a settle).
    store.attach("cv_auto_marker", undefined, false, true)
    const source = FakeEventSource.latest()
    source.message(stateIdle("cv_auto_marker", "asked_user"))
    expect(calls.idleMarkers).toBe(1)
    expect(calls.interactiveIdles).toBe(0)
    expect(calls.idleReasons).toEqual([])
  })

  it("awaiting_approval signals the approvals hook on marker AND transition", () => {
    store.attach("cv_appr")
    const source = FakeEventSource.latest()
    // Marker: a refreshed tab re-attaching to a parked run must re-surface
    // the box (functional spec §5) — unlike the settle hooks, this one DOES
    // fire on the marker.
    source.message({
      type: "conversation-state",
      session_id: "cv_appr",
      kind: "interactive",
      state: "awaiting_approval",
      auto_flag: false,
    })
    expect(calls.awaitingApprovals).toBe(1)
    expect(get(store.working)).toBe(false)

    // Live transition (a later park on the same stream).
    source.message(stateRunning("cv_appr", "interactive"))
    source.message({
      type: "conversation-state",
      session_id: "cv_appr",
      kind: "interactive",
      state: "awaiting_approval",
      auto_flag: false,
    })
    expect(calls.awaitingApprovals).toBe(2)
  })

  it("tool-calls-pending on the observer stream hands off to the approval sink", async () => {
    store.attach("cv_pend")
    const source = FakeEventSource.latest()
    source.message(stateRunning("cv_pend", "interactive"))

    const items = [
      {
        toolCallId: "tc1",
        toolName: "call_kiln_api",
        input: { path: "/x" },
        requiresApproval: true,
      },
    ]
    source.message({ type: "tool-calls-pending", items })
    // Handed off to the approval machinery (not forwarded to the processor).
    expect(calls.pendingToolCalls.length).toBe(1)
    expect(calls.pendingToolCalls[0]).toEqual(items)
    expect(get(store.working)).toBe(false)
  })

  it("auto-mode-consent-required on the observer hands off the consent payload", () => {
    store.attach("cv_consent")
    const source = FakeEventSource.latest()
    source.message(stateRunning("cv_consent", "interactive"))
    source.message({
      type: "auto-mode-consent-required",
      trigger: "enable_auto_mode",
      gating_tool_call_id: "call_enable",
      enable_tool_call_id: "call_enable",
      reason: "let me work",
      sibling_tool_calls: [],
    })
    // Phase 5: the payload carries no trace id — accept/decline is keyed by
    // the observed conversation's session id.
    expect(calls.consentPayloads).toEqual([
      {
        trigger: "enable_auto_mode",
        gatingToolCallId: "call_enable",
        reason: "let me work",
        spawn: null,
        siblingToolCalls: [],
      },
    ])
    // The turn ended with the consent event (the idle state follows).
    expect(get(store.working)).toBe(false)
  })

  it("a spawn-triggered consent event hands off the spawn variant (FR2)", () => {
    store.attach("cv_spawn_consent")
    const source = FakeEventSource.latest()
    source.message(stateRunning("cv_spawn_consent", "interactive"))
    source.message({
      type: "auto-mode-consent-required",
      trigger: "spawn_subagent",
      gating_tool_call_id: "call_spawn",
      spawn: { agent_type: "general", name: "Helper", prompt: "dig in" },
      sibling_tool_calls: [],
    })
    expect(calls.consentPayloads).toEqual([
      {
        trigger: "spawn_subagent",
        gatingToolCallId: "call_spawn",
        reason: null,
        spawn: {
          agentType: "general",
          name: "Helper",
          prompt: "dig in",
          rawInput: { agent_type: "general", name: "Helper", prompt: "dig in" },
        },
        siblingToolCalls: [],
      },
    ])
    expect(get(store.working)).toBe(false)
  })

  it("a flag-off TRANSITION clears the auto affordances but keeps the stream open", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ session_id: "cv_2" }),
    })
    vi.stubGlobal("fetch", fetchMock)
    await store.requestEnable({ kind: "auto", session_id: "cv_seed" })
    const source = FakeEventSource.latest()
    source.message(stateRunning("cv_2"))
    expect(get(store.autoModeOn)).toBe(true)

    source.message(stateOff("cv_2", "user_disabled"))
    expect(get(store.autoModeOn)).toBe(false)
    expect(get(store.offReason)).toBe("user_disabled")
    expect(calls.offReasons).toEqual(["user_disabled"])
    // Phase 4: an off-auto conversation IS the same live interactive
    // conversation — the observer keeps carrying its turns (the old auto
    // store closed the stream and dropped the session id here).
    expect(source.closed).toBe(false)
    expect(get(store.sessionId)).toBe("cv_2")

    // The conversation continues interactively on the SAME stream: a later
    // idle settle is an interactive one (the off already signalled).
    source.message(stateRunning("cv_2", "interactive"))
    source.message(stateInteractiveIdle("cv_2"))
    expect(calls.interactiveIdles).toBe(1)
    expect(calls.offReasons).toEqual(["user_disabled"])
  })

  it("stop posts to the conversation's stop endpoint without flipping state locally", async () => {
    const enableFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ session_id: "cv_3" }),
    })
    vi.stubGlobal("fetch", enableFetch)
    await store.requestEnable({ kind: "auto", session_id: "cv_seed" })
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

  it("stop with cascade posts ?cascade=true (kill the whole tree)", async () => {
    const enableFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ session_id: "cv_3" }),
    })
    vi.stubGlobal("fetch", enableFetch)
    await store.requestEnable({ kind: "auto", session_id: "cv_seed" })
    FakeEventSource.latest().message(stateRunning("cv_3"))

    const stopFetch = vi.fn().mockResolvedValue({ ok: true })
    vi.stubGlobal("fetch", stopFetch)
    await store.stop({ cascade: true })

    expect(stopFetch).toHaveBeenCalledTimes(1)
    expect(stopFetch.mock.calls[0][0]).toBe(
      "http://localhost:8757/api/conversations/cv_3/stop?cascade=true",
    )
  })

  it("decline posts the fold-in body to /{sid}/auto and opens a fresh turn", async () => {
    store.attach("cv_dec")
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 202 })
    vi.stubGlobal("fetch", fetchMock)

    await store.decline({
      gating_tool_call_id: "call_1",
      siblings: [],
    })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0]
    // The old /api/conversations/auto/decline endpoint died in phase 4; the
    // decline rides POST /{sid}/auto with enabled=false + the consent ctx
    // (gating_tool_call_id since FR2 — the gating call can be an enable OR a
    // spawn; the desktop route also accepts the legacy spelling).
    expect(url).toBe("http://localhost:8757/api/conversations/cv_dec/auto")
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      enabled: false,
      decline: { gating_tool_call_id: "call_1", siblings: [] },
    })
    // A fresh assistant turn renders the declined continuation, which
    // streams on the ALREADY-OPEN observer (the old endpoint streamed the
    // response body instead).
    expect(calls.beginAssistantTurn).toBe(1)
    expect(get(store.working)).toBe(true)
    const source = FakeEventSource.latest()
    source.message({ type: "text-start", id: "x" })
    source.message({ type: "text-delta", delta: "resumed" })
    const last = calls.assistantUpdates[calls.assistantUpdates.length - 1]
    expect(last.parts?.[0]).toEqual({ type: "text", text: "resumed" })
  })

  it("sendMessage posts to /messages and returns the echo-dedupe message id", async () => {
    store.attach("cv_inj", undefined, false, true)
    FakeEventSource.latest().message(stateRunning("cv_inj"))

    const messageFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ message_id: "cm_42" }),
    })
    vi.stubGlobal("fetch", messageFetch)
    const result = await store.sendMessage("keep going")

    expect(result.ok).toBe(true)
    expect(result.messageId).toBe("cm_42")
    expect(messageFetch).toHaveBeenCalledTimes(1)
    const [url, init] = messageFetch.mock.calls[0]
    expect(url).toBe("http://localhost:8757/api/conversations/cv_inj/messages")
    expect((init as RequestInit).method).toBe("POST")
    // No trace_id rides the send: the desktop supervisor's own leaf is
    // authoritative.
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      content: "keep going",
    })
    // Send never stops: no /stop call, flag stays on, working set.
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

  it("a failed send clears the optimistic working flag", async () => {
    store.attach("cv_fail")
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      json: () => Promise.resolve({ detail: "finished" }),
    })
    vi.stubGlobal("fetch", fetchMock)
    const result = await store.sendMessage("late")
    expect(result.ok).toBe(false)
    expect(result.error).toBe("finished")
    expect(get(store.working)).toBe(false)
  })

  it("fetchApprovals returns the parked batch; null on 404", async () => {
    store.attach("cv_appr2")
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          batch_id: "ab_1",
          items: [
            {
              toolCallId: "tc1",
              toolName: "add",
              input: {},
              requiresApproval: true,
            },
          ],
        }),
    })
    vi.stubGlobal("fetch", fetchMock)
    const batch = await store.fetchApprovals()
    expect(batch).toEqual({
      batchId: "ab_1",
      items: [
        {
          toolCallId: "tc1",
          toolName: "add",
          input: {},
          requiresApproval: true,
        },
      ],
    })
    expect(fetchMock.mock.calls[0][0]).toBe(
      "http://localhost:8757/api/conversations/cv_appr2/approvals",
    )

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 404 }),
    )
    expect(await store.fetchApprovals()).toBeNull()
  })

  it("decide posts the batch decisions; 409 reports a conflict", async () => {
    store.attach("cv_dec2")
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 202 })
    vi.stubGlobal("fetch", fetchMock)
    const result = await store.decide("ab_1", { tc1: true, tc2: false })
    expect(result.ok).toBe(true)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe(
      "http://localhost:8757/api/conversations/cv_dec2/approvals/decisions",
    )
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      batch_id: "ab_1",
      decisions: { tc1: true, tc2: false },
    })
    // The resumed execution reads as a working turn.
    expect(get(store.working)).toBe(true)

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 409 }),
    )
    const conflict = await store.decide("ab_1", { tc1: true })
    expect(conflict).toEqual({ ok: false, conflict: true })
  })

  it("re-attach opens the events stream and replays buffered events with no gap", () => {
    store.attach("cv_re", undefined, false, true)
    const source = FakeEventSource.latest()
    expect(source.url).toBe(
      "http://localhost:8757/api/conversations/cv_re/events",
    )
    // assumeAutoOn (the auto-row restore path): the indicator reflects
    // immediately, before the marker.
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

  it("connection failure on an AUTO conversation keeps the flag on (FR5: no fake off)", () => {
    vi.useFakeTimers()
    try {
      store.attach("cv_gone", undefined, false, true)
      const source = FakeEventSource.latest()
      expect(get(store.autoModeOn)).toBe(true)

      // EventSource errors before opening (events 404 → unknown/GC'd record).
      expect(() => source.fail()).not.toThrow()
      // The desktop-owned run is unaffected by observer connection loss:
      // the flag holds and the bounded re-attach owns recovery (a real off
      // that happened server-side arrives via the re-attach marker).
      expect(get(store.autoModeOn)).toBe(true)
      expect(source.closed).toBe(true)
      expect(calls.offReasons).toEqual([])
      expect(get(store.connection)).toBe("closed")
      expect(get(store.reconnecting)).toBe(true)
      // Cancel the scheduled re-attach so no timer leaks past the test.
      store.detach()
    } finally {
      vi.useRealTimers()
    }
  })

  it("connection failure on an INTERACTIVE conversation keeps the session id (re-attachable)", () => {
    store.attach("cv_gone_int")
    const source = FakeEventSource.latest()
    source.fail()
    // No off signal (nothing was on); the id survives so the next
    // send/ensure can re-attach.
    expect(calls.offReasons).toEqual([])
    expect(get(store.sessionId)).toBe("cv_gone_int")
    expect(get(store.connection)).toBe("closed")
  })

  it("enable 429 returns an error and opens no stream", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 429,
      json: () => Promise.resolve({ detail: "Too many auto runs" }),
    })
    vi.stubGlobal("fetch", fetchMock)

    const result = await store.requestEnable({
      kind: "auto",
      session_id: "cv_seed",
    })
    expect(result.ok).toBe(false)
    expect(result.error).toBe("Too many auto runs")
    expect(get(store.autoModeOn)).toBe(false)
    expect(FakeEventSource.instances.length).toBe(0)
    expect(calls.beginAssistantTurn).toBe(0)
  })

  it("detach closes the observer and clears the indicator without signalling off", () => {
    store.attach("cv_nav", undefined, false, true)
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
    await store.requestEnable({ kind: "auto", session_id: "cv_seed" })
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
    // working timeline: off (armed-only enable attach — no burst to presume)
    // → on (running state) → off (idle).
    expect(calls.working).toEqual([false, true, false])
  })

  it("kiln-chat-retry surfaces retrying progress and clears on the next event", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ session_id: "cv_retry" }),
    })
    vi.stubGlobal("fetch", fetchMock)
    await store.requestEnable({ kind: "auto", session_id: "cv_seed" })
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

  it("a user-message echo renders a fresh user turn and marks working", () => {
    store.attach("cv_echo", undefined, false, true)
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

  it("beginTurn opens a fresh assistant turn AND resets the processor", () => {
    store.attach("cv_turnreset")
    const source = FakeEventSource.latest()
    source.message({ type: "text-start" })
    source.message({ type: "text-delta", delta: "Old turn." })

    store.beginTurn()
    expect(calls.beginAssistantTurn).toBe(1)

    source.message({ type: "text-start" })
    source.message({ type: "text-delta", delta: "New turn." })
    const last = calls.assistantUpdates[calls.assistantUpdates.length - 1]
    const text = (last.parts ?? [])
      .filter((p): p is { type: "text"; text: string } => p.type === "text")
      .map((p) => p.text)
      .join("")
    expect(text).toBe("New turn.")
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

  it("the attach-time idle marker updates state without signaling the idle sinks", () => {
    // The first conversation-state event after attach is the bus's
    // on-subscribe MARKER — a snapshot of where the run already is, not a
    // settle transition. It must reflect flag/working WITHOUT firing
    // sink.onAutoModeIdle / onInteractiveIdle (the session store's settle
    // hooks, which flush queued messages) — the old auto-mode-state marker
    // never fired them.
    store.attach("cv_marker", false, true)
    const source = FakeEventSource.latest()
    source.message(stateIdle("cv_marker", "asked_user"))
    expect(get(store.autoModeOn)).toBe(true)
    expect(get(store.working)).toBe(false)
    expect(calls.idleReasons).toEqual([])
    expect(calls.interactiveIdles).toBe(0)

    // A later REAL settle transition on the same stream does signal.
    source.message(stateRunning("cv_marker"))
    source.message(stateIdle("cv_marker", "done"))
    expect(calls.idleReasons).toEqual(["done"])
  })

  it("a running attach marker consumes the marker slot so the next idle signals", () => {
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
    // A RUNNING conversation (from the resync state) shows working before
    // any event.
    store.beginReconnect()
    store.attach("cv_work", true, false, true)
    expect(get(store.working)).toBe(true)
    expect(get(store.autoModeOn)).toBe(true)

    // An IDLE one (initialWorking=false) shows the idle indicator.
    store.detach()
    store.beginReconnect()
    store.attach("cv_wait", false, false, true)
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

  it("reconnecting clears on error so the affordance can't get stuck", () => {
    store.beginReconnect()
    store.attach("cv_rc_gone")
    expect(get(store.reconnecting)).toBe(true)

    const source = FakeEventSource.latest()
    source.fail() // events 404 / connection failure before opening
    expect(get(store.reconnecting)).toBe(false)
  })

  it("reconnecting clears on a flag-off state and on detach", () => {
    store.beginReconnect()
    store.attach("cv_rc_off", undefined, false, true)
    const source = FakeEventSource.latest()
    source.message(stateOff("cv_rc_off", "user_stopped"))
    expect(get(store.reconnecting)).toBe(false)

    store.beginReconnect()
    expect(get(store.reconnecting)).toBe(true)
    store.detach()
    expect(get(store.reconnecting)).toBe(false)
  })

  it("ignores conversation-state events for sub-agent kinds (defense in depth)", () => {
    // A subagent state event must never flip the main indicator — the
    // observer stream shouldn't carry one, but guard against multiplexing.
    store.attach("cv_kind", undefined, false, true)
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
    await store.requestEnable({ kind: "auto", session_id: "cv_seed" })

    const postSpy = vi.fn().mockResolvedValue({ ok: true })
    vi.stubGlobal("fetch", postSpy)

    const source = FakeEventSource.latest()
    source.message(stateRunning("cv_4"))
    source.message(stateOff("cv_4", "user_stopped"))

    expect(postSpy).not.toHaveBeenCalled()
  })
})
