import { derived, get, writable, type Readable } from "svelte/store"
import { base_url } from "$lib/api_client"
import { ui_state } from "$lib/stores"
import type { JobRecord } from "./jobs_api"
import { is_active } from "./job_status"

const RECONNECT_DELAY_MS = 2000

type JobsMap = Map<string, JobRecord>

// Connection state surfaced to the UI so the panel can distinguish "still
// connecting" from "can't connect". Stays a pure observer: this only reports
// the EventSource lifecycle, it never triggers a job mutation.
export type JobsConnection = "idle" | "connecting" | "open" | "errored"

function createJobsStore() {
  const jobs_map = writable<JobsMap>(new Map())

  // True once the first `snapshot` event for the current connection has been
  // processed. Lets the panel show a loading state until the stream syncs.
  const synced = writable(false)

  // Lifecycle of the underlying EventSource. The panel pairs this with `synced`
  // to show a "can't connect / retrying" affordance instead of spinning forever
  // when the stream errors before its first snapshot.
  const connection = writable<JobsConnection>("idle")

  let event_source: EventSource | null = null
  let reconnect_timer: ReturnType<typeof setTimeout> | null = null
  let subscriber_count = 0
  let current_project_id: string | null = null

  function build_url(): string {
    const url = new URL(`${base_url}/api/jobs/events`)
    if (current_project_id) {
      url.searchParams.set("project_id", current_project_id)
    }
    return url.toString()
  }

  function upsert(record: JobRecord) {
    jobs_map.update((map) => {
      const next = new Map(map)
      next.set(record.id, record)
      return next
    })
  }

  function remove(id: string) {
    jobs_map.update((map) => {
      if (!map.has(id)) {
        return map
      }
      const next = new Map(map)
      next.delete(id)
      return next
    })
  }

  function replace_all(records: JobRecord[]) {
    const next: JobsMap = new Map()
    for (const record of records) {
      next.set(record.id, record)
    }
    jobs_map.set(next)
  }

  function handle_snapshot(event: MessageEvent) {
    try {
      const parsed = JSON.parse(event.data) as { jobs?: JobRecord[] }
      replace_all(parsed.jobs ?? [])
      synced.set(true)
      connection.set("open")
    } catch {
      // Ignore malformed payloads; the next snapshot will re-sync.
    }
  }

  function handle_job(event: MessageEvent) {
    try {
      const record = JSON.parse(event.data) as JobRecord
      upsert(record)
    } catch {
      // Ignore malformed payloads.
    }
  }

  function handle_deleted(event: MessageEvent) {
    try {
      const parsed = JSON.parse(event.data) as { id?: string }
      if (parsed.id) {
        remove(parsed.id)
      }
    } catch {
      // Ignore malformed payloads.
    }
  }

  function clear_reconnect() {
    if (reconnect_timer !== null) {
      clearTimeout(reconnect_timer)
      reconnect_timer = null
    }
  }

  function schedule_reconnect() {
    if (reconnect_timer !== null || subscriber_count === 0) {
      return
    }
    reconnect_timer = setTimeout(() => {
      reconnect_timer = null
      if (subscriber_count > 0) {
        connect()
      }
    }, RECONNECT_DELAY_MS)
  }

  function close_source() {
    if (event_source) {
      event_source.close()
      event_source = null
    }
  }

  function connect() {
    // Pure observer: opening or closing this stream never affects a job. A
    // dropped connection is recovered by reconnecting; the fresh `snapshot`
    // re-syncs the map (no Last-Event-ID needed).
    const EventSourceCtor = globalThis.EventSource
    if (!EventSourceCtor) {
      return
    }
    close_source()
    clear_reconnect()
    synced.set(false)
    connection.set("connecting")

    const source = new EventSourceCtor(build_url())
    event_source = source

    source.addEventListener("snapshot", handle_snapshot as EventListener)
    source.addEventListener("job", handle_job as EventListener)
    source.addEventListener("deleted", handle_deleted as EventListener)
    source.onerror = () => {
      // Only reconnect if this is still the active source (avoids racing a
      // teardown or a project switch).
      if (event_source !== source) {
        return
      }
      close_source()
      connection.set("errored")
      schedule_reconnect()
    }
  }

  function disconnect() {
    close_source()
    clear_reconnect()
    synced.set(false)
    connection.set("idle")
  }

  // Re-open the stream against a new project filter. Called by the ui_state
  // subscription below and exposed for tests.
  function set_project(project_id: string | null) {
    if (project_id === current_project_id) {
      return
    }
    current_project_id = project_id
    if (subscriber_count > 0) {
      connect()
    }
  }

  // Track the active project from UI state so the badge/panel stay scoped to
  // the project the user is viewing. `ui_state` fires on any field change, so
  // we react only when `current_project_id` actually differs from what we last
  // saw — keeping rapid project switches correct (the old source is closed by
  // `connect()` before the new one opens, so there's no leak).
  current_project_id = get(ui_state).current_project_id ?? null
  let last_seen_project_id = current_project_id
  ui_state.subscribe((state) => {
    const next = state.current_project_id ?? null
    if (next === last_seen_project_id) {
      return
    }
    last_seen_project_id = next
    set_project(next)
  })

  const subscribe: Readable<JobsMap>["subscribe"] = (run, invalidate) => {
    if (subscriber_count === 0) {
      connect()
    }
    subscriber_count += 1
    const unsubscribe = jobs_map.subscribe(run, invalidate)
    return () => {
      unsubscribe()
      subscriber_count -= 1
      if (subscriber_count <= 0) {
        subscriber_count = 0
        disconnect()
      }
    }
  }

  return {
    subscribe,
    synced: { subscribe: synced.subscribe } as Readable<boolean>,
    connection: {
      subscribe: connection.subscribe,
    } as Readable<JobsConnection>,
    set_project,
    // Exposed for tests / explicit teardown; not part of normal usage.
    _disconnect: disconnect,
  }
}

export const jobs_store = createJobsStore()

export const synced: Readable<boolean> = jobs_store.synced

export const connection: Readable<JobsConnection> = jobs_store.connection

export const jobs: Readable<JobRecord[]> = derived(jobs_store, ($map) =>
  Array.from($map.values()).sort(
    (a, b) =>
      new Date(b.created_at ?? 0).getTime() -
      new Date(a.created_at ?? 0).getTime(),
  ),
)

export const active_jobs_count: Readable<number> = derived(
  jobs_store,
  ($map) => {
    let count = 0
    for (const job of $map.values()) {
      if (is_active(job.status)) {
        count += 1
      }
    }
    return count
  },
)
