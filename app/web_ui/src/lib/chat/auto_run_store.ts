/**
 * Owns the auto-run lifecycle for the active conversation.
 *
 * Auto mode lifts the chat loop out of the browser into a server-owned runner
 * (Phase 2/3). This store drives that runner from the UI: enable / decline /
 * stop, and — critically — observes the per-run SSE stream as a pure observer,
 * feeding its bytes into the EXISTING ``StreamEventProcessor`` so the running
 * turn renders exactly like an interactive turn. Connection handling mirrors
 * ``jobs_store.ts``: opening or closing the stream never mutates the run; the
 * authoritative "on/off" state comes from the runner's ``auto-mode-on`` /
 * ``auto-mode-off`` control events, so it is correct on first paint after a
 * re-attach (not just after a local toggle).
 */

import { get, writable, type Readable } from "svelte/store"
import { base_url } from "$lib/api_client"
import type { components } from "$lib/api_schema"
import {
  StreamEventProcessor,
  consumeSseStream,
  type ChatMessage,
  type StreamEvent,
  type ToolCallsPendingItem,
} from "./streaming_chat"

export type EnableAutoRequest = components["schemas"]["EnableAutoRequest"]
export type DeclineAutoRequest = components["schemas"]["DeclineAutoRequest"]
export type ResolveAutoResponse = components["schemas"]["ResolveAutoResponse"]

const AUTO_BASE_URL = `${base_url}/api/chat/auto`

// Lifecycle of the per-run events EventSource, surfaced for tests / debugging.
// A pure observer: this only reports the connection, it never mutates the run.
export type AutoConnection = "idle" | "connecting" | "open" | "closed"

/**
 * Callbacks the chat session store registers so the auto runner can drive the
 * same conversation the interactive stream drives. Mirrors the hooks
 * ``streamChat`` already calls, plus turn lifecycle and an off-signal.
 */
export interface AutoRunChatSink {
  /** Begin a fresh assistant turn (append an empty assistant message). */
  beginAssistantTurn: () => void
  onAssistantMessage: (update: (draft: ChatMessage) => void) => void
  onChatTrace: (traceId: string) => void
  onInlineError: (message: string, traceId?: string, code?: string) => void
  onToolExecutionStart: (toolCount: number) => void
  onToolExecutionEnd: (toolCount: number) => void
  onShowActivityIndicator: (show: boolean) => void
  /**
   * A burst started / is live (RUNNING). Lets the chat view drive the SAME
   * loading affordances (thinking dots, animated icon) as interactive
   * streaming while the runner works between events. ``false`` on burst end.
   */
  onWorkingChange: (working: boolean) => void
  /** The runner echoed an injected user message; render it as a new user turn. */
  onUserMessage: (content: string) => void
  /**
   * A burst ended but auto mode stays ON (asked_user / done / error /
   * max_rounds). The indicator persists; only the working sub-state clears.
   */
  onAutoModeIdle: (reason: string | null) => void
  /** Auto mode turned off for the conversation (user_stopped / user_disabled). */
  onAutoModeOff: (reason: string | null) => void
  /**
   * Graceful stop (functional spec §4.4(1)): the runner finished the in-flight
   * turn and surfaced its client tool calls for approval instead of
   * auto-executing them. Hand off to the EXISTING normal approval +
   * /api/chat/execute-tools flow (the conversation is now in normal mode). The
   * runner publishes auto-mode-off(user_stopped) alongside this, so the
   * indicator clears on its own.
   */
  onToolCallsPending: (items: ToolCallsPendingItem[]) => void
}

export interface AutoRunStore {
  /** Conversation auto-mode flag: ON across RUNNING and IDLE bursts. */
  autoModeOn: Readable<boolean>
  /** Burst sub-state: a burst is actively running (vs idle, flag still on). */
  working: Readable<boolean>
  /**
   * A transient "reconnecting…" window while a re-attach (hard-refresh resync or
   * History restore) resolves → hydrates → attaches the live observer. Drives a
   * brief loading affordance in the transcript so a reattaching conversation
   * doesn't look done/idle before liveness is known. Cleared once the events
   * stream is established (or on error / off / idle). Always false in the
   * normal (non-reattach) enable flow.
   */
  reconnecting: Readable<boolean>
  runId: Readable<string | null>
  offReason: Readable<string | null>
  connection: Readable<AutoConnection>
  bind(sink: AutoRunChatSink): void
  requestEnable(
    seed: EnableAutoRequest,
  ): Promise<{ ok: boolean; error?: string }>
  decline(req: DeclineAutoRequest): Promise<void>
  /**
   * Inject a user message into the live conversation WITHOUT disabling auto
   * mode (Revision R1). Routes to ``POST /api/chat/auto/{run_id}/message``; the
   * runner echoes the message + streams the resulting burst on the observer
   * stream. Never stops the run.
   */
  sendMessage(
    text: string,
    traceId?: string,
  ): Promise<{ ok: boolean; error?: string }>
  stop(): Promise<void>
  /**
   * Resolve a (possibly stale) trace id to the conversation's active auto run.
   * Used to resync after a hard refresh: returns the run id plus the run's
   * CURRENT leaf trace id so the caller can hydrate the rounds completed while
   * the tab was gone, then ``attach``. ``null`` when no active run owns the
   * trace (404) or the request fails — the caller leaves the restored state.
   */
  resolve(traceId: string): Promise<ResolveAutoResponse | null>
  /**
   * Mark the start of a re-attach (after we know it's an active run) so the
   * transcript shows a transient "reconnecting…" affordance during the
   * resolve→hydrate→attach window. ``attach`` keeps it on through the connecting
   * phase and clears it once the stream is established. Safe no-op clear paths
   * (error / off / idle) guarantee it can't get stuck on.
   */
  beginReconnect(): void
  /**
   * Open the per-run events SSE and re-attach. ``initialWorking`` (from the
   * resolve response status) drives the thinking indicator immediately on
   * attach; omit it when the liveness isn't known up front (History restore).
   */
  attach(runId: string, initialWorking?: boolean): void
  /** Stop observing + clear the indicator without ending the run (navigation). */
  detach(): void
  /** Exposed for tests / explicit teardown; not part of normal usage. */
  _close(): void
}

export function createAutoRunStore(): AutoRunStore {
  const autoModeOn = writable<boolean>(false)
  const working = writable<boolean>(false)
  const reconnecting = writable<boolean>(false)
  const runId = writable<string | null>(null)
  const offReason = writable<string | null>(null)
  const connection = writable<AutoConnection>("idle")

  function setWorking(next: boolean): void {
    working.set(next)
    sink?.onWorkingChange(next)
  }

  let sink: AutoRunChatSink | null = null
  let eventSource: EventSource | null = null

  function bind(newSink: AutoRunChatSink): void {
    sink = newSink
  }

  function buildProcessor(): StreamEventProcessor {
    return new StreamEventProcessor({
      onAssistantMessage: (update) => sink?.onAssistantMessage(update),
      onChatTrace: (tid) => sink?.onChatTrace(tid),
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
  }

  function clearToOff(reason: string | null): void {
    closeSource()
    autoModeOn.set(false)
    setWorking(false)
    reconnecting.set(false)
    runId.set(null)
    offReason.set(reason)
    connection.set("closed")
    sink?.onAutoModeOff(reason)
  }

  // Stop observing the current run and clear the indicator WITHOUT signalling the
  // sink (the run keeps going server-side; the user just navigated away — e.g.
  // New Chat / load another conversation). Re-attach is available from history.
  function detach(): void {
    closeSource()
    autoModeOn.set(false)
    setWorking(false)
    reconnecting.set(false)
    runId.set(null)
    offReason.set(null)
    connection.set("idle")
  }

  // Mark the start of a re-attach (resolve→hydrate→attach). attach() keeps this
  // on through the connecting phase and clears it once the stream is established;
  // all off/idle/error paths also clear it so it can never get stuck on.
  function beginReconnect(): void {
    reconnecting.set(true)
  }

  // --- Control-event handling on the per-run stream ---------------------------
  // Returns true when it claims the event (so it isn't forwarded to the
  // processor). The control vocabulary is auto-mode-on / auto-mode-idle /
  // auto-mode-off / user-message; every other event is normal chat SSE and
  // flows to the processor unchanged.
  function handleControlEvent(event: StreamEvent): boolean {
    if (event.type === "auto-mode-state") {
      // Phase 9: on-subscribe liveness snapshot. The run published its CURRENT
      // working/idle state the instant we attached, so reflect it immediately
      // (show the thinking indicator if working, "· waiting for you" if idle)
      // instead of looking idle until the next event lands. Attach is now
      // established → clear the transient reconnecting affordance.
      autoModeOn.set(!!event.flag_on)
      setWorking(!!event.working)
      reconnecting.set(false)
      if (event.run_id) runId.set(event.run_id)
      offReason.set(null)
      return true
    }
    if (event.type === "auto-mode-on") {
      // The conversation flag is on AND a burst is now running.
      autoModeOn.set(true)
      setWorking(true)
      reconnecting.set(false)
      if (event.run_id) runId.set(event.run_id)
      offReason.set(null)
      return true
    }
    if (event.type === "auto-mode-idle") {
      // A burst ended but the flag STAYS on (Revision R1). Keep the indicator;
      // only clear the working sub-state so the thinking dots stop. An idle
      // marker on attach also means we're established → clear reconnecting.
      autoModeOn.set(true)
      setWorking(false)
      reconnecting.set(false)
      sink?.onAutoModeIdle(event.reason ?? null)
      return true
    }
    if (event.type === "auto-mode-off") {
      clearToOff(event.reason ?? null)
      return true
    }
    if (event.type === "user-message") {
      // The runner echoed an injected user message. Render it as a fresh user
      // turn (then a new assistant turn for the burst it triggers) so every
      // observer — including the sender — sees it, consistent with replay.
      setWorking(true)
      sink?.onUserMessage(event.content ?? "")
      return true
    }
    if (event.type === "tool-calls-pending") {
      // Graceful stop (functional spec §4.4(1)): the runner surfaced the final
      // turn's client tool calls for approval instead of auto-executing them.
      // Hand off to the EXISTING normal approval + execute-tools flow. The
      // accompanying auto-mode-off(user_stopped) clears the indicator; here we
      // only stop the working sub-state and delegate the pending calls.
      setWorking(false)
      sink?.onToolCallsPending(Array.isArray(event.items) ? event.items : [])
      return true
    }
    return false
  }

  function attach(newRunId: string, initialWorking?: boolean): void {
    const EventSourceCtor = globalThis.EventSource
    if (!EventSourceCtor) {
      // No SSE support: don't leave a "reconnecting…" affordance stuck on.
      reconnecting.set(false)
      return
    }
    closeSource()

    runId.set(newRunId)
    autoModeOn.set(true)
    // Drive the working sub-state from the surfaced liveness when known
    // (Phase 9: the resolve response carries the run's status). When unknown
    // (History restore, which has no status), presume a live burst — the buffer
    // replay + on-subscribe state marker correct it with no visible gap.
    setWorking(initialWorking ?? true)
    offReason.set(null)
    connection.set("connecting")

    const processor = buildProcessor()
    const source = new EventSourceCtor(
      `${AUTO_BASE_URL}/${encodeURIComponent(newRunId)}/events`,
    )
    eventSource = source

    source.onopen = () => {
      if (eventSource !== source) return
      connection.set("open")
      // Attach is established (resolve→hydrate→attach complete). Clear the
      // transient reconnecting affordance; the run's liveness now arrives via the
      // buffer replay + on-subscribe state marker.
      reconnecting.set(false)
    }

    source.onmessage = (e: MessageEvent) => {
      if (eventSource !== source) return
      // First byte over the stream also means we're established — clear the
      // reconnecting affordance even if onopen didn't fire (test environments).
      reconnecting.set(false)
      const data = typeof e.data === "string" ? e.data.trim() : ""
      if (!data || data === "[DONE]") return
      let event: StreamEvent
      try {
        event = JSON.parse(data) as StreamEvent
      } catch {
        return
      }
      if (handleControlEvent(event)) return
      processor.handleEvent(event)
    }

    source.onerror = () => {
      // Only act on the active source (avoid racing a teardown / re-attach).
      if (eventSource !== source) return
      // No reconnect loop. Whether the run was never reachable (GC'd / unknown →
      // events 404, never opened) or it opened then dropped without an explicit
      // off, the conversation is persisted server-side: degrade cleanly to the
      // hydrated-history "off" state — never a hard error (ui_design §5). A run
      // that finished normally already cleared us via auto-mode-off.
      clearToOff(null)
    }
  }

  async function requestEnable(
    seed: EnableAutoRequest,
  ): Promise<{ ok: boolean; error?: string }> {
    let response: Response
    try {
      response = await fetch(`${AUTO_BASE_URL}/enable`, {
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
    let data: { run_id?: string }
    try {
      data = (await response.json()) as { run_id?: string }
    } catch {
      return { ok: false, error: "Malformed response from enable auto mode." }
    }
    if (!data.run_id) {
      return { ok: false, error: "Enable auto mode did not return a run id." }
    }
    // Manual enable (Revision R1, functional spec §4.1(2)) only ARMS the
    // conversation: the server creates the run IDLE without starting an empty
    // upstream burst, so there's no immediate assistant turn — the indicator
    // just turns on ("waiting for you") and the next user message starts the
    // first burst via the /message inject path. The backend-tool path (an
    // ``enable_tool_call_id`` is present) DOES start a burst immediately, so we
    // open a fresh assistant turn to render it.
    const armingOnly =
      !seed.enable_tool_call_id &&
      !(seed.pending_tool_calls && seed.pending_tool_calls.length > 0)
    if (!armingOnly) {
      // A fresh assistant turn renders the runner's first burst.
      sink?.beginAssistantTurn()
    }
    attach(data.run_id)
    return { ok: true }
  }

  async function decline(req: DeclineAutoRequest): Promise<void> {
    // Decline resolves enable→declined server-side and resumes the normal
    // interactive stream; consume it into the same sink as a fresh turn.
    let response: Response
    try {
      response = await fetch(`${AUTO_BASE_URL}/decline`, {
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
    traceId?: string,
  ): Promise<{ ok: boolean; error?: string }> {
    const id = get(runId)
    if (!id) {
      return { ok: false, error: "No active auto run to send the message to." }
    }
    // Optimistically reflect that a burst is (re)starting so the indicator
    // shows immediately; the echoed user-message + burst events confirm it.
    setWorking(true)
    let response: Response
    try {
      response = await fetch(
        `${AUTO_BASE_URL}/${encodeURIComponent(id)}/message`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: text, trace_id: traceId ?? null }),
        },
      )
    } catch (err) {
      return {
        ok: false,
        error: err instanceof Error ? err.message : String(err),
      }
    }
    if (!response.ok) {
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

  async function resolve(traceId: string): Promise<ResolveAutoResponse | null> {
    let response: Response
    try {
      response = await fetch(
        `${AUTO_BASE_URL}/resolve?trace_id=${encodeURIComponent(traceId)}`,
      )
    } catch {
      // Network error — treat as "no active run"; the restored state stands.
      return null
    }
    // 404 (no active run) or any non-OK status: leave the restored state as-is.
    if (!response.ok) return null
    try {
      const data = (await response.json()) as ResolveAutoResponse
      if (!data?.run_id || !data?.current_trace_id) return null
      return data
    } catch {
      return null
    }
  }

  async function stop(): Promise<void> {
    const id = get(runId)
    if (!id) return
    // Optimistic only: the authoritative clear arrives as auto-mode-off. We do
    // not flip state here so a failed stop doesn't lie about being off.
    try {
      await fetch(`${AUTO_BASE_URL}/${encodeURIComponent(id)}/stop`, {
        method: "POST",
      })
    } catch {
      /* idempotent; the run keeps going and the user can retry */
    }
  }

  return {
    autoModeOn: { subscribe: autoModeOn.subscribe },
    working: { subscribe: working.subscribe },
    reconnecting: { subscribe: reconnecting.subscribe },
    runId: { subscribe: runId.subscribe },
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
    _close: closeSource,
  }
}

export const auto_run_store: AutoRunStore = createAutoRunStore()
