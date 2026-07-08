/**
 * Owns the sub-agent (child run) state for the active conversation.
 *
 * The desktop server runs sub-agents in the background and exposes them as
 * pure-observer streams (mirroring ``auto_run_store.ts``): observing, stopping
 * observation, or reconnecting never mutates a run. This store tracks the
 * current conversation's children (``syncForConversation`` + a registry-level
 * status firehose, connection handling modeled on ``jobs_store.ts``), and — per
 * observed child — maintains a read-only transcript by hydrating the child's
 * persisted session then feeding its live events SSE into the EXISTING
 * ``StreamEventProcessor``, so a child transcript renders exactly like a main
 * transcript.
 */

import { get, writable, type Readable } from "svelte/store"
import { base_url } from "$lib/api_client"
import type { components } from "$lib/api_schema"
import {
  StreamEventProcessor,
  chatGenerateId,
  consumeSseStream,
  type ChatMessage,
  type StreamEvent,
} from "./streaming_chat"
import {
  hydrateSessionFromSnapshot,
  stripInternalFraming,
  type ChatSessionSnapshot,
} from "./session_messages"

export type SubAgentItem = components["schemas"]["SubAgentItem"]
export type SubAgentStatus = components["schemas"]["SubAgentStatus"]

/**
 * Per-child runtime affordances mirrored from the child's live stream so its
 * transcript renders with the SAME fidelity as the main one (thinking dots via
 * the activity indicator, "retrying N/M…" via the retry state). Runtime-only —
 * cleared when the observation ends.
 */
export interface SubagentRuntimeState {
  showActivityIndicator: boolean
  retry: { attempt: number; max: number } | null
}

const SUBAGENTS_BASE_URL = `${base_url}/api/chat/subagents`
const RECONNECT_DELAY_MS = 2000

// Lifecycle of the status-firehose EventSource, surfaced for tests / debugging.
// A pure observer: this only reports the connection, it never mutates a run.
export type SubagentConnection = "idle" | "connecting" | "open" | "errored"

/**
 * ``kiln-subagent-status`` payload as it arrives on the firehose and on the
 * per-run observer stream (as the on-subscribe liveness marker).
 */
interface SubagentStatusEvent {
  type?: string
  subagent_id?: string
  name?: string
  agent_type?: string
  status?: string
  trace_id?: string | null
  report_available?: boolean
}

const TERMINAL_STATUSES: ReadonlySet<string> = new Set([
  "completed",
  "failed",
  "stopped",
  "timeout",
])

export function isTerminalSubagentStatus(status: string): boolean {
  return TERMINAL_STATUSES.has(status)
}

/** Max individual child tabs before the strip collapses into a count chip. */
export const SUBAGENT_TAB_OVERFLOW_LIMIT = 3

/**
 * Children whose tab is visible in the strip: running ones, plus the currently
 * selected child even when terminal (so the view isn't yanked while the user
 * is reading it — selecting away drops the terminal tab). Purely derived from
 * status + selection (no tombstoning), so a child whose status ever returns to
 * running reappears automatically.
 */
export function visibleSubagentTabs(
  children: SubAgentItem[],
  selectedId: string | null,
): SubAgentItem[] {
  return children.filter(
    (c) => c.status === "running" || c.subagent_id === selectedId,
  )
}

/**
 * Whether the strip should collapse individual child tabs into a single
 * "N agents running" chip (the selected child keeps its own tab beside it).
 */
export function shouldCollapseSubagentTabs(
  visibleChildren: SubAgentItem[],
): boolean {
  return visibleChildren.length > SUBAGENT_TAB_OVERFLOW_LIMIT
}

export interface SubagentStore {
  /** Children of the current conversation (server order). */
  children: Readable<SubAgentItem[]>
  /** Selected tab: a child's subagent_id, or null for the main agent. */
  selectedId: Readable<string | null>
  /** Per-child read-only transcripts, keyed by subagent_id. */
  transcripts: Readable<Map<string, ChatMessage[]>>
  /** Per-child live rendering affordances (activity indicator, retry). */
  runtime: Readable<Map<string, SubagentRuntimeState>>
  connection: Readable<SubagentConnection>
  /** Open the registry-level status firehose (assistant page active). */
  connect(): void
  /** Close the firehose (navigation away). Observers are left alone. */
  disconnect(): void
  /**
   * Replace ``children`` with the sub-agents of the conversation owning the
   * given (possibly stale) leaf trace id — the server resolves the whole trace
   * chain. ``null`` (no conversation yet) clears the list. Deduped by trace id,
   * so it is safe to call on every reactive trace change.
   */
  syncForConversation(parentTraceId: string | null): Promise<void>
  /** Select a tab; selecting a child starts observing it. */
  select(subagentId: string | null): void
  /**
   * Observe one child: hydrate its persisted history, then attach the live
   * events tail (buffer replay + status marker + live). Idempotent while an
   * observation is active; a re-observe after the stream ended re-hydrates.
   */
  observe(subagentId: string): Promise<void>
  stop(subagentId: string): Promise<void>
  sendMessage(
    subagentId: string,
    content: string,
  ): Promise<{ ok: boolean; error?: string }>
  /** Clear everything for a new chat (the firehose connection is kept). */
  reset(): void
  /** Exposed for tests / explicit teardown; not part of normal usage. */
  _close(): void
}

interface ChildObservation {
  abort: AbortController
  // Render the replayed in-flight turn into a FRESH assistant message instead
  // of overwriting the last hydrated one (same rule as auto re-attach).
  pendingFreshTurn: boolean
}

export function createSubagentStore(): SubagentStore {
  const children = writable<SubAgentItem[]>([])
  const selectedId = writable<string | null>(null)
  const transcripts = writable<Map<string, ChatMessage[]>>(new Map())
  const runtime = writable<Map<string, SubagentRuntimeState>>(new Map())
  const connection = writable<SubagentConnection>("idle")

  // The trace id the current children list was fetched for (undefined = never
  // synced). Dedupes reactive syncForConversation calls and keys the firehose
  // "unknown child → re-fetch" rule.
  let syncedTraceId: string | null | undefined = undefined
  let syncGeneration = 0

  let eventSource: EventSource | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  // True between connect() and disconnect(): gates the reconnect loop.
  let firehoseActive = false

  const observations = new Map<string, ChildObservation>()

  // --- Transcript bookkeeping ------------------------------------------------

  function setTranscript(id: string, messages: ChatMessage[]): void {
    transcripts.update((map) => {
      const next = new Map(map)
      next.set(id, messages)
      return next
    })
  }

  function transcriptFor(id: string): ChatMessage[] {
    return get(transcripts).get(id) ?? []
  }

  function appendMessage(id: string, message: ChatMessage): void {
    setTranscript(id, [...transcriptFor(id), message])
  }

  function updateLastAssistant(
    id: string,
    update: (draft: ChatMessage) => void,
  ): void {
    const msgs = transcriptFor(id)
    const last = msgs[msgs.length - 1]
    if (last?.role !== "assistant") return
    const draft = { ...last, parts: last.parts ? [...last.parts] : [] }
    update(draft)
    setTranscript(id, [...msgs.slice(0, -1), draft])
  }

  function appendErrorMessage(id: string, message: string): void {
    appendMessage(id, { id: chatGenerateId(), role: "error", content: message })
  }

  function updateRuntime(
    id: string,
    patch: Partial<SubagentRuntimeState>,
  ): void {
    runtime.update((map) => {
      const next = new Map(map)
      const prev = next.get(id) ?? {
        showActivityIndicator: false,
        retry: null,
      }
      next.set(id, { ...prev, ...patch })
      return next
    })
  }

  function clearRuntime(id: string): void {
    runtime.update((map) => {
      if (!map.has(id)) return map
      const next = new Map(map)
      next.delete(id)
      return next
    })
  }

  // --- Children list ----------------------------------------------------------

  function updateChildFromStatusEvent(event: SubagentStatusEvent): void {
    children.update((list) =>
      list.map((child) =>
        child.subagent_id === event.subagent_id
          ? {
              ...child,
              name: event.name ?? child.name,
              agent_type: event.agent_type ?? child.agent_type,
              status: (event.status ?? child.status) as SubAgentStatus,
              current_trace_id: event.trace_id ?? child.current_trace_id,
              report_available:
                event.report_available ?? child.report_available,
            }
          : child,
      ),
    )
  }

  // Drop observations/transcripts for children no longer in the list, and clear
  // the selection if the selected child disappeared (conversation switch).
  function pruneToChildren(list: SubAgentItem[]): void {
    const ids = new Set(list.map((c) => c.subagent_id))
    for (const [id, obs] of observations) {
      if (!ids.has(id)) {
        obs.abort.abort()
        observations.delete(id)
      }
    }
    transcripts.update((map) => {
      let changed = false
      const next = new Map(map)
      for (const id of next.keys()) {
        if (!ids.has(id)) {
          next.delete(id)
          changed = true
        }
      }
      return changed ? next : map
    })
    runtime.update((map) => {
      let changed = false
      const next = new Map(map)
      for (const id of next.keys()) {
        if (!ids.has(id)) {
          next.delete(id)
          changed = true
        }
      }
      return changed ? next : map
    })
    const selected = get(selectedId)
    if (selected && !ids.has(selected)) {
      selectedId.set(null)
    }
  }

  async function fetchChildren(parentTraceId: string): Promise<void> {
    const thisGeneration = ++syncGeneration
    let list: SubAgentItem[] = []
    try {
      const response = await fetch(
        `${SUBAGENTS_BASE_URL}?parent_trace_id=${encodeURIComponent(parentTraceId)}`,
      )
      if (response.ok) {
        const data = (await response.json()) as SubAgentItem[]
        if (Array.isArray(data)) list = data
      }
    } catch {
      // Local server unreachable — fall through to an empty list rather than
      // leaving another conversation's children showing.
    }
    // A newer sync (conversation switch) superseded this fetch; drop the result.
    if (thisGeneration !== syncGeneration) return
    children.set(list)
    pruneToChildren(list)
  }

  async function syncForConversation(
    parentTraceId: string | null,
  ): Promise<void> {
    if (parentTraceId === syncedTraceId) return
    syncedTraceId = parentTraceId
    if (!parentTraceId) {
      syncGeneration++
      children.set([])
      pruneToChildren([])
      return
    }
    await fetchChildren(parentTraceId)
  }

  // --- Status firehose ---------------------------------------------------------

  function handleFirehoseEvent(event: SubagentStatusEvent): void {
    if (event.type !== "kiln-subagent-status" || !event.subagent_id) return
    const known = get(children).some((c) => c.subagent_id === event.subagent_id)
    if (known) {
      updateChildFromStatusEvent(event)
      return
    }
    // Unknown child: we can't tell whether it belongs to this conversation from
    // the event alone, so re-fetch the list for the current parent (cheap).
    if (syncedTraceId) {
      void fetchChildren(syncedTraceId)
    }
  }

  function clearReconnect(): void {
    if (reconnectTimer !== null) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
  }

  function scheduleReconnect(): void {
    if (reconnectTimer !== null || !firehoseActive) return
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null
      if (firehoseActive) connectFirehose()
    }, RECONNECT_DELAY_MS)
  }

  function closeSource(): void {
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
  }

  function connectFirehose(): void {
    // Pure observer: opening or closing this stream never affects a run. A
    // dropped connection is recovered by reconnecting; the fresh snapshot
    // (one status event per known run) re-syncs the children.
    const EventSourceCtor = globalThis.EventSource
    if (!EventSourceCtor) return
    closeSource()
    clearReconnect()
    connection.set("connecting")

    const source = new EventSourceCtor(`${SUBAGENTS_BASE_URL}/events`)
    eventSource = source

    source.onopen = () => {
      if (eventSource !== source) return
      connection.set("open")
    }
    source.onmessage = (e: MessageEvent) => {
      if (eventSource !== source) return
      const data = typeof e.data === "string" ? e.data.trim() : ""
      if (!data) return
      let event: SubagentStatusEvent
      try {
        event = JSON.parse(data) as SubagentStatusEvent
      } catch {
        return
      }
      handleFirehoseEvent(event)
    }
    source.onerror = () => {
      // Only act on the active source (avoid racing a teardown / reconnect).
      if (eventSource !== source) return
      closeSource()
      connection.set("errored")
      scheduleReconnect()
    }
  }

  function connect(): void {
    if (firehoseActive) return
    firehoseActive = true
    connectFirehose()
  }

  function disconnect(): void {
    firehoseActive = false
    closeSource()
    clearReconnect()
    connection.set("idle")
  }

  // --- Per-child observation -----------------------------------------------

  function buildProcessor(
    id: string,
    obs: ChildObservation,
  ): StreamEventProcessor {
    return new StreamEventProcessor({
      onAssistantMessage: (update) => {
        // First assistant content of the replayed in-flight turn (or of a turn
        // following a user-message echo): render into a fresh assistant message
        // rather than overwriting the last hydrated one.
        const msgs = transcriptFor(id)
        if (
          obs.pendingFreshTurn ||
          msgs[msgs.length - 1]?.role !== "assistant"
        ) {
          obs.pendingFreshTurn = false
          appendMessage(id, {
            id: chatGenerateId(),
            role: "assistant",
            parts: [],
          })
        }
        updateLastAssistant(id, update)
      },
      onInlineError: (message) => appendErrorMessage(id, message),
      // Mirror the live rendering affordances the main transcript gets from the
      // session store, so the child transcript shows the same thinking-dots and
      // "retrying N/M…" states.
      onShowActivityIndicator: (show) =>
        updateRuntime(id, { showActivityIndicator: show }),
      onRetry: (attempt, max) => updateRuntime(id, { retry: { attempt, max } }),
      onRetryClear: () => updateRuntime(id, { retry: null }),
    })
  }

  // Control events on the per-run stream: status markers keep the children list
  // fresh even without the firehose; user-message echoes open a new turn.
  function handleObserverControlEvent(
    id: string,
    obs: ChildObservation,
    processor: StreamEventProcessor,
    event: StreamEvent,
  ): boolean {
    if (event.type === "kiln-subagent-status") {
      const statusEvent = event as SubagentStatusEvent
      if (statusEvent.subagent_id) updateChildFromStatusEvent(statusEvent)
      return true
    }
    if (event.type === "user-message") {
      // The run echoed an injected user message (the kickoff briefing at run
      // start, or a steer from the overseeing user). Dedupe by echo id — a
      // buffer replay on re-attach re-emits the echo for a message the
      // transcript already shows.
      const echoId = event.id
      if (echoId && transcriptFor(id).some((m) => m.echoId === echoId)) {
        return true
      }
      // Kickoff echo ("kickoff-<id>") replayed after hydration already seeded
      // the briefing: the hydrated message carries no echoId, so dedupe
      // structurally — a kickoff can only ever be the first message, so skip it
      // whenever a user message already opens the transcript.
      if (echoId === `kickoff-${id}` && transcriptFor(id)[0]?.role === "user") {
        return true
      }
      // A buffer-replayed echo may carry the steer framing (<system-reminder>)
      // the runner adds before sending upstream; strip it for display the same
      // way hydration does, so the bubble shows what the user actually typed.
      appendMessage(id, {
        id: chatGenerateId(),
        role: "user",
        content: stripInternalFraming(event.content ?? ""),
        echoId,
      })
      // The next assistant content belongs to a fresh turn; reset the processor
      // so the prior turn's accumulated parts aren't re-flushed into it.
      obs.pendingFreshTurn = true
      processor.reset()
      return true
    }
    return false
  }

  async function observe(subagentId: string): Promise<void> {
    if (observations.has(subagentId)) return
    const child = get(children).find((c) => c.subagent_id === subagentId)
    if (!child) return
    const abort = new AbortController()
    const obs: ChildObservation = { abort, pendingFreshTurn: true }
    observations.set(subagentId, obs)

    // 1. Hydrate the child's persisted history (its session snapshot). Best
    // effort: a failure still attaches the live tail on an empty transcript.
    let messages: ChatMessage[] = []
    if (child.current_trace_id) {
      try {
        const response = await fetch(
          `${base_url}/api/chat/sessions/${encodeURIComponent(child.current_trace_id)}`,
          { signal: abort.signal },
        )
        if (response.ok) {
          const snapshot = (await response.json()) as ChatSessionSnapshot
          messages = hydrateSessionFromSnapshot(snapshot).messages
        }
      } catch {
        /* aborted or unreachable — live tail below still attaches */
      }
    }
    if (abort.signal.aborted) return
    setTranscript(subagentId, messages)

    // 2. Attach the live tail: buffer replay (current turn) + status marker +
    // live events. For terminal runs the stream ends after the marker.
    void observeEvents(subagentId, obs)
  }

  async function observeEvents(
    subagentId: string,
    obs: ChildObservation,
  ): Promise<void> {
    try {
      const response = await fetch(
        `${SUBAGENTS_BASE_URL}/${encodeURIComponent(subagentId)}/events`,
        { signal: obs.abort.signal },
      )
      if (!response.ok) return
      const reader = response.body?.getReader()
      if (!reader) return
      const processor = buildProcessor(subagentId, obs)
      await consumeSseStream(reader, processor, (event) =>
        handleObserverControlEvent(subagentId, obs, processor, event),
      )
    } catch {
      /* aborted or dropped — the transcript keeps what it has */
    } finally {
      // Allow a later select to re-observe (re-hydrate + re-attach) after the
      // stream ended — terminal run, network drop, or abort. The live-only
      // affordances (activity indicator, retry) die with the stream.
      if (observations.get(subagentId) === obs) {
        observations.delete(subagentId)
        clearRuntime(subagentId)
      }
    }
  }

  // --- Actions ----------------------------------------------------------------

  function select(subagentId: string | null): void {
    selectedId.set(subagentId)
    if (subagentId) void observe(subagentId)
  }

  async function stop(subagentId: string): Promise<void> {
    // Idempotent server-side; the authoritative status change arrives as a
    // kiln-subagent-status event (firehose and observer stream).
    try {
      await fetch(
        `${SUBAGENTS_BASE_URL}/${encodeURIComponent(subagentId)}/stop`,
        { method: "POST" },
      )
    } catch {
      /* the run keeps going and the user can retry */
    }
  }

  async function sendMessage(
    subagentId: string,
    content: string,
  ): Promise<{ ok: boolean; error?: string }> {
    let response: Response
    try {
      response = await fetch(
        `${SUBAGENTS_BASE_URL}/${encodeURIComponent(subagentId)}/message`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content }),
        },
      )
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      appendErrorMessage(subagentId, `Couldn't send the message: ${message}`)
      return { ok: false, error: message }
    }
    if (response.status === 409) {
      // The run reached a terminal state since the UI last heard; refresh the
      // list so the tab reflects it, and surface a friendly inline error.
      const message =
        "This sub-agent has already finished, so it can't receive messages."
      appendErrorMessage(subagentId, message)
      if (syncedTraceId) void fetchChildren(syncedTraceId)
      return { ok: false, error: message }
    }
    if (!response.ok) {
      let message = `Couldn't send the message (${response.status}).`
      try {
        const parsed = (await response.json()) as { detail?: string }
        if (parsed?.detail) message = parsed.detail
      } catch {
        /* keep default */
      }
      appendErrorMessage(subagentId, message)
      return { ok: false, error: message }
    }
    // No optimistic append: the run echoes the message on the observer stream
    // (user-message), which is what the transcript renders.
    return { ok: true }
  }

  function reset(): void {
    for (const obs of observations.values()) {
      obs.abort.abort()
    }
    observations.clear()
    syncGeneration++
    syncedTraceId = undefined
    children.set([])
    selectedId.set(null)
    transcripts.set(new Map())
    runtime.set(new Map())
  }

  return {
    children: { subscribe: children.subscribe },
    selectedId: { subscribe: selectedId.subscribe },
    transcripts: { subscribe: transcripts.subscribe },
    runtime: { subscribe: runtime.subscribe },
    connection: { subscribe: connection.subscribe },
    connect,
    disconnect,
    syncForConversation,
    select,
    observe,
    stop,
    sendMessage,
    reset,
    _close: closeSource,
  }
}

export const subagent_store: SubagentStore = createSubagentStore()
