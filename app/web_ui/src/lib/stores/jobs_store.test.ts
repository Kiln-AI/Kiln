// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest"
import { get, writable } from "svelte/store"
import type { JobRecord } from "./jobs_api"

// ui_state drives the project filter. Provide a real writable so we can flip
// the current project mid-test.
const ui_state = writable<{ current_project_id: string | null }>({
  current_project_id: null,
})

vi.mock("$lib/api_client", () => ({
  base_url: "http://localhost:8757",
  client: {},
}))

vi.mock("$lib/stores", () => ({
  ui_state,
}))

// Spy on every mutation entry point. The store is a pure observer: it must
// never call any of these. We assert that explicitly on teardown below.
const mutationSpies = {
  pause_job: vi.fn(),
  resume_job: vi.fn(),
  cancel_job: vi.fn(),
  delete_job: vi.fn(),
  create_job: vi.fn(),
}
vi.mock("./jobs_api", () => mutationSpies)

// A controllable fake EventSource installed on globalThis. Records construction
// URLs and close() calls so tests can assert the pure-observer / reconnect
// behavior without a real network connection.
type Listener = (event: MessageEvent) => void

class FakeEventSource {
  static instances: FakeEventSource[] = []
  url: string
  closed = false
  onerror: ((this: EventSource, ev: Event) => void) | null = null
  private listeners: Record<string, Listener[]> = {}

  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }

  addEventListener(type: string, listener: Listener) {
    ;(this.listeners[type] ||= []).push(listener)
  }

  close() {
    this.closed = true
  }

  emit(type: string, data: unknown) {
    const event = { data: JSON.stringify(data) } as MessageEvent
    for (const listener of this.listeners[type] || []) {
      listener(event)
    }
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

function makeJob(overrides: Partial<JobRecord> = {}): JobRecord {
  return {
    id: "j_1",
    type: "noop",
    status: "running",
    supports_pause: true,
    created_at: "2026-05-28T12:00:00Z",
    ...overrides,
  }
}

// Import the module fresh per test so the ref-counted connection and the
// module-level ui_state subscription start clean.
async function loadStore() {
  vi.resetModules()
  ui_state.set({ current_project_id: null })
  FakeEventSource.reset()
  return await import("./jobs_store")
}

describe("jobs_store", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    // @ts-expect-error install fake on global
    globalThis.EventSource = FakeEventSource
    for (const spy of Object.values(mutationSpies)) {
      spy.mockClear()
    }
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it("snapshot replaces the whole map", async () => {
    const { jobs } = await loadStore()
    const unsub = jobs.subscribe(() => {})
    const source = FakeEventSource.latest()

    source.emit("snapshot", {
      jobs: [makeJob({ id: "j_1" }), makeJob({ id: "j_2" })],
    })
    expect(
      get(jobs)
        .map((j) => j.id)
        .sort(),
    ).toEqual(["j_1", "j_2"])

    // A second snapshot fully replaces the prior contents.
    source.emit("snapshot", { jobs: [makeJob({ id: "j_3" })] })
    expect(get(jobs).map((j) => j.id)).toEqual(["j_3"])
    unsub()
  })

  it("job event inserts a new job", async () => {
    const { jobs } = await loadStore()
    const unsub = jobs.subscribe(() => {})
    const source = FakeEventSource.latest()
    source.emit("snapshot", { jobs: [] })
    source.emit("job", makeJob({ id: "j_new" }))
    expect(get(jobs).map((j) => j.id)).toEqual(["j_new"])
    unsub()
  })

  it("job event upserts status + progress for an existing job", async () => {
    const { jobs } = await loadStore()
    const unsub = jobs.subscribe(() => {})
    const source = FakeEventSource.latest()
    source.emit("snapshot", {
      jobs: [
        makeJob({
          id: "j_1",
          status: "running",
          progress: { success: 1, error: 0, total: 10 },
        }),
      ],
    })
    source.emit(
      "job",
      makeJob({
        id: "j_1",
        status: "succeeded",
        progress: { success: 10, error: 0, total: 10 },
      }),
    )
    const job = get(jobs)[0]
    expect(job.status).toBe("succeeded")
    expect(job.progress?.success).toBe(10)
    unsub()
  })

  it("deleted event removes a job; unknown id is a no-op", async () => {
    const { jobs } = await loadStore()
    const unsub = jobs.subscribe(() => {})
    const source = FakeEventSource.latest()
    source.emit("snapshot", {
      jobs: [makeJob({ id: "j_1" }), makeJob({ id: "j_2" })],
    })
    source.emit("deleted", { id: "j_1" })
    expect(get(jobs).map((j) => j.id)).toEqual(["j_2"])
    source.emit("deleted", { id: "does_not_exist" })
    expect(get(jobs).map((j) => j.id)).toEqual(["j_2"])
    unsub()
  })

  it("reconnects on error and re-syncs from the fresh snapshot", async () => {
    const { jobs } = await loadStore()
    const unsub = jobs.subscribe(() => {})
    const first = FakeEventSource.latest()
    first.emit("snapshot", { jobs: [makeJob({ id: "stale" })] })
    expect(get(jobs).map((j) => j.id)).toEqual(["stale"])

    first.fail()
    expect(first.closed).toBe(true)

    // After the backoff a new EventSource is constructed.
    vi.advanceTimersByTime(2000)
    expect(FakeEventSource.instances.length).toBe(2)
    const second = FakeEventSource.latest()
    expect(second).not.toBe(first)

    second.emit("snapshot", { jobs: [makeJob({ id: "fresh" })] })
    expect(get(jobs).map((j) => j.id)).toEqual(["fresh"])
    unsub()
  })

  it("active_jobs_count counts only pending/running/paused", async () => {
    const { jobs, active_jobs_count } = await loadStore()
    const unsubJobs = jobs.subscribe(() => {})
    const unsub = active_jobs_count.subscribe(() => {})
    const source = FakeEventSource.latest()
    source.emit("snapshot", {
      jobs: [
        makeJob({ id: "a", status: "pending" }),
        makeJob({ id: "b", status: "running" }),
        makeJob({ id: "c", status: "paused" }),
        makeJob({ id: "d", status: "succeeded" }),
        makeJob({ id: "e", status: "failed" }),
      ],
    })
    expect(get(active_jobs_count)).toBe(3)
    unsub()
    unsubJobs()
  })

  it("closes the EventSource when the last subscriber unsubscribes (pure observer)", async () => {
    const { jobs } = await loadStore()
    const unsub1 = jobs.subscribe(() => {})
    const unsub2 = jobs.subscribe(() => {})
    const source = FakeEventSource.latest()
    // Only one EventSource is opened regardless of subscriber count.
    expect(FakeEventSource.instances.length).toBe(1)

    unsub1()
    expect(source.closed).toBe(false)
    unsub2()
    expect(source.closed).toBe(true)
  })

  it("opens with the project filter and re-opens when the project changes", async () => {
    const { jobs } = await loadStore()
    ui_state.set({ current_project_id: "p_1" })
    const unsub = jobs.subscribe(() => {})
    const first = FakeEventSource.latest()
    expect(first.url).toContain("project_id=p_1")

    ui_state.set({ current_project_id: "p_2" })
    expect(first.closed).toBe(true)
    const second = FakeEventSource.latest()
    expect(second).not.toBe(first)
    expect(second.url).toContain("project_id=p_2")
    unsub()
  })

  it("ignores ui_state changes that don't touch current_project_id", async () => {
    const { jobs } = await loadStore()
    ui_state.set({ current_project_id: "p_1" })
    const unsub = jobs.subscribe(() => {})
    const first = FakeEventSource.latest()
    expect(FakeEventSource.instances.length).toBe(1)

    // An unrelated ui_state update with the same project id must not re-open.
    ui_state.set({ current_project_id: "p_1", other: "x" } as {
      current_project_id: string | null
    })
    expect(FakeEventSource.instances.length).toBe(1)
    expect(first.closed).toBe(false)
    unsub()
  })

  it("reports an errored connection when the stream fails before syncing", async () => {
    const { jobs, connection } = await loadStore()
    const unsub = jobs.subscribe(() => {})
    expect(get(connection)).toBe("connecting")

    FakeEventSource.latest().fail()
    expect(get(connection)).toBe("errored")
    unsub()
  })

  it("connection becomes open once a snapshot arrives", async () => {
    const { jobs, connection } = await loadStore()
    const unsub = jobs.subscribe(() => {})
    FakeEventSource.latest().emit("snapshot", { jobs: [] })
    expect(get(connection)).toBe("open")
    unsub()
  })

  it("never calls a mutation endpoint (pure observer) across its full lifecycle", async () => {
    const { jobs } = await loadStore()
    const unsub = jobs.subscribe(() => {})
    const source = FakeEventSource.latest()

    // Drive every observable path: snapshot, job upsert, deletion, an error +
    // reconnect, a project switch, and finally teardown.
    source.emit("snapshot", { jobs: [makeJob({ id: "j_1" })] })
    source.emit("job", makeJob({ id: "j_1", status: "succeeded" }))
    source.emit("deleted", { id: "j_1" })
    source.fail()
    vi.advanceTimersByTime(2000)
    ui_state.set({ current_project_id: "p_switch" })
    unsub()

    for (const spy of Object.values(mutationSpies)) {
      expect(spy).not.toHaveBeenCalled()
    }
  })
})
