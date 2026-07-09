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
  chatGenerateId,
  consumeSseStream,
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
export type DeclineAutoModeRequest =
  components["schemas"]["DeclineAutoModeRequest"]
export type ResolveConversationResponse =
  components["schemas"]["ResolveConversationResponse"]

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

// Lifecycle of the state-firehose EventSource, surfaced for tests / debugging.
// A pure observer: this only reports the connection, it never mutates a run.
export type ConversationConnection = "idle" | "connecting" | "open" | "errored"

/**
 * `conversation-state` payload as it arrives on the firehose and on the
 * per-conversation observer stream (as the on-subscribe liveness marker).
 * Replaces the old `kiln-subagent-status` shape: `session_id` is the handle,
 * `state` uses the unified RunState strings, and trace ids are deliberately
 * absent (the browser never sees trace ids on the new event vocabulary — the
 * REST item carries the hydration leaf until phase 5).
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
   * Replace `children` with the sub-agents of the conversation owning the
   * given parent handle — while parents run on the legacy loops this is the
   * main transcript's (possibly stale) leaf trace id, which the server
   * resolves through the whole trace chain. `null` (no conversation yet)
   * clears the list. Deduped by value, so it is safe to call on every
   * reactive trace change.
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
    // events): the item's current_trace_id is refreshed by observe()'s
    // re-fetch instead, so hydration never depends on event payloads.
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

  function updateChildFromItem(item: ConversationItem): void {
    children.update((list) =>
      list.map((child) =>
        child.session_id === item.session_id ? { ...child, ...item } : child,
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
    let child = get(children).find((c) => c.session_id === sessionId)
    if (!child) return
    const abort = new AbortController()
    const obs: ChildObservation = { abort, pendingFreshTurn: true }
    observations.set(sessionId, obs)

    // 0. Re-fetch the item so hydration uses a FRESH persisted leaf. The old
    // store refreshed current_trace_id from status events; conversation-state
    // events deliberately carry no trace ids, so a re-observe (e.g. selecting
    // a child again after its stream ended) would otherwise hydrate a stale
    // snapshot. Best effort: on failure the listed item is used as-is.
    try {
      const response = await fetch(
        `${CONVERSATIONS_BASE_URL}/${encodeURIComponent(sessionId)}`,
        { signal: abort.signal },
      )
      if (response.ok) {
        const item = (await response.json()) as ConversationItem
        if (item?.session_id === sessionId) {
          updateChildFromItem(item)
          child = { ...child, ...item }
        }
      }
    } catch {
      /* aborted or unreachable — hydrate with what the list already has */
    }
    if (abort.signal.aborted) return

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
// Auto conversation store — the fold-in of the deleted `auto_run_store.ts`
// (phase 3). Owns the auto-mode lifecycle of the ACTIVE (main) conversation:
// enable / decline / stop / inject / resolve against `/api/conversations`,
// plus a pure-observer attachment to the conversation's events stream whose
// bytes feed the EXISTING `StreamEventProcessor` so an auto burst renders
// exactly like an interactive turn. Connection handling mirrors
// `jobs_store.ts`: opening or closing the stream never mutates the run; the
// authoritative on/off state comes from the unified `conversation-state`
// events, mapped below onto the exact states the old
// `auto-mode-on/off/idle/state` vocabulary drove — so it is correct on first
// paint after a re-attach (not just after a local toggle).
// ─────────────────────────────────────────────────────────────────────────────

// Lifecycle of the per-conversation events EventSource, surfaced for tests /
// debugging. A pure observer: this only reports the connection, it never
// mutates the run.
export type AutoConnection = "idle" | "connecting" | "open" | "closed"

/**
 * Callbacks the chat session store registers so the desktop-owned auto run
 * can drive the same conversation the interactive stream drives. Mirrors the
 * hooks `streamChat` already calls, plus turn lifecycle and an off-signal.
 * (The old `AutoRunChatSink`, unchanged — the sink contract is what
 * guarantees zero visual change across the event-vocabulary swap.)
 */
export interface AutoConversationSink {
  /** Begin a fresh assistant turn (append an empty assistant message). */
  beginAssistantTurn: () => void
  onAssistantMessage: (update: (draft: ChatMessage) => void) => void
  onChatTrace: (traceId: string) => void
  /** Fired when an auto-burst snapshot event carries ``context_usage``. */
  onContextUsage: (usage: ContextUsage) => void
  /**
   * Fired when an auto-burst emits ``kiln_compaction_status``:
   * ``true`` to show the "summarizing…" indicator, ``false`` to clear it.
   */
  onCompactionStatus: (compacting: boolean) => void
  onInlineError: (message: string, traceId?: string, code?: string) => void
  onToolExecutionStart: (toolCount: number) => void
  onToolExecutionEnd: (toolCount: number) => void
  onShowActivityIndicator: (show: boolean) => void
  /**
   * A burst started / is live (RUNNING). Lets the chat view drive the SAME
   * loading affordances (thinking dots, animated icon) as interactive
   * streaming while the run works between events. ``false`` on burst end.
   */
  onWorkingChange: (working: boolean) => void
  /**
   * The run echoed an injected user message; render it as a new user turn.
   * ``echoId`` is the message's stable id, so the sink can render it
   * idempotently (a buffer replay on re-attach re-emits the echo for a
   * message already shown).
   */
  onUserMessage: (content: string, echoId?: string) => void
  /**
   * A burst ended but auto mode stays ON (asked_user / done / error /
   * max_rounds / armed). The indicator persists; only working clears.
   */
  onAutoModeIdle: (reason: string | null) => void
  /** Auto mode turned off (user_stopped / user_disabled). */
  onAutoModeOff: (reason: string | null) => void
  /**
   * Graceful stop (functional spec §3): the run finished the in-flight turn
   * and surfaced its client tool calls for approval instead of
   * auto-executing them. Hand off to the EXISTING normal approval +
   * /api/chat/execute-tools flow (the conversation is now in normal mode).
   * The flag-off state publishes alongside, so the indicator clears on its
   * own.
   */
  onToolCallsPending: (items: ToolCallsPendingItem[]) => void
}

export interface AutoConversationStore {
  /** Conversation auto-mode flag: ON across RUNNING and IDLE bursts. */
  autoModeOn: Readable<boolean>
  /**
   * Client-only "armed" flag (Revision R2): the user turned auto mode on for
   * a brand-new conversation that has no ``trace_id`` yet, so there is no
   * desktop-owned conversation to key. The indicator shows on ("waiting for
   * you") with NO server call. The FIRST ``sendMessage`` creates the
   * conversation (enable with the first message + no trace_id) and clears
   * this. Distinct from ``autoModeOn`` (which tracks a real desktop-owned
   * conversation): the footer treats ``autoModeOn || armed`` as "on".
   * Disable/decline before the first send clears it.
   */
  armed: Readable<boolean>
  /** Burst sub-state: a burst is actively running (vs idle, flag still on). */
  working: Readable<boolean>
  /**
   * A transient "reconnecting…" window while a re-attach (hard-refresh resync
   * or History restore) resolves → hydrates → attaches the live observer.
   * Cleared once the events stream is established (or on error / off /
   * idle). Always false in the normal (non-reattach) enable flow.
   */
  reconnecting: Readable<boolean>
  /**
   * Transient retry affordance: ``{ attempt, max }`` while a transient
   * upstream failure is being retried with backoff, else ``null``.
   */
  retry: Readable<{ attempt: number; max: number } | null>
  /** The auto conversation's session id (was the old run id). */
  sessionId: Readable<string | null>
  offReason: Readable<string | null>
  connection: Readable<AutoConnection>
  bind(sink: AutoConversationSink): void
  requestEnable(
    seed: CreateAutoConversationRequest,
  ): Promise<{ ok: boolean; error?: string }>
  decline(req: DeclineAutoModeRequest): Promise<void>
  /**
   * Inject a user message into the live conversation WITHOUT disabling auto
   * mode. Routes to ``POST /api/conversations/{sid}/messages``; the run
   * echoes the message + streams the resulting burst on the observer stream.
   * Never stops the run. (The old endpoint also took a trace_id for the idle
   * re-arm; the supervisor's own leaf is authoritative now, so it is gone.)
   */
  sendMessage(text: string): Promise<{ ok: boolean; error?: string }>
  stop(): Promise<void>
  /**
   * Resolve a (possibly stale) trace id to the conversation's live auto
   * record. Used to resync after a hard refresh: returns the session id plus
   * the conversation's CURRENT leaf trace id so the caller can hydrate the
   * rounds completed while the tab was gone, then ``attach``. ``null`` when
   * no live flag-on auto conversation owns the trace (404) or the request
   * fails — the caller leaves the restored state.
   */
  resolve(traceId: string): Promise<ResolveConversationResponse | null>
  /**
   * Mark the start of a re-attach (after we know it's an active run) so the
   * transcript shows a transient "reconnecting…" affordance during the
   * resolve→hydrate→attach window. ``attach`` keeps it on through the
   * connecting phase and clears it once the stream is established. Safe
   * no-op clear paths (error / off / idle) guarantee it can't get stuck on.
   */
  beginReconnect(): void
  /**
   * Open the conversation's events SSE and re-attach. ``initialWorking``
   * (from the resolve response state) drives the thinking indicator
   * immediately on attach; omit it when the liveness isn't known up front
   * (History restore). ``openInflightTurn`` opens a fresh assistant turn for
   * the replayed in-flight round so it doesn't overwrite the last hydrated
   * bubble — set on re-attach (resync / History restore), left false on the
   * initial burst attach.
   */
  attach(
    sessionId: string,
    initialWorking?: boolean,
    openInflightTurn?: boolean,
  ): void
  /** Stop observing + clear the indicator without ending the run (navigation). */
  detach(): void
  /**
   * Client-arm auto mode on a brand-new conversation (Revision R2). No
   * server call — the indicator turns on ("waiting for you") and the first
   * ``sendMessage`` creates the conversation. Idempotent.
   */
  arm(): void
  /** Clear the client-armed flag (disable/decline before the first send). */
  disarm(): void
  /** Exposed for tests / explicit teardown; not part of normal usage. */
  _close(): void
}

export function createAutoConversationStore(): AutoConversationStore {
  const autoModeOn = writable<boolean>(false)
  const armed = writable<boolean>(false)
  const working = writable<boolean>(false)
  const reconnecting = writable<boolean>(false)
  const sessionId = writable<string | null>(null)
  const offReason = writable<string | null>(null)
  const connection = writable<AutoConnection>("idle")
  // Transient "retrying N/M…" affordance: set on each kiln-chat-retry event,
  // cleared by the next event of any other kind (the recovered round's first
  // event, or a state marker). Null when no retry is in flight.
  const retry = writable<{ attempt: number; max: number } | null>(null)

  function setWorking(next: boolean): void {
    working.set(next)
    sink?.onWorkingChange(next)
  }

  let sink: AutoConversationSink | null = null
  let eventSource: EventSource | null = null
  // True from attach() until the FIRST conversation-state event arrives on
  // the new stream: that event is the bus's ON-SUBSCRIBE marker (it follows
  // the buffer replay), a snapshot of where the run already is — not a
  // transition. The old vocabulary made this distinction structurally
  // (attaching to a RUNNING run got `auto-mode-state`, which never signalled
  // the idle sink); the unified event doesn't, so the store must: the marker
  // updates the flag/working affordances but must NOT fire
  // sink.onAutoModeIdle — that hook is the chat session store's
  // burst-settled signal (it flushes queued messages), and a mere re-attach
  // to an idle conversation is not a settle.
  let attachMarkerPending = false
  // On a re-attach (resync / History restore) the buffer replay carries ONLY
  // the current in-flight round (the run buffer clears on every snapshot),
  // but the restored/hydrated transcript's last assistant bubble holds
  // earlier rounds. Without opening a fresh turn first, the in-flight round's
  // first flush would overwrite that bubble (``draft.parts = next``) and
  // destroy those rounds. So on re-attach we open a fresh assistant turn
  // lazily — on the first assistant content of the in-flight round (or it's
  // consumed by an injected-message echo, which opens its own turn). Lazy so
  // an idle re-attach leaves no empty bubble.
  let pendingInflightTurn = false

  function consumeInflightTurn(): void {
    if (pendingInflightTurn) {
      pendingInflightTurn = false
      sink?.beginAssistantTurn()
    }
  }

  function bind(newSink: AutoConversationSink): void {
    sink = newSink
  }

  function buildProcessor(): StreamEventProcessor {
    return new StreamEventProcessor({
      onAssistantMessage: (update) => {
        // First assistant content of a re-attached in-flight round: open a
        // fresh turn so it renders into its own bubble instead of
        // overwriting the last.
        consumeInflightTurn()
        sink?.onAssistantMessage(update)
      },
      onChatTrace: (tid) => sink?.onChatTrace(tid),
      onContextUsage: (usage) => sink?.onContextUsage(usage),
      onCompactionStatus: (compacting) => sink?.onCompactionStatus(compacting),
      onInlineError: (message, traceId, code) =>
        sink?.onInlineError(message, traceId, code),
      onToolExecutionStart: (count) => sink?.onToolExecutionStart(count),
      onToolExecutionEnd: (count) => sink?.onToolExecutionEnd(count),
      onShowActivityIndicator: (show) => sink?.onShowActivityIndicator(show),
    })
  }

  function closeSource(): void {
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
    // A pending fresh-turn belongs to the stream we're tearing down; drop it
    // so a later attach can't open a stray empty bubble. Ditto the pending
    // attach marker — it describes a stream that no longer exists.
    pendingInflightTurn = false
    attachMarkerPending = false
  }

  function clearToOff(reason: string | null): void {
    closeSource()
    autoModeOn.set(false)
    armed.set(false)
    setWorking(false)
    reconnecting.set(false)
    retry.set(null)
    sessionId.set(null)
    offReason.set(reason)
    connection.set("closed")
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

  // Stop observing the current conversation and clear the indicator WITHOUT
  // signalling the sink (the run keeps going server-side; the user just
  // navigated away — e.g. New Chat / load another conversation). Re-attach is
  // available from history.
  function detach(): void {
    closeSource()
    autoModeOn.set(false)
    armed.set(false)
    setWorking(false)
    reconnecting.set(false)
    retry.set(null)
    sessionId.set(null)
    offReason.set(null)
    connection.set("idle")
  }

  // Mark the start of a re-attach (resolve→hydrate→attach). attach() keeps
  // this on through the connecting phase and clears it once the stream is
  // established; all off/idle/error paths also clear it so it can never get
  // stuck on.
  function beginReconnect(): void {
    reconnecting.set(true)
  }

  // --- Control-event handling on the observer stream --------------------------
  // Returns true when it claims the event (so it isn't forwarded to the
  // processor). The lifecycle vocabulary is the ONE `conversation-state`
  // event, mapped back onto the exact states the old per-kind events drove:
  //
  //   old auto-mode-on            → state=running, auto_flag=true
  //   old auto-mode-idle{reason}  → state=idle,    auto_flag=true, idle_reason
  //   old auto-mode-off{reason}   → auto_flag=false (idle_reason carries
  //                                 user_stopped/user_disabled)
  //   old auto-mode-state{working}→ the on-subscribe marker: working ⇔ running
  //
  // `user-message` / `kiln-chat-retry` / `tool-calls-pending` are unchanged;
  // every other event is normal chat SSE and flows to the processor.
  function handleControlEvent(event: StreamEvent): boolean {
    if (event.type === "conversation-state") {
      // Only this conversation's auto lifecycle is ours to reflect. (The
      // per-conversation stream carries no other session's events, but guard
      // by kind anyway — defense in depth against future multiplexing.)
      if (event.kind && event.kind !== "auto") return true
      // The first state event after attach is the on-subscribe MARKER (a
      // snapshot, not a transition) — consume the flag; everything after it
      // is a live transition. See the attachMarkerPending declaration.
      const isAttachMarker = attachMarkerPending
      attachMarkerPending = false
      // Any state event means the attach is established — clear the
      // transient reconnecting affordance (old on/idle/state handling).
      reconnecting.set(false)
      if (event.session_id) sessionId.set(event.session_id)
      if (event.auto_flag === false) {
        // Old auto-mode-off: published on explicit stop/disable only; the
        // reason (user_stopped/user_disabled) rides idle_reason. A late
        // attach to an OFF record gets this as its marker too — the old
        // terminal off marker likewise drove the off handler on subscribe.
        clearToOff(event.idle_reason ?? null)
        return true
      }
      autoModeOn.set(true)
      offReason.set(null)
      if (event.state === "idle") {
        // Old auto-mode-idle: a burst ended (or the on-subscribe marker of
        // an idle conversation, incl. "armed") but the flag STAYS on. Keep
        // the indicator; only clear the working sub-state.
        setWorking(false)
        // No in-flight round produced content — drop the pending fresh-turn
        // so we don't open an empty bubble.
        pendingInflightTurn = false
        // Only a real burst-settled TRANSITION signals the idle sink (which
        // flushes queued messages in the session store); the attach-time
        // marker merely reports where the run already is — the old
        // auto-mode-state marker never fired this hook.
        if (!isAttachMarker) {
          sink?.onAutoModeIdle(event.idle_reason ?? null)
        }
      } else {
        // running (old auto-mode-on / state{working:true}). AWAITING_
        // APPROVAL is unreachable for the auto policy but would also mean
        // "a turn is in flight" — same affordance.
        setWorking(true)
      }
      return true
    }
    if (event.type === "kiln-chat-retry") {
      // A transient upstream failure is being retried with backoff. The
      // burst is still working — keep the indicator on and surface
      // "retrying N/M…" so the user sees progress rather than a hard error.
      setWorking(true)
      retry.set({
        attempt: event.attempt ?? 0,
        max: event.max_attempts ?? 0,
      })
      return true
    }
    if (event.type === "user-message") {
      // The run echoed an injected user message. Render it as a fresh user
      // turn (then a new assistant turn for the burst it triggers) so every
      // observer — including the sender — sees it, consistent with replay.
      // The echo id lets the sink dedupe a replayed echo (re-attach) against
      // a message it already shows.
      setWorking(true)
      // The echo opens (or dedupes into) its own assistant turn, so the
      // in-flight round renders there — consume any pending fresh-turn to
      // avoid a second.
      pendingInflightTurn = false
      sink?.onUserMessage(event.content ?? "", event.id)
      return true
    }
    if (event.type === "tool-calls-pending") {
      // Graceful stop (functional spec §3): the run surfaced the final
      // turn's client tool calls for approval instead of auto-executing
      // them. Hand off to the EXISTING normal approval + execute-tools flow.
      // The accompanying flag-off state clears the indicator; here we only
      // stop the working sub-state and delegate the pending calls.
      setWorking(false)
      sink?.onToolCallsPending(Array.isArray(event.items) ? event.items : [])
      return true
    }
    return false
  }

  function attach(
    newSessionId: string,
    initialWorking?: boolean,
    openInflightTurn = false,
  ): void {
    const EventSourceCtor = globalThis.EventSource
    if (!EventSourceCtor) {
      // No SSE support: don't leave a "reconnecting…" affordance stuck on.
      reconnecting.set(false)
      return
    }
    closeSource()

    // Re-attach (resync / History restore): render the replayed in-flight
    // round into a fresh assistant turn rather than overwriting the last
    // hydrated one. (closeSource above cleared any stale value.) Not set on
    // the initial burst attach, which already opened its turn via
    // requestEnable.
    pendingInflightTurn = openInflightTurn
    // The next conversation-state event on this stream is the on-subscribe
    // marker (snapshot, not transition) — see handleControlEvent.
    attachMarkerPending = true

    sessionId.set(newSessionId)
    autoModeOn.set(true)
    // Drive the working sub-state from the surfaced liveness when known (the
    // resolve response carries the conversation's state). When unknown
    // (History restore, which has no state), presume a live burst — the
    // buffer replay + on-subscribe state marker correct it with no visible
    // gap.
    setWorking(initialWorking ?? true)
    offReason.set(null)
    connection.set("connecting")

    const processor = buildProcessor()
    const source = new EventSourceCtor(
      `${CONVERSATIONS_BASE_URL}/${encodeURIComponent(newSessionId)}/events`,
    )
    eventSource = source

    source.onopen = () => {
      if (eventSource !== source) return
      connection.set("open")
      // Attach is established (resolve→hydrate→attach complete). Clear the
      // transient reconnecting affordance; the run's liveness now arrives
      // via the buffer replay + on-subscribe state marker.
      reconnecting.set(false)
    }

    source.onmessage = (e: MessageEvent) => {
      if (eventSource !== source) return
      // First byte over the stream also means we're established — clear the
      // reconnecting affordance even if onopen didn't fire (test envs).
      reconnecting.set(false)
      const data = typeof e.data === "string" ? e.data.trim() : ""
      if (!data || data === "[DONE]") return
      let event: StreamEvent
      try {
        event = JSON.parse(data) as StreamEvent
      } catch {
        return
      }
      // Any event other than another retry means the retry window is over
      // (the round recovered, or the burst settled) — clear the affordance.
      if (event.type !== "kiln-chat-retry") retry.set(null)
      if (handleControlEvent(event)) {
        // A ``user-message`` echo opens a fresh assistant turn (the sink
        // calls beginAssistantTurn). Reset the processor so the prior turn's
        // accumulated parts aren't re-flushed into the new turn (which would
        // duplicate the previous round's text + tools into it).
        if (event.type === "user-message") processor.reset()
        return
      }
      processor.handleEvent(event)
    }

    source.onerror = () => {
      // Only act on the active source (avoid racing a teardown / re-attach).
      if (eventSource !== source) return
      // No reconnect loop. Whether the conversation was never reachable
      // (GC'd / unknown → events 404, never opened) or it opened then
      // dropped without an explicit off, the conversation is persisted
      // server-side: degrade cleanly to the hydrated-history "off" state —
      // never a hard error. A run that finished normally already cleared us
      // via the flag-off state event.
      clearToOff(null)
    }
  }

  async function requestEnable(
    seed: CreateAutoConversationRequest,
  ): Promise<{ ok: boolean; error?: string }> {
    // POST /api/conversations — the re-homed enable (old /api/chat/auto/
    // enable): creates or flips the auto conversation on the supervisor.
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
    // Manual enable only ARMS the conversation: the server creates the
    // record IDLE without starting an empty upstream burst, so there's no
    // immediate assistant turn — the indicator just turns on ("waiting for
    // you") and the next user message starts the first burst via the
    // /messages inject path. A burst starts immediately when the seed
    // carries content to run: the consent path (an ``enable_tool_call_id``)
    // OR a brand-new conversation seeded with the first user message
    // (``extra_messages``, Revision R2). In those cases open a fresh
    // assistant turn to render the first burst.
    const startsBurst =
      !!seed.enable_tool_call_id ||
      (!!seed.pending_tool_calls && seed.pending_tool_calls.length > 0) ||
      (!!seed.extra_messages && seed.extra_messages.length > 0)
    if (startsBurst) {
      sink?.beginAssistantTurn()
    }
    // A real desktop-owned conversation now owns the on-state; clear any
    // client-armed flag (Revision R2: the first send on a brand-new
    // conversation reaches here).
    armed.set(false)
    attach(data.session_id)
    return { ok: true }
  }

  async function decline(req: DeclineAutoModeRequest): Promise<void> {
    // Decline resolves enable→declined server-side and resumes the normal
    // interactive stream; consume it into the same sink as a fresh turn.
    // (POST /api/conversations/auto/decline — the re-homed
    // /api/chat/auto/decline, same body and stream semantics.)
    let response: Response
    try {
      response = await fetch(`${CONVERSATIONS_BASE_URL}/auto/decline`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req),
      })
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
    const reader = response.body?.getReader()
    if (!reader) {
      sink?.onInlineError("No response body when resuming chat.")
      return
    }
    sink?.beginAssistantTurn()
    try {
      await consumeSseStream(reader, buildProcessor())
    } catch (err) {
      sink?.onInlineError(err instanceof Error ? err.message : String(err))
    }
  }

  async function sendMessage(
    text: string,
  ): Promise<{ ok: boolean; error?: string }> {
    const id = get(sessionId)
    if (!id) {
      return {
        ok: false,
        error: "No active auto conversation to send the message to.",
      }
    }
    // Optimistically reflect that a burst is (re)starting so the indicator
    // shows immediately; the echoed user-message + burst events confirm it.
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
      // The optimistic working flag must be cleared on failure: no burst
      // started, so no state event will arrive to clear it and the thinking
      // indicator would stay stuck on.
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
    return { ok: true }
  }

  async function resolve(
    traceId: string,
  ): Promise<ResolveConversationResponse | null> {
    // GET /api/conversations/resolve — the re-homed /api/chat/auto/resolve,
    // keyed on session ids (the browser holds possibly-stale leaf trace ids
    // until phase 5).
    let response: Response
    try {
      response = await fetch(
        `${CONVERSATIONS_BASE_URL}/resolve?trace_id=${encodeURIComponent(traceId)}`,
      )
    } catch {
      // Network error — treat as "no active run"; the restored state stands.
      return null
    }
    // 404 (no live auto conversation) or any non-OK: leave restored state.
    if (!response.ok) return null
    try {
      const data = (await response.json()) as ResolveConversationResponse
      if (!data?.session_id || !data?.current_trace_id) return null
      return data
    } catch {
      return null
    }
  }

  async function stop(): Promise<void> {
    const id = get(sessionId)
    if (!id) return
    // Optimistic only: the authoritative clear arrives as the flag-off
    // conversation-state event. We do not flip state here so a failed stop
    // doesn't lie about being off.
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
    requestEnable,
    decline,
    sendMessage,
    stop,
    resolve,
    beginReconnect,
    attach,
    detach,
    arm,
    disarm,
    _close: closeSource,
  }
}

export const auto_conversation_store: AutoConversationStore =
  createAutoConversationStore()
