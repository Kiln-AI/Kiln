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
  type ContextUsage,
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
  /** Fired when a snapshot event echoes the stable ``conversation_id``. */
  onConversationId?: (conversationId: string) => void
  /** Fired when an auto-burst snapshot event carries ``context_usage``. */
  onContextUsage: (usage: ContextUsage) => void
  /**
   * Fired when an auto-burst emits ``kiln_compaction_status`` (Phase 5):
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
   * streaming while the runner works between events. ``false`` on burst end.
   */
  onWorkingChange: (working: boolean) => void
  /**
   * The runner echoed an injected user message; render it as a new user turn.
   * ``echoId`` is the message's stable id, so the sink can render it idempotently
   * (a buffer replay on re-attach re-emits the echo for a message already shown).
   */
  onUserMessage: (content: string, echoId?: string) => void
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
  /**
   * Client-only "armed" flag (Revision R2): the user turned auto mode on for a
   * brand-new conversation that has no ``trace_id`` yet, so there is no
   * server-owned run to key. The indicator shows on ("waiting for you") with NO
   * server call. The FIRST ``sendMessage`` creates the run (enable with the
   * first message + no trace_id) and clears this. Distinct from ``autoModeOn``
   * (which tracks a real server run): the footer treats ``autoModeOn || armed``
   * as "on". Disable/decline before the first send clears it.
   */
  armed: Readable<boolean>
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
  /**
   * Transient retry affordance: ``{ attempt, max }`` while a transient upstream
   * failure is being retried with backoff, else ``null``. Lets the transcript
   * show "retrying N/M…" instead of stalling silently or erroring.
   */
  retry: Readable<{ attempt: number; max: number } | null>
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
   * ``openInflightTurn`` opens a fresh assistant turn for the replayed in-flight
   * round so it doesn't overwrite the last hydrated bubble — set on re-attach
   * (resync / History restore), left false on the initial burst attach.
   */
  attach(
    runId: string,
    initialWorking?: boolean,
    openInflightTurn?: boolean,
  ): void
  /** Stop observing + clear the indicator without ending the run (navigation). */
  detach(): void
  /**
   * Client-arm auto mode on a brand-new conversation (Revision R2). No server
   * call — the indicator turns on ("waiting for you") and the first
   * ``sendMessage`` creates the run. Idempotent.
   */
  arm(): void
  /** Clear the client-armed flag (disable/decline before the first send). */
  disarm(): void
  /** Exposed for tests / explicit teardown; not part of normal usage. */
  _close(): void
}

export function createAutoRunStore(): AutoRunStore {
  const autoModeOn = writable<boolean>(false)
  const armed = writable<boolean>(false)
  const working = writable<boolean>(false)
  const reconnecting = writable<boolean>(false)
  const runId = writable<string | null>(null)
  const offReason = writable<string | null>(null)
  const connection = writable<AutoConnection>("idle")
  // Transient "retrying N/M…" affordance: set on each kiln-chat-retry event,
  // cleared by the next event of any other kind (the recovered round's first
  // event, or an idle/off marker). Null when no retry is in flight.
  const retry = writable<{ attempt: number; max: number } | null>(null)

  function setWorking(next: boolean): void {
    working.set(next)
    sink?.onWorkingChange(next)
  }

  let sink: AutoRunChatSink | null = null
  let eventSource: EventSource | null = null
  // On a re-attach (resync / History restore) the buffer replay carries ONLY the
  // current in-flight round (the run buffer clears on every snapshot), but the
  // restored/hydrated transcript's last assistant bubble holds earlier rounds.
  // Without opening a fresh turn first, the in-flight round's first flush would
  // overwrite that bubble (``draft.parts = next``) and destroy those rounds. So
  // on re-attach we open a fresh assistant turn lazily — on the first assistant
  // content of the in-flight round (or it's consumed by an injected-message echo,
  // which opens its own turn). Lazy so an idle re-attach leaves no empty bubble.
  let pendingInflightTurn = false

  function consumeInflightTurn(): void {
    if (pendingInflightTurn) {
      pendingInflightTurn = false
      sink?.beginAssistantTurn()
    }
  }

  function bind(newSink: AutoRunChatSink): void {
    sink = newSink
  }

  function buildProcessor(): StreamEventProcessor {
    return new StreamEventProcessor({
      onAssistantMessage: (update) => {
        // First assistant content of a re-attached in-flight round: open a fresh
        // turn so it renders into its own bubble instead of overwriting the last.
        consumeInflightTurn()
        sink?.onAssistantMessage(update)
      },
      onChatTrace: (tid) => sink?.onChatTrace(tid),
      onConversationId: (cid) => sink?.onConversationId?.(cid),
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
    // A pending fresh-turn belongs to the stream we're tearing down; drop it so a
    // later attach can't open a stray empty bubble.
    pendingInflightTurn = false
  }

  function clearToOff(reason: string | null): void {
    closeSource()
    autoModeOn.set(false)
    armed.set(false)
    setWorking(false)
    reconnecting.set(false)
    retry.set(null)
    runId.set(null)
    offReason.set(reason)
    connection.set("closed")
    sink?.onAutoModeOff(reason)
  }

  // Client-arm on a brand-new conversation (Revision R2): indicator on, no
  // server call. The first sendMessage creates the run and clears this.
  function arm(): void {
    armed.set(true)
  }

  function disarm(): void {
    armed.set(false)
  }

  // Stop observing the current run and clear the indicator WITHOUT signalling the
  // sink (the run keeps going server-side; the user just navigated away — e.g.
  // New Chat / load another conversation). Re-attach is available from history.
  function detach(): void {
    closeSource()
    autoModeOn.set(false)
    armed.set(false)
    setWorking(false)
    reconnecting.set(false)
    retry.set(null)
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
    if (event.type === "kiln-chat-retry") {
      // A transient upstream failure is being retried with backoff. The burst is
      // still working — keep the indicator on and surface "retrying N/M…" so the
      // user sees progress rather than a hard error. Cleared by the next event.
      setWorking(true)
      retry.set({
        attempt: event.attempt ?? 0,
        max: event.max_attempts ?? 0,
      })
      return true
    }
    if (event.type === "auto-mode-idle") {
      // A burst ended but the flag STAYS on (Revision R1). Keep the indicator;
      // only clear the working sub-state so the thinking dots stop. An idle
      // marker on attach also means we're established → clear reconnecting.
      autoModeOn.set(true)
      setWorking(false)
      reconnecting.set(false)
      // No in-flight round produced content (idle on/just-after re-attach) — drop
      // the pending fresh-turn so we don't open an empty bubble.
      pendingInflightTurn = false
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
      // observer — including the sender — sees it, consistent with replay. The
      // echo id lets the sink dedupe a replayed echo (re-attach) against a
      // message it already shows.
      setWorking(true)
      // The echo opens (or dedupes into) its own assistant turn, so the in-flight
      // round renders there — consume any pending fresh-turn to avoid a second.
      pendingInflightTurn = false
      sink?.onUserMessage(event.content ?? "", event.id)
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

  function attach(
    newRunId: string,
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

    // Re-attach (resync / History restore): render the replayed in-flight round
    // into a fresh assistant turn rather than overwriting the last hydrated one.
    // (closeSource above cleared any stale value.) Not set on the initial burst
    // attach, which already opened its turn via requestEnable.
    pendingInflightTurn = openInflightTurn

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
      // Any event other than another retry means the retry window is over (the
      // round recovered, or the burst settled idle/off) — clear the affordance.
      if (event.type !== "kiln-chat-retry") retry.set(null)
      if (handleControlEvent(event)) {
        // A ``user-message`` echo opens a fresh assistant turn (the sink calls
        // beginAssistantTurn). Reset the processor so the prior turn's
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
    // first burst via the /message inject path. A burst starts immediately when
    // the seed carries content to run: the backend-tool path (an
    // ``enable_tool_call_id``) OR a brand-new conversation seeded with the first
    // user message (``extra_messages``, Revision R2). In those cases open a
    // fresh assistant turn to render the runner's first burst.
    const startsBurst =
      !!seed.enable_tool_call_id ||
      (!!seed.pending_tool_calls && seed.pending_tool_calls.length > 0) ||
      (!!seed.extra_messages && seed.extra_messages.length > 0)
    if (startsBurst) {
      // A fresh assistant turn renders the runner's first burst.
      sink?.beginAssistantTurn()
    }
    // A real server run now owns the on-state; clear any client-armed flag
    // (Revision R2: the first send on a brand-new conversation reaches here).
    armed.set(false)
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
      // The optimistic working flag must be cleared on failure: no burst
      // started, so no auto-mode-idle/off event will arrive to clear it and the
      // thinking indicator would stay stuck on.
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
    armed: { subscribe: armed.subscribe },
    working: { subscribe: working.subscribe },
    reconnecting: { subscribe: reconnecting.subscribe },
    retry: { subscribe: retry.subscribe },
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
    arm,
    disarm,
    _close: closeSource,
  }
}

export const auto_run_store: AutoRunStore = createAutoRunStore()
