/**
 * The unified conversation store (architecture §7).
 *
 * One module for desktop-owned conversations, keyed by session id, speaking
 * the `/api/conversations` surface and the unified `conversation-state` event
 * vocabulary. Phase 2 folded in `subagent_store.ts` (the CHILDREN UI,
 * behavior preserved 1:1); phase 3 folded in `auto_run_store.ts` — the auto
 * conversation store below drives enable/decline/stop/inject/resolve against
 * the re-homed endpoints and maps `conversation-state` back onto the exact
 * UX states the old `auto-mode-on/off/idle/state` events drove (green dot,
 * "waiting for you", consent + stop dialogs) with zero visual change.
 *
 * The desktop server runs conversations in the background and exposes them as
 * pure-observer streams: observing, stopping observation, or reconnecting
 * never mutates a run. This store tracks the current conversation's children
 * (`syncForConversation` + a registry-level `conversation-state` firehose,
 * connection handling modeled on `jobs_store.ts`), and — per observed child —
 * maintains a read-only transcript by hydrating the child's persisted session
 * then feeding its live events SSE into the EXISTING `StreamEventProcessor`,
 * so a child transcript renders exactly like a main transcript.
 */

import { get, writable, type Readable } from "svelte/store"
import { base_url } from "$lib/api_client"
import type { components } from "$lib/api_schema"
import {
  StreamEventProcessor,
  autoModeConsentPayloadFromEvent,
  chatGenerateId,
  consumeSseStream,
  type AutoModeConsentRequiredPayload,
  type ChatMessage,
  type ContextUsage,
  type StreamEvent,
  type ToolCallsPendingItem,
} from "./streaming_chat"
import {
  hydrateSessionFromSnapshot,
  stripInternalFraming,
  type ChatSessionSnapshot,
} from "./session_messages"

export type ConversationItem = components["schemas"]["ConversationItem"]
export type RunState = components["schemas"]["RunState"]
export type CreateAutoConversationRequest =
  components["schemas"]["CreateConversationRequest"]

/**
 * Per-conversation runtime affordances mirrored from the live stream so its
 * transcript renders with the SAME fidelity as the main one (thinking dots via
 * the activity indicator, "retrying N/M…" via the retry state). Runtime-only —
 * cleared when the observation ends.
 */
export interface ConversationRuntimeState {
  showActivityIndicator: boolean
  retry: { attempt: number; max: number } | null
}

const CONVERSATIONS_BASE_URL = `${base_url}/api/conversations`
const RECONNECT_DELAY_MS = 2000
// Low-frequency safety-net re-fetch of the children list while the firehose is
// connected and a parent is set (see `updateReconcileTimer`). WHY: the children
// strip is populated only when a child's firehose `conversation-state` event
// triggers a fetch, and a running child publishes that event exactly ONCE (at
// spawn) — nothing more until it settles. If that single event is missed (a
// firehose micro-drop, a server snapshot/subscribe race on (re)connect, or a
// fetch-race edge), a RUNNING child is absent from the strip with no further
// trigger until it COMPLETES (whose terminal tab is dropped by design) or the
// user refreshes. This periodic reconcile re-fetches the authoritative list
// (`children_of` always returns the complete current set) so any missed child
// converges within a few seconds instead of never. Cheap: localhost, and the
// server fix closes the snapshot gap so this rarely has anything to correct.
const RECONCILE_INTERVAL_MS = 3500

// Lifecycle of the state-firehose EventSource, surfaced for tests / debugging.
// A pure observer: this only reports the connection, it never mutates a run.
export type ConversationConnection = "idle" | "connecting" | "open" | "errored"

/**
 * `conversation-state` payload as it arrives on the firehose and on the
 * per-conversation observer stream (as the on-subscribe liveness marker).
 * Replaces the old `kiln-subagent-status` shape: `session_id` is the handle,
 * `state` uses the unified RunState strings, and trace ids are deliberately
 * absent (phase 5: the browser never sees trace ids anywhere — hydration is
 * keyed by session id and the desktop resolves the current leaf).
 */
interface ConversationStateEvent {
  type?: string
  session_id?: string
  kind?: string
  state?: string
  auto_flag?: boolean
  idle_reason?: string
  name?: string
  report_available?: boolean
}

// Terminal = the run can never advance again (one-shot kinds only). Same
// strings the old SubAgentStatus used, plus nothing: idle/awaiting_approval
// are live states (unreachable for phase-2 children, but the type covers
// every kind for phases 3-4).
const TERMINAL_STATES: ReadonlySet<string> = new Set([
  "completed",
  "failed",
  "stopped",
  "timeout",
])

export function isTerminalState(state: string): boolean {
  return TERMINAL_STATES.has(state)
}

/** Max individual child tabs before the strip collapses into a count chip. */
export const CHILD_TAB_OVERFLOW_LIMIT = 3

/**
 * Children whose tab is visible in the strip: live (non-terminal) ones, plus
 * the currently selected child even when terminal (so the view isn't yanked
 * while the user is reading it — selecting away drops the terminal tab).
 * Purely derived from state + selection (no tombstoning), so a child whose
 * state ever returns to live reappears automatically.
 */
export function visibleChildTabs(
  children: ConversationItem[],
  selectedId: string | null,
): ConversationItem[] {
  return children.filter(
    (c) => !isTerminalState(c.state) || c.session_id === selectedId,
  )
}

/**
 * Whether the strip should collapse individual child tabs into a single
 * "N agents running" chip (the selected child keeps its own tab beside it).
 */
export function shouldCollapseChildTabs(
  visibleChildren: ConversationItem[],
): boolean {
  return visibleChildren.length > CHILD_TAB_OVERFLOW_LIMIT
}

export interface ConversationStore {
  /** Children of the current conversation (server order). */
  children: Readable<ConversationItem[]>
  /** Selected tab: a child's session_id, or null for the main agent. */
  selectedId: Readable<string | null>
  /** Per-child read-only transcripts, keyed by session_id. */
  transcripts: Readable<Map<string, ChatMessage[]>>
  /** Per-child live rendering affordances (activity indicator, retry). */
  runtime: Readable<Map<string, ConversationRuntimeState>>
  connection: Readable<ConversationConnection>
  /** Open the registry-level state firehose (assistant page active). */
  connect(): void
  /** Close the firehose (navigation away). Observers are left alone. */
  disconnect(): void
  /**
   * Replace `children` with the sub-agents of the given parent conversation,
   * keyed by its SESSION id (phase 5: the browser's only parent handle —
   * chat.svelte binds this to `main_conversation_store.sessionId`; the old
   * leaf-trace-id handle and its server-side chain resolution are gone).
   * `null` (no conversation attached) clears the list. Deduped by value, so
   * it is safe to call reactively.
   */
  syncForConversation(parentId: string | null): Promise<void>
  /** Select a tab; selecting a child starts observing it. */
  select(sessionId: string | null): void
  /**
   * Observe one child: hydrate its persisted history, then attach the live
   * events tail (buffer replay + state marker + live). Idempotent while an
   * observation is active; a re-observe after the stream ended re-hydrates.
   */
  observe(sessionId: string): Promise<void>
  stop(sessionId: string): Promise<void>
  sendMessage(
    sessionId: string,
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

export function createConversationStore(): ConversationStore {
  const children = writable<ConversationItem[]>([])
  const selectedId = writable<string | null>(null)
  const transcripts = writable<Map<string, ChatMessage[]>>(new Map())
  const runtime = writable<Map<string, ConversationRuntimeState>>(new Map())
  const connection = writable<ConversationConnection>("idle")

  // The parent handle the current children list was fetched for (undefined =
  // never synced). Dedupes reactive syncForConversation calls and keys the
  // firehose "unknown child → re-fetch" rule.
  let syncedParentId: string | null | undefined = undefined
  let syncGeneration = 0

  let eventSource: EventSource | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  // Periodic children reconcile (see RECONCILE_INTERVAL_MS): runs only while
  // the firehose is active AND a parent is set; null when stopped.
  let reconcileTimer: ReturnType<typeof setInterval> | null = null
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
    patch: Partial<ConversationRuntimeState>,
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

  function updateChildFromStateEvent(event: ConversationStateEvent): void {
    // conversation-state events carry no trace id (unlike the old status
    // events) — and since phase 5 hydration doesn't either: it fetches by
    // session id and the desktop resolves the fresh leaf per request.
    children.update((list) =>
      list.map((child) =>
        child.session_id === event.session_id
          ? {
              ...child,
              name: event.name ?? child.name,
              state: (event.state ?? child.state) as RunState,
              report_available:
                event.report_available ?? child.report_available,
            }
          : child,
      ),
    )
  }

  // Drop observations/transcripts for children no longer in the list, and clear
  // the selection if the selected child disappeared (conversation switch).
  function pruneToChildren(list: ConversationItem[]): void {
    const ids = new Set(list.map((c) => c.session_id))
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

  async function fetchChildren(parentId: string): Promise<void> {
    const thisGeneration = ++syncGeneration
    let list: ConversationItem[] = []
    try {
      const response = await fetch(
        `${CONVERSATIONS_BASE_URL}?parent=${encodeURIComponent(parentId)}`,
      )
      if (response.ok) {
        const data = (await response.json()) as ConversationItem[]
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

  async function syncForConversation(parentId: string | null): Promise<void> {
    if (parentId === syncedParentId) return
    syncedParentId = parentId
    // The parent changed: (re)evaluate whether the reconcile timer should run
    // (it only runs with a non-null parent). Do this before the fetch so a
    // switch to null stops reconciling immediately.
    updateReconcileTimer()
    if (!parentId) {
      syncGeneration++
      children.set([])
      pruneToChildren([])
      return
    }
    await fetchChildren(parentId)
  }

  // --- State firehose ---------------------------------------------------------

  function handleFirehoseEvent(event: ConversationStateEvent): void {
    if (event.type !== "conversation-state" || !event.session_id) return
    // Phase 2: only sub-agent records exist on the server registry, but guard
    // by kind anyway so phase 3-4 parent records never leak into the children
    // strip once they share the firehose.
    if (event.kind && event.kind !== "subagent") return
    const known = get(children).some((c) => c.session_id === event.session_id)
    if (known) {
      updateChildFromStateEvent(event)
      return
    }
    // Unknown child: we can't tell whether it belongs to this conversation from
    // the event alone, so re-fetch the list for the current parent (cheap).
    if (syncedParentId) {
      void fetchChildren(syncedParentId)
    }
  }

  function clearReconnect(): void {
    if (reconnectTimer !== null) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
  }

  // Start/stop the periodic children reconcile to match the current lifecycle:
  // it runs iff the firehose is active AND a parent is set (a missed running
  // child can only exist under those two conditions). Idempotent, so it is
  // safe to call from every place those inputs change (connect / disconnect /
  // syncForConversation / reset). Each tick re-fetches the authoritative list;
  // fetchChildren's generation guard drops a tick that races a real
  // conversation switch, and same-parent ticks all hit the identical
  // children_of endpoint so the last one applied is always correct.
  function updateReconcileTimer(): void {
    const shouldRun = firehoseActive && !!syncedParentId
    if (shouldRun && reconcileTimer === null) {
      reconcileTimer = setInterval(() => {
        // Re-check inside the tick: firehoseActive/syncedParentId may have
        // flipped between scheduling and firing.
        if (firehoseActive && syncedParentId) {
          void fetchChildren(syncedParentId)
        }
      }, RECONCILE_INTERVAL_MS)
    } else if (!shouldRun && reconcileTimer !== null) {
      clearInterval(reconcileTimer)
      reconcileTimer = null
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
    // (one state event per known conversation) re-syncs the children.
    const EventSourceCtor = globalThis.EventSource
    if (!EventSourceCtor) return
    closeSource()
    clearReconnect()
    connection.set("connecting")

    const source = new EventSourceCtor(`${CONVERSATIONS_BASE_URL}/events`)
    eventSource = source

    source.onopen = () => {
      if (eventSource !== source) return
      connection.set("open")
    }
    source.onmessage = (e: MessageEvent) => {
      if (eventSource !== source) return
      const data = typeof e.data === "string" ? e.data.trim() : ""
      if (!data) return
      let event: ConversationStateEvent
      try {
        event = JSON.parse(data) as ConversationStateEvent
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
    // A parent may already be set (syncForConversation runs before connect on
    // the assistant page); start reconciling if so.
    updateReconcileTimer()
  }

  function disconnect(): void {
    firehoseActive = false
    closeSource()
    clearReconnect()
    updateReconcileTimer()
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

  // Control events on the per-conversation stream: state markers keep the
  // children list fresh even without the firehose; user-message echoes open a
  // new turn.
  function handleObserverControlEvent(
    id: string,
    obs: ChildObservation,
    processor: StreamEventProcessor,
    event: StreamEvent,
  ): boolean {
    if (event.type === "conversation-state") {
      const stateEvent = event as ConversationStateEvent
      if (stateEvent.session_id) updateChildFromStateEvent(stateEvent)
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
      // Kickoff echo ("kickoff-<session_id>") replayed after hydration already
      // seeded the briefing: the hydrated message carries no echoId, so dedupe
      // structurally — a kickoff can only ever be the first message, so skip it
      // whenever a user message already opens the transcript.
      if (echoId === `kickoff-${id}` && transcriptFor(id)[0]?.role === "user") {
        return true
      }
      // A buffer-replayed echo may carry the steer framing (<system-reminder>)
      // the engine adds before sending upstream; strip it for display the same
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

  async function observe(sessionId: string): Promise<void> {
    if (observations.has(sessionId)) return
    const child = get(children).find((c) => c.session_id === sessionId)
    if (!child) return
    const abort = new AbortController()
    const obs: ChildObservation = { abort, pendingFreshTurn: true }
    observations.set(sessionId, obs)

    // 1. Hydrate the child's persisted history by SESSION id (phase 5): the
    // desktop resolves the record's CURRENT leaf per request, so hydration
    // is always fresh — this replaces the deleted current_trace_id field
    // AND the pre-hydration item re-fetch that kept it fresh. Best effort:
    // a failure (including 404 for a child with nothing persisted yet)
    // still attaches the live tail on an empty transcript.
    let messages: ChatMessage[] = []
    try {
      const response = await fetch(
        `${base_url}/api/chat/sessions/${encodeURIComponent(sessionId)}`,
        { signal: abort.signal },
      )
      if (response.ok) {
        const snapshot = (await response.json()) as ChatSessionSnapshot
        messages = hydrateSessionFromSnapshot(snapshot).messages
      }
    } catch {
      /* aborted or unreachable — live tail below still attaches */
    }
    if (abort.signal.aborted) return
    setTranscript(sessionId, messages)

    // 2. Attach the live tail: buffer replay (current turn) + state marker +
    // live events. For terminal runs the stream ends after the marker.
    void observeEvents(sessionId, obs)
  }

  async function observeEvents(
    sessionId: string,
    obs: ChildObservation,
  ): Promise<void> {
    try {
      const response = await fetch(
        `${CONVERSATIONS_BASE_URL}/${encodeURIComponent(sessionId)}/events`,
        { signal: obs.abort.signal },
      )
      if (!response.ok) return
      const reader = response.body?.getReader()
      if (!reader) return
      const processor = buildProcessor(sessionId, obs)
      await consumeSseStream(reader, processor, (event) =>
        handleObserverControlEvent(sessionId, obs, processor, event),
      )
    } catch {
      /* aborted or dropped — the transcript keeps what it has */
    } finally {
      // Allow a later select to re-observe (re-hydrate + re-attach) after the
      // stream ended — terminal run, network drop, or abort. The live-only
      // affordances (activity indicator, retry) die with the stream.
      if (observations.get(sessionId) === obs) {
        observations.delete(sessionId)
        clearRuntime(sessionId)
      }
    }
  }

  // --- Actions ----------------------------------------------------------------

  function select(sessionId: string | null): void {
    selectedId.set(sessionId)
    if (sessionId) void observe(sessionId)
  }

  async function stop(sessionId: string): Promise<void> {
    // Idempotent server-side; the authoritative state change arrives as a
    // conversation-state event (firehose and observer stream).
    try {
      await fetch(
        `${CONVERSATIONS_BASE_URL}/${encodeURIComponent(sessionId)}/stop`,
        { method: "POST" },
      )
    } catch {
      /* the run keeps going and the user can retry */
    }
  }

  async function sendMessage(
    sessionId: string,
    content: string,
  ): Promise<{ ok: boolean; error?: string }> {
    let response: Response
    try {
      response = await fetch(
        `${CONVERSATIONS_BASE_URL}/${encodeURIComponent(sessionId)}/messages`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content }),
        },
      )
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      appendErrorMessage(sessionId, `Couldn't send the message: ${message}`)
      return { ok: false, error: message }
    }
    if (response.status === 409) {
      // The run reached a terminal state since the UI last heard; refresh the
      // list so the tab reflects it, and surface a friendly inline error.
      const message =
        "This sub-agent has already finished, so it can't receive messages."
      appendErrorMessage(sessionId, message)
      if (syncedParentId) void fetchChildren(syncedParentId)
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
      appendErrorMessage(sessionId, message)
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
    syncedParentId = undefined
    // No parent anymore: stop the reconcile timer (the firehose connection
    // itself is intentionally kept — reset() is a new-chat clear, not a
    // navigation-away).
    updateReconcileTimer()
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

export const conversation_store: ConversationStore = createConversationStore()

// ─────────────────────────────────────────────────────────────────────────────
// Main conversation store — the phase-4 generalization of the phase-3 auto
// conversation store (itself the fold-in of the deleted `auto_run_store.ts`).
// The MAIN conversation is now "just another observed conversation"
// (architecture §7): ONE pure-observer attachment to the conversation's
// events stream feeds the EXISTING `StreamEventProcessor`, for BOTH kinds —
// a plain interactive conversation and an auto conversation are the same
// record whose policy/kind flip on enable/disable. This store owns:
//
// - create-or-adopt (`ensure`, replacing the old per-request POST /api/chat
//   conversation model) + attach/detach of the observer,
// - the auto-mode lifecycle (enable / decline / stop / arm) with the exact
//   UX states the old `auto-mode-on/off/idle/state` events drove (green dot,
//   "waiting for you", consent + stop dialogs) — zero visual change,
// - sends (`POST /{sid}/messages`, returning the echo-dedupe message id),
// - approvals (`fetchApprovals` + `decide` — the old two-request
//   stream-ends-at-pending + /execute-tools flow became a parked batch).
//
// Connection handling mirrors `jobs_store.ts`: opening or closing the stream
// never mutates the run; the authoritative lifecycle state comes from the
// unified `conversation-state` events, mapped below so it is correct on
// first paint after a re-attach (not just after a local action).
// ─────────────────────────────────────────────────────────────────────────────

// Lifecycle of the per-conversation events EventSource, surfaced for tests /
// debugging. A pure observer: this only reports the connection, it never
// mutates the run.
export type MainConnection = "idle" | "connecting" | "open" | "closed"

/** The parked approval batch as the browser consumes it (GET /approvals). */
export interface PendingApprovalsView {
  batchId: string
  items: ToolCallsPendingItem[]
}

export interface DeclineAutoModeContext {
  enable_tool_call_id: string
  siblings: ToolCallsPendingItem[]
}

/**
 * Callbacks the chat session store registers so the desktop-owned
 * conversation drives the transcript. Mirrors the hooks the old streamChat
 * called, plus turn lifecycle and the auto on/off signals — the sink
 * contract is what guarantees zero visual change across the transport swap.
 */
export interface MainConversationSink {
  /** Begin a fresh assistant turn (append an empty assistant message). */
  beginAssistantTurn: () => void
  onAssistantMessage: (update: (draft: ChatMessage) => void) => void
  /**
   * A turn's snapshot persisted upstream (the `kiln_chat_trace` event).
   * Phase 5: deliberately carries NO trace id — the browser never keys on
   * one (functional spec §4); the session store uses this purely as the
   * moment to learn the conversation's durable `root_id` (one item fetch)
   * for its restart-recovery key, replacing the old persisted-leaf update.
   */
  onTurnPersisted: () => void
  /** Fired when a snapshot event carries ``context_usage`` (the gauge). */
  onContextUsage: (usage: ContextUsage) => void
  /** ``kiln_compaction_status``: true shows the "summarizing…" indicator. */
  onCompactionStatus: (compacting: boolean) => void
  onInlineError: (message: string, traceId?: string, code?: string) => void
  onToolExecutionStart: (toolCount: number) => void
  onToolExecutionEnd: (toolCount: number) => void
  onShowActivityIndicator: (show: boolean) => void
  /**
   * A turn/burst is live (RUNNING) — drives the SAME loading affordances
   * (thinking dots, animated icon) for interactive turns and auto bursts.
   * ``false`` on settle.
   */
  onWorkingChange: (working: boolean) => void
  /**
   * The run echoed a user message (an own send, a second tab's send, or an
   * injected sub-agent report); ``echoId`` lets the sink dedupe its own
   * just-sent message and buffer replays.
   */
  onUserMessage: (content: string, echoId?: string) => void
  /**
   * A burst ended but auto mode stays ON (asked_user / done / error /
   * max_rounds / armed). The indicator persists; only working clears.
   */
  onAutoModeIdle: (reason: string | null) => void
  /** Auto mode turned OFF — fired on a true on→off TRANSITION only. */
  onAutoModeOff: (reason: string | null) => void
  /**
   * An INTERACTIVE turn settled (idle transition with the flag off). Fires
   * where the old streamChat called onFinish: status → ready, flush queued.
   * Deliberately carries NO reason: the engine records the auto idle
   * vocabulary on interactive records too, and the phase-1 rendering rule
   * says interactive conversations must never render `idle_reason` (see
   * ConversationEngine._finish_idle).
   */
  onInteractiveIdle: () => void
  /**
   * BUG 2 fix — the idle ATTACH MARKER of a genuinely-idle, flag-off
   * conversation. Distinct from ``onInteractiveIdle`` (a real settle): the
   * refresh-brick fix deliberately keeps markers settle-SILENT (a marker is
   * not a settle), but the LIVE idle ``conversation-state`` event that would
   * fire ``onInteractiveIdle`` is published live-only and can be MISSED when
   * the observer is momentarily detached/reconnecting at the instant the turn
   * settles. On (re)subscribe the bus delivers an idle marker instead — and a
   * CLIENT-HELD queued message would then wait forever for a settle hook that
   * never comes. So this hook does a queued-message FLUSH ONLY (no other
   * settle semantics): the session store wires it to ``maybeFlush``, which is
   * a safe no-op without a queue or while a turn is active. Optional so other
   * sink consumers need not implement it.
   */
  onIdleMarker?: () => void
  /**
   * The run parked on a pending approval batch (state awaiting_approval —
   * marker or live). The session store fetches the batch and opens the SAME
   * approval box the old stream-ending tool-calls-pending event drove.
   */
  onAwaitingApproval: () => void
  /**
   * ``tool-calls-pending`` on the observer stream — the pending batch's wire
   * payload (also replayed to re-attaching tabs while parked). Same entry as
   * onAwaitingApproval (both funnel into the idempotent approvals fetch).
   */
  onToolCallsPending: (items: ToolCallsPendingItem[]) => void
  /**
   * ``auto-mode-consent-required`` on the observer stream (the engine ends
   * the turn after emitting it): drive the consent dialog exactly as the old
   * stream-ending event did.
   */
  onConsentRequired: (payload: AutoModeConsentRequiredPayload) => void
  /** ``kiln_client_upgrade_nudge`` — the non-blocking upgrade banner. */
  onVersionNudge: (preferredVersion: string) => void
}

export interface MainConversationStore {
  /** Conversation auto-mode flag: ON across RUNNING and IDLE bursts. */
  autoModeOn: Readable<boolean>
  /**
   * Client-only "armed" flag (Revision R2): auto mode turned on for a
   * brand-new conversation with no trace yet — indicator on, NO server call;
   * the first send creates the conversation in auto mode.
   */
  armed: Readable<boolean>
  /** A turn/burst is actively running (either kind). */
  working: Readable<boolean>
  /** Transient "reconnecting…" window during a re-attach. */
  reconnecting: Readable<boolean>
  /** Transient "retrying N/M…" affordance. */
  retry: Readable<{ attempt: number; max: number } | null>
  /** The main conversation's session id (null before ensure/attach). */
  sessionId: Readable<string | null>
  offReason: Readable<string | null>
  connection: Readable<MainConnection>
  bind(sink: MainConversationSink): void
  /**
   * Create-or-adopt the conversation for the given conversation KEY — a
   * session id, a history row id (live sid / durable root id / legacy
   * leaf), or null for a brand-new conversation — and attach the observer.
   * The desktop resolves the key (phase 5: the browser never holds trace
   * ids; the old trace-keyed ensure died with them). Idempotent while
   * attached. Replaces the old conversation-per-request POST /api/chat
   * model.
   */
  ensure(
    sessionKey: string | null,
    opts?: {
      openInflightTurn?: boolean
      initialWorking?: boolean
      /** Reflect the auto indicator immediately (history auto-row restore —
       * the marker would set it anyway, but the old attach was instant). */
      assumeAutoOn?: boolean
    },
  ): Promise<{ ok: boolean; sessionId?: string; error?: string }>
  requestEnable(
    seed: CreateAutoConversationRequest,
  ): Promise<{ ok: boolean; error?: string }>
  /**
   * Decline a pending enable_auto_mode consent request
   * (POST /{sid}/auto {enabled:false, decline}): the declined continuation
   * streams on the observer into a fresh assistant turn.
   */
  decline(ctx: DeclineAutoModeContext): Promise<void>
  /**
   * Send a user message (POST /{sid}/messages): IDLE starts the turn/burst,
   * RUNNING queues into the server inbox, AWAITING_APPROVAL queues until
   * decisions resolve. Returns the server-minted message id so the sender
   * can dedupe its own echo.
   */
  sendMessage(
    text: string,
  ): Promise<{ ok: boolean; error?: string; messageId?: string }>
  stop(): Promise<void>
  /** Fetch the parked approval batch (404 → null). */
  fetchApprovals(): Promise<PendingApprovalsView | null>
  /**
   * Resolve the parked batch. ``conflict`` = another tab decided first
   * (409) — the box should clear and the stream carries the resolution.
   */
  decide(
    batchId: string,
    decisions: Record<string, boolean>,
  ): Promise<{ ok: boolean; conflict?: boolean; error?: string }>
  /** Mark the start of a re-attach so the transcript shows "reconnecting…". */
  beginReconnect(): void
  /**
   * Open the conversation's events SSE. ``initialWorking`` drives the
   * thinking indicator immediately; ``openInflightTurn`` renders a replayed
   * in-flight round into a fresh assistant turn; ``assumeAutoOn`` turns the
   * auto indicator on optimistically (enable / auto-row restore) instead of
   * waiting for the marker.
   */
  attach(
    sessionId: string,
    initialWorking?: boolean,
    openInflightTurn?: boolean,
    assumeAutoOn?: boolean,
  ): void
  /** Stop observing + clear the indicator without ending the run. */
  detach(): void
  /**
   * Open a fresh assistant turn AND reset the stream processor so the prior
   * turn's parts aren't re-flushed into it. Used before dispatching an
   * action whose reply streams on the already-open observer (send / enable
   * burst / decline).
   */
  beginTurn(): void
  /** Client-arm auto mode on a brand-new conversation (Revision R2). */
  arm(): void
  disarm(): void
  /** Exposed for tests / explicit teardown; not part of normal usage. */
  _close(): void
}

export function createMainConversationStore(): MainConversationStore {
  const autoModeOn = writable<boolean>(false)
  const armed = writable<boolean>(false)
  const working = writable<boolean>(false)
  const reconnecting = writable<boolean>(false)
  const sessionId = writable<string | null>(null)
  const offReason = writable<string | null>(null)
  const connection = writable<MainConnection>("idle")
  // Transient "retrying N/M…" affordance: set on each kiln-chat-retry event,
  // cleared by the next event of any other kind.
  const retry = writable<{ attempt: number; max: number } | null>(null)

  function setWorking(next: boolean): void {
    working.set(next)
    sink?.onWorkingChange(next)
  }

  let sink: MainConversationSink | null = null
  let eventSource: EventSource | null = null
  // The live stream's processor, held store-level so beginTurn() can reset
  // it (a fresh assistant turn must not have the prior turn's accumulated
  // parts re-flushed into it — the same rule the user-message echo path
  // applies).
  let processor: StreamEventProcessor | null = null
  // True from attach() until the FIRST conversation-state event arrives on
  // the new stream: that event is the bus's ON-SUBSCRIBE marker (a snapshot
  // of where the run already is, following the buffer replay) — NOT a
  // transition. The marker updates affordances (flag, working, approval box)
  // but must never fire the SETTLE hooks (onAutoModeIdle /
  // onInteractiveIdle, which flush queued messages) — a re-attach to an idle
  // conversation is not a settle (the old auto-mode-state marker's silence).
  let attachMarkerPending = false
  // On a re-attach the buffer replay carries ONLY the current in-flight
  // round; without opening a fresh turn its first flush would overwrite the
  // last hydrated bubble. Lazy so an idle re-attach leaves no empty bubble.
  let pendingInflightTurn = false
  // Whether the flag has been observed ON on this attachment — an off state
  // event is only a TRANSITION (→ onAutoModeOff) when it was.
  let flagSeenOn = false
  // Serializes ensure() so two racing callers can't both create.
  let ensureInFlight: Promise<{
    ok: boolean
    sessionId?: string
    error?: string
  }> | null = null

  function consumeInflightTurn(): void {
    if (pendingInflightTurn) {
      pendingInflightTurn = false
      sink?.beginAssistantTurn()
    }
  }

  function bind(newSink: MainConversationSink): void {
    sink = newSink
  }

  function buildProcessor(): StreamEventProcessor {
    return new StreamEventProcessor({
      onAssistantMessage: (update) => {
        // First assistant content of a re-attached in-flight round: open a
        // fresh turn so it renders into its own bubble.
        consumeInflightTurn()
        sink?.onAssistantMessage(update)
      },
      // The processor's kiln_chat_trace hook still receives the upstream
      // event's trace id (backend vocabulary — the event keeps carrying the
      // rotating leaf id even after phase 6's session-id continuation) but
      // it is DROPPED at this boundary — the sink only learns "a turn
      // persisted" (functional spec §4: browser code never sees trace_id).
      onChatTrace: () => sink?.onTurnPersisted(),
      onContextUsage: (usage) => sink?.onContextUsage(usage),
      onCompactionStatus: (compacting) => sink?.onCompactionStatus(compacting),
      onInlineError: (message, traceId, code) =>
        sink?.onInlineError(message, traceId, code),
      onVersionNudge: (preferred) => sink?.onVersionNudge(preferred),
      onToolExecutionStart: (count) => sink?.onToolExecutionStart(count),
      onToolExecutionEnd: (count) => sink?.onToolExecutionEnd(count),
      onShowActivityIndicator: (show) => sink?.onShowActivityIndicator(show),
    })
  }

  function beginTurn(): void {
    sink?.beginAssistantTurn()
    processor?.reset()
    // The fresh turn supersedes any pending inflight-turn bookkeeping.
    pendingInflightTurn = false
  }

  function closeSource(): void {
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
    processor = null
    // A pending fresh-turn / attach marker belongs to the stream being torn
    // down.
    pendingInflightTurn = false
    attachMarkerPending = false
  }

  // The on→off TRANSITION (stop / disable / model-called disable): clear the
  // auto affordances and signal the sink ONCE. Unlike the old auto store's
  // clearToOff this NEVER closes the stream or clears the session id — an
  // off-auto conversation IS the same live interactive conversation
  // (phase 4's policy flip), and the observer keeps carrying its turns.
  function applyOffTransition(reason: string | null): void {
    flagSeenOn = false
    autoModeOn.set(false)
    armed.set(false)
    setWorking(false)
    reconnecting.set(false)
    retry.set(null)
    offReason.set(reason)
    sink?.onAutoModeOff(reason)
  }

  // Client-arm on a brand-new conversation (Revision R2): indicator on, no
  // server call. The first sendMessage creates the conversation.
  function arm(): void {
    armed.set(true)
  }

  function disarm(): void {
    armed.set(false)
  }

  // Stop observing the current conversation and clear all affordances
  // WITHOUT signalling the sink (the run keeps going server-side; the user
  // navigated away — New Chat / load another conversation).
  function detach(): void {
    closeSource()
    flagSeenOn = false
    autoModeOn.set(false)
    armed.set(false)
    setWorking(false)
    reconnecting.set(false)
    retry.set(null)
    sessionId.set(null)
    offReason.set(null)
    connection.set("idle")
  }

  function beginReconnect(): void {
    reconnecting.set(true)
  }

  // --- Control-event handling on the observer stream --------------------------
  // Returns true when it claims the event (so it isn't forwarded to the
  // processor). The lifecycle vocabulary is the ONE `conversation-state`
  // event; the old per-kind mapping is preserved exactly:
  //
  //   old auto-mode-on            → state=running, auto_flag=true
  //   old auto-mode-idle{reason}  → state=idle,    auto_flag=true, idle_reason
  //   old auto-mode-off{reason}   → auto_flag false TRANSITION (idle_reason
  //                                 carries user_stopped/user_disabled)
  //   old auto-mode-state{working}→ the on-subscribe marker: working ⇔ running
  //   old interactive stream end  → state=idle, auto_flag=false (transition)
  //                                 → onInteractiveIdle (status ready + flush)
  //   old stream-ends-at-pending  → state=awaiting_approval + the replayed
  //                                 tool-calls-pending event → approvals fetch
  //   old stream-ends-at-consent  → auto-mode-consent-required on the stream
  function handleControlEvent(event: StreamEvent): boolean {
    if (event.type === "conversation-state") {
      // Ignore other kinds defensively (the per-conversation stream carries
      // only this conversation's events; sub-agent records are never the
      // main conversation).
      if (event.kind && event.kind !== "auto" && event.kind !== "interactive")
        return true
      const isAttachMarker = attachMarkerPending
      attachMarkerPending = false
      // Any state event means the attach is established.
      reconnecting.set(false)
      if (event.session_id) sessionId.set(event.session_id)

      const flagOn = event.auto_flag === true
      // A true on→off TRANSITION (old auto-mode-off) — including one arriving
      // as the marker of a freshly re-attached OFF record (the old terminal
      // off marker likewise drove the off handler).
      const offTransition = !flagOn && flagSeenOn
      if (offTransition) {
        applyOffTransition(event.idle_reason ?? null)
      } else if (!flagOn) {
        autoModeOn.set(false)
      } else {
        flagSeenOn = true
        autoModeOn.set(true)
        offReason.set(null)
      }

      if (event.state === "running") {
        // old auto-mode-on / state{working:true}; for interactive kind this
        // is a turn in flight (the old client stream being live).
        setWorking(true)
      } else if (event.state === "awaiting_approval") {
        // The run parked on approvals. The thinking affordance stops (the
        // old stream ENDED here); the approval box re-surfaces via the
        // sink's idempotent approvals fetch — marker included, so a
        // refreshed tab recovers the box (functional spec §5).
        setWorking(false)
        pendingInflightTurn = false
        sink?.onAwaitingApproval()
      } else {
        // idle
        setWorking(false)
        pendingInflightTurn = false
        // Exactly ONE settle signal per settle: an off transition already
        // signalled onAutoModeOff above (the old auto-mode-off event carried
        // both facts in one payload), markers signal nothing.
        if (!isAttachMarker && !offTransition) {
          if (flagOn) {
            // Burst settled, flag stays on (old auto-mode-idle) — flushes
            // queued messages in the session store.
            sink?.onAutoModeIdle(event.idle_reason ?? null)
          } else {
            // Interactive turn settled (the old streamChat onFinish moment).
            // idle_reason deliberately not forwarded (rendering rule).
            sink?.onInteractiveIdle()
          }
        } else if (isAttachMarker && !offTransition && !flagOn) {
          // BUG 2 fix: a genuinely-idle, flag-off conversation whose LIVE
          // idle event was missed (the observer was detached/reconnecting at
          // the settle instant) now arrives only as this on-subscribe marker.
          // The refresh-brick fix keeps the marker settle-silent above, so a
          // CLIENT-HELD queued message would strand. Fire the flush-only hook
          // to unstick it — WITHOUT the full settle semantics the brick fix
          // suppresses. Safe: onIdleMarker → maybeFlush no-ops without a queue
          // (e.g. the brick's echo-then-idle-marker sequence carries none) and
          // dispatchQueued clears before sending, so a real live idle racing
          // this marker can never double-send. Excludes flag-on (auto idle
          // markers) and off transitions (onAutoModeOff already cleared the
          // queue there).
          sink?.onIdleMarker?.()
        }
      }
      return true
    }
    if (event.type === "kiln-chat-retry") {
      // A transient upstream failure is being retried with backoff — the
      // turn/burst is still working; surface "retrying N/M…".
      setWorking(true)
      retry.set({
        attempt: event.attempt ?? 0,
        max: event.max_attempts ?? 0,
      })
      return true
    }
    if (event.type === "user-message") {
      // The run echoed a user message (enqueue-time echo). Render as a fresh
      // user turn followed by a new assistant turn — every observer
      // (including the sender, deduped by echo id) sees it, consistent with
      // replay.
      setWorking(true)
      pendingInflightTurn = false
      sink?.onUserMessage(event.content ?? "", event.id)
      return true
    }
    if (event.type === "tool-calls-pending") {
      // The run parked (or re-surfaced, via replay/rehydration) a pending
      // approval batch. The old stream ENDED here; now the box opens off the
      // fetched batch while the run stays parked.
      setWorking(false)
      sink?.onToolCallsPending(Array.isArray(event.items) ? event.items : [])
      return true
    }
    if (event.type === "auto-mode-consent-required") {
      // The model asked to enable auto mode; the engine emitted the consent
      // control event and ended the turn (an idle state event follows).
      setWorking(false)
      sink?.onConsentRequired(autoModeConsentPayloadFromEvent(event))
      return true
    }
    return false
  }

  function attach(
    newSessionId: string,
    initialWorking?: boolean,
    openInflightTurn = false,
    assumeAutoOn = false,
  ): void {
    const EventSourceCtor = globalThis.EventSource
    if (!EventSourceCtor) {
      reconnecting.set(false)
      return
    }
    closeSource()

    pendingInflightTurn = openInflightTurn
    attachMarkerPending = true
    flagSeenOn = assumeAutoOn

    sessionId.set(newSessionId)
    if (assumeAutoOn) {
      // Enable / auto-row restore: reflect the on-state immediately (the old
      // attach semantics); the marker corrects it if stale. Plain
      // interactive attaches wait for the marker instead.
      autoModeOn.set(true)
      offReason.set(null)
    }
    // Working: explicit when the caller knows (resync state); presumed live
    // only on the optimistic auto attach (History restore had no status —
    // the marker corrects it with no visible gap).
    setWorking(initialWorking ?? assumeAutoOn)
    connection.set("connecting")

    processor = buildProcessor()
    const activeProcessor = processor
    const source = new EventSourceCtor(
      `${CONVERSATIONS_BASE_URL}/${encodeURIComponent(newSessionId)}/events`,
    )
    eventSource = source

    source.onopen = () => {
      if (eventSource !== source) return
      connection.set("open")
      reconnecting.set(false)
    }

    source.onmessage = (e: MessageEvent) => {
      if (eventSource !== source) return
      // First byte over the stream also means we're established.
      reconnecting.set(false)
      const data = typeof e.data === "string" ? e.data.trim() : ""
      if (!data || data === "[DONE]") return
      let event: StreamEvent
      try {
        event = JSON.parse(data) as StreamEvent
      } catch {
        return
      }
      // Any event other than another retry means the retry window is over.
      if (event.type !== "kiln-chat-retry") retry.set(null)
      if (handleControlEvent(event)) {
        // A ``user-message`` echo opened a fresh assistant turn (the sink
        // calls beginAssistantTurn); reset the processor so the prior turn's
        // accumulated parts aren't re-flushed into it.
        if (event.type === "user-message") activeProcessor.reset()
        return
      }
      activeProcessor.handleEvent(event)
    }

    source.onerror = () => {
      if (eventSource !== source) return
      // No reconnect loop. The conversation is persisted server-side, so
      // degrade cleanly: an auto conversation falls to the hydrated-history
      // "off" look (the old behavior); an interactive one just marks the
      // connection closed — the session id survives, and the next
      // send/ensure re-attaches.
      const droppedMidTurn = get(working)
      closeSource()
      if (get(autoModeOn)) {
        applyOffTransition(null)
      } else {
        // setWorking(false) doubles as the session store's status reset (it
        // clears a stuck "submitted"/"streaming" without flushing the
        // queue), mirroring the old streamChat fetch-error path's return to
        // ready.
        setWorking(false)
        reconnecting.set(false)
        if (droppedMidTurn) {
          // A turn was visibly in flight when the observer died — surface
          // it like the old streamChat onError surfaced a dropped fetch
          // (an idle-observer drop stays silent, as no request was in
          // flight in the old world either).
          sink?.onInlineError(
            "Lost the connection to the assistant. Please try again.",
          )
        }
      }
      connection.set("closed")
    }
  }

  async function ensure(
    sessionKey: string | null,
    opts?: {
      openInflightTurn?: boolean
      initialWorking?: boolean
      assumeAutoOn?: boolean
    },
  ): Promise<{ ok: boolean; sessionId?: string; error?: string }> {
    // Already attached: the conversation exists and is observed.
    const current = get(sessionId)
    if (current && eventSource) return { ok: true, sessionId: current }
    if (ensureInFlight) return ensureInFlight

    const doEnsure = async () => {
      let response: Response
      try {
        response = await fetch(CONVERSATIONS_BASE_URL, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            kind: "interactive",
            ...(sessionKey ? { session_id: sessionKey } : {}),
          }),
        })
      } catch (err) {
        return {
          ok: false,
          error: err instanceof Error ? err.message : String(err),
        }
      }
      if (!response.ok) {
        return {
          ok: false,
          error: `Could not open the conversation (${response.status}).`,
        }
      }
      let data: { session_id?: string }
      try {
        data = (await response.json()) as { session_id?: string }
      } catch {
        return { ok: false, error: "Malformed response opening conversation." }
      }
      if (!data.session_id) {
        return { ok: false, error: "No conversation id returned." }
      }
      attach(
        data.session_id,
        opts?.initialWorking,
        opts?.openInflightTurn ?? false,
        opts?.assumeAutoOn ?? false,
      )
      return { ok: true, sessionId: data.session_id }
    }
    ensureInFlight = doEnsure()
    try {
      return await ensureInFlight
    } finally {
      ensureInFlight = null
    }
  }

  async function requestEnable(
    seed: CreateAutoConversationRequest,
  ): Promise<{ ok: boolean; error?: string }> {
    // POST /api/conversations — the re-homed enable (old /api/chat/auto/
    // enable): flips the SAME conversation record to the auto policy (or
    // creates one for the armed-first-send / legacy paths).
    // A burst starts immediately when the seed carries content to run: the
    // consent path (enable_tool_call_id) or the armed-first-send first
    // message (extra_messages).
    const startsBurst =
      !!seed.enable_tool_call_id ||
      (!!seed.pending_tool_calls && seed.pending_tool_calls.length > 0) ||
      (!!seed.extra_messages && seed.extra_messages.length > 0)
    const alreadyAttached = eventSource !== null && get(sessionId) !== null
    if (startsBurst && alreadyAttached) {
      // The burst will stream on the ALREADY-OPEN observer — open the fresh
      // assistant turn before the enable POST so no burst byte can race into
      // the previous bubble. (A failed enable leaves an empty, invisible
      // assistant message; the inline error follows it.)
      beginTurn()
    }
    let response: Response
    try {
      response = await fetch(CONVERSATIONS_BASE_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(seed),
      })
    } catch (err) {
      return {
        ok: false,
        error: err instanceof Error ? err.message : String(err),
      }
    }
    if (!response.ok) {
      let message = `Could not enable auto mode (${response.status}).`
      try {
        const parsed = (await response.json()) as { detail?: string }
        if (parsed?.detail) message = parsed.detail
      } catch {
        /* keep default */
      }
      return { ok: false, error: message }
    }
    let data: { session_id?: string }
    try {
      data = (await response.json()) as { session_id?: string }
    } catch {
      return { ok: false, error: "Malformed response from enable auto mode." }
    }
    if (!data.session_id) {
      return {
        ok: false,
        error: "Enable auto mode did not return a conversation id.",
      }
    }
    // A real desktop-owned conversation now owns the on-state; clear any
    // client-armed flag (Revision R2).
    armed.set(false)
    if (alreadyAttached && get(sessionId) === data.session_id) {
      // The flip happened on the conversation we already observe — reflect
      // the on-state without re-attaching (a re-attach would replay the
      // buffer into a transcript that already shows it).
      flagSeenOn = true
      autoModeOn.set(true)
      offReason.set(null)
      if (startsBurst) setWorking(true)
      return { ok: true }
    }
    if (startsBurst) {
      // Fresh attachment: the new stream renders the burst into a fresh
      // assistant turn.
      sink?.beginAssistantTurn()
    }
    attach(data.session_id, startsBurst, false, true)
    return { ok: true }
  }

  async function decline(ctx: DeclineAutoModeContext): Promise<void> {
    // Decline resolves enable→declined server-side (old
    // /api/chat/auto/decline, folded into POST /{sid}/auto) and streams the
    // interactive continuation on the observer — open a fresh turn for it.
    const id = get(sessionId)
    if (!id) {
      sink?.onInlineError("No conversation to decline auto mode for.")
      return
    }
    beginTurn()
    let response: Response
    try {
      response = await fetch(
        `${CONVERSATIONS_BASE_URL}/${encodeURIComponent(id)}/auto`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ enabled: false, decline: ctx }),
        },
      )
    } catch (err) {
      sink?.onInlineError(err instanceof Error ? err.message : String(err))
      return
    }
    if (!response.ok) {
      const text = await response.text()
      sink?.onInlineError(
        `Could not resume chat after declining auto mode (${response.status}): ${
          text || response.statusText
        }`,
      )
      return
    }
    // The declined continuation is a normal turn; reflect the in-flight
    // affordance until its idle event lands.
    setWorking(true)
  }

  async function sendMessage(
    text: string,
  ): Promise<{ ok: boolean; error?: string; messageId?: string }> {
    const id = get(sessionId)
    if (!id) {
      return {
        ok: false,
        error: "No active conversation to send the message to.",
      }
    }
    // Optimistically reflect that a turn/burst is (re)starting; the echoed
    // user-message + events confirm it (and a failed send clears it below).
    setWorking(true)
    let response: Response
    try {
      response = await fetch(
        `${CONVERSATIONS_BASE_URL}/${encodeURIComponent(id)}/messages`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: text }),
        },
      )
    } catch (err) {
      setWorking(false)
      return {
        ok: false,
        error: err instanceof Error ? err.message : String(err),
      }
    }
    if (!response.ok) {
      setWorking(false)
      let message = `Could not send the message (${response.status}).`
      try {
        const parsed = (await response.json()) as { detail?: string }
        if (parsed?.detail) message = parsed.detail
      } catch {
        /* keep default */
      }
      return { ok: false, error: message }
    }
    let messageId: string | undefined
    try {
      const parsed = (await response.json()) as { message_id?: string }
      if (typeof parsed?.message_id === "string") messageId = parsed.message_id
    } catch {
      /* the send succeeded; dedupe falls back to content matching */
    }
    return { ok: true, messageId }
  }

  async function fetchApprovals(): Promise<PendingApprovalsView | null> {
    const id = get(sessionId)
    if (!id) return null
    let response: Response
    try {
      response = await fetch(
        `${CONVERSATIONS_BASE_URL}/${encodeURIComponent(id)}/approvals`,
      )
    } catch {
      return null
    }
    if (!response.ok) return null
    try {
      const data = (await response.json()) as {
        batch_id?: string
        items?: ToolCallsPendingItem[]
      }
      if (!data?.batch_id || !Array.isArray(data.items)) return null
      return { batchId: data.batch_id, items: data.items }
    } catch {
      return null
    }
  }

  async function decide(
    batchId: string,
    decisions: Record<string, boolean>,
  ): Promise<{ ok: boolean; conflict?: boolean; error?: string }> {
    const id = get(sessionId)
    if (!id) return { ok: false, error: "No active conversation." }
    // The resumed execution streams on the observer into a fresh turn (the
    // old execute-tools continuation opened one implicitly by streaming into
    // the same assistant message the pending round left behind — the exec
    // framing + outputs land in the CURRENT turn, so no beginTurn here).
    let response: Response
    try {
      response = await fetch(
        `${CONVERSATIONS_BASE_URL}/${encodeURIComponent(id)}/approvals/decisions`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ batch_id: batchId, decisions }),
        },
      )
    } catch (err) {
      return {
        ok: false,
        error: err instanceof Error ? err.message : String(err),
      }
    }
    if (response.status === 409) {
      // Two tabs: the other one decided first; the stream carries the
      // resolution either way (functional spec §5).
      return { ok: false, conflict: true }
    }
    if (!response.ok) {
      return {
        ok: false,
        error: `Could not submit approvals (${response.status}).`,
      }
    }
    setWorking(true)
    return { ok: true }
  }

  async function stop(): Promise<void> {
    const id = get(sessionId)
    if (!id) return
    // Optimistic only: the authoritative state change arrives as a
    // conversation-state event (idle for interactive, flag-off for auto).
    try {
      await fetch(`${CONVERSATIONS_BASE_URL}/${encodeURIComponent(id)}/stop`, {
        method: "POST",
      })
    } catch {
      /* idempotent; the run keeps going and the user can retry */
    }
  }

  return {
    autoModeOn: { subscribe: autoModeOn.subscribe },
    armed: { subscribe: armed.subscribe },
    working: { subscribe: working.subscribe },
    reconnecting: { subscribe: reconnecting.subscribe },
    retry: { subscribe: retry.subscribe },
    sessionId: { subscribe: sessionId.subscribe },
    offReason: { subscribe: offReason.subscribe },
    connection: { subscribe: connection.subscribe },
    bind,
    ensure,
    requestEnable,
    decline,
    sendMessage,
    stop,
    fetchApprovals,
    decide,
    beginReconnect,
    attach,
    detach,
    beginTurn,
    arm,
    disarm,
    _close: closeSource,
  }
}

export const main_conversation_store: MainConversationStore =
  createMainConversationStore()
