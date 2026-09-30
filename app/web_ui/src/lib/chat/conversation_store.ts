/**
 * The main conversation store.
 *
 * The assistant's conversation is a desktop-owned run keyed by session id,
 * reached over the `/api/conversations` surface. ONE pure-observer attachment
 * to the conversation's events stream feeds the `StreamEventProcessor`, for
 * both kinds: an interactive conversation and an auto conversation are the
 * same record, whose policy flips on enable/disable. This store owns:
 *
 * - create-or-adopt (`ensure`) and attach/detach of the observer,
 * - the auto-mode lifecycle (enable / decline / stop / arm) and its UX states
 *   (indicator, "waiting for you", consent and stop dialogs),
 * - sends (`POST /{sid}/messages`, returning the echo-dedupe message id),
 * - approvals (`fetchApprovals` + `decide` against the parked batch).
 *
 * Opening or closing the stream never mutates the run. The authoritative
 * lifecycle state comes from `conversation-state` events, so it is correct on
 * first paint after a re-attach, not only after a local action.
 */

import { get, writable, type Readable } from "svelte/store"
import { base_url } from "$lib/api_client"
import type { components } from "$lib/api_schema"
import {
  StreamEventProcessor,
  autoModeConsentPayloadFromEvent,
  type AutoModeConsentRequiredPayload,
  type ChatMessage,
  type ContextUsage,
  type StreamEvent,
  type ToolCallsPendingItem,
} from "./streaming_chat"

export type CreateAutoConversationRequest =
  components["schemas"]["CreateConversationRequest"]

const CONVERSATIONS_BASE_URL = `${base_url}/api/conversations`

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
  /** The ``enable_auto_mode`` call to resolve as ``{"status": "declined"}``. */
  gating_tool_call_id: string
  siblings: ToolCallsPendingItem[]
}

/**
 * Callbacks the chat session store registers so the desktop-owned
 * conversation drives the transcript: stream content, turn lifecycle and the
 * auto on/off signals.
 */
export interface MainConversationSink {
  /** Begin a fresh assistant turn (append an empty assistant message). */
  beginAssistantTurn: () => void
  onAssistantMessage: (update: (draft: ChatMessage) => void) => void
  /**
   * A turn's snapshot persisted upstream (the `kiln_chat_trace` event).
   * Deliberately carries NO trace id: the browser never keys on one. The
   * session store uses this as the moment to learn the conversation's
   * durable `root_id` (one item fetch) for its restart-recovery key.
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
   * The run echoed a user message (an own send or a second tab's send);
   * ``echoId`` lets the sink dedupe its own just-sent message and buffer
   * replays.
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
   * An INTERACTIVE turn settled (idle transition with the flag off): status
   * goes to ready and the queued message flushes. Deliberately carries NO
   * reason: the engine records the auto idle vocabulary on interactive
   * records too, and interactive conversations never render `idle_reason`.
   */
  onInteractiveIdle: () => void
  /**
   * The idle ATTACH MARKER of a genuinely-idle conversation. Distinct from
   * ``onInteractiveIdle`` (a real settle): markers stay settle-SILENT, but
   * the LIVE idle ``conversation-state`` event is published live-only and
   * can be MISSED when the observer is momentarily detached at the instant
   * the turn settles. On (re)subscribe the bus delivers an idle marker
   * instead, and a CLIENT-HELD queued message would then wait forever for a
   * settle hook that never comes. So this hook does a queued-message FLUSH
   * ONLY: the session store wires it to ``maybeFlush``, which is a safe no-op
   * without a queue or while a turn is active. Optional so other sink
   * consumers need not implement it.
   */
  onIdleMarker?: () => void
  /**
   * The run parked on a pending approval batch (state awaiting_approval,
   * marker or live). The session store fetches the batch and opens the
   * approval box.
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
   * the turn after emitting it): drive the consent dialog.
   */
  onConsentRequired: (payload: AutoModeConsentRequiredPayload) => void
  /** ``kiln_client_upgrade_nudge`` — the non-blocking upgrade banner. */
  onVersionNudge: (preferredVersion: string) => void
}

export interface MainConversationStore {
  /** Conversation auto-mode flag: ON across RUNNING and IDLE bursts. */
  autoModeOn: Readable<boolean>
  /**
   * Client-only "armed" flag: auto mode turned on for a brand-new
   * conversation with no server record yet. Indicator on, NO server call;
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
   * Create-or-adopt the conversation for the given conversation KEY (a
   * session id, a history row id, or null for a brand-new conversation) and
   * attach the observer. The desktop resolves the key. Idempotent while
   * attached.
   */
  ensure(
    sessionKey: string | null,
    opts?: {
      openInflightTurn?: boolean
      initialWorking?: boolean
      /** Reflect the auto indicator immediately (history auto-row restore)
       * instead of waiting for the marker. */
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
  /**
   * Stop the run (POST /{sid}/stop): cancels the in-flight turn, and turns
   * auto mode off when it is on.
   */
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
  /** Client-arm auto mode on a brand-new conversation. */
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
  // conversation is not a settle.
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
  // Bounded re-attach after an observer drop while the conversation
  // still matters (auto mode on, or a turn was in flight). One backoff entry
  // per attempt; the timer is cancelled by closeSource (detach / a manual
  // re-attach) and the budget resets once a stream DELIVERS an event again
  // (not merely opens — a flapping stream that opens then drops before any
  // byte still burns the budget). The budget is strictly per-stream: a
  // direct attach() starts fresh; only the scheduled re-attach below carries
  // spent attempts forward (reattachInProgress).
  const REATTACH_BACKOFF_MS: readonly number[] = [2000, 5000, 10000]
  let reattachTimer: ReturnType<typeof setTimeout> | null = null
  let reattachAttempt = 0
  let reattachInProgress = false

  function clearReattachTimer(): void {
    if (reattachTimer !== null) {
      clearTimeout(reattachTimer)
      reattachTimer = null
    }
  }

  // Schedule the next bounded re-attach, or — attempts exhausted — degrade
  // to the manual-recovery paths (the next send/ensure re-attaches; a
  // refresh resyncs). Auto state is deliberately NOT touched anywhere on
  // this path: the desktop-owned run is unaffected by observer connection
  // loss, so faking an off-transition would lie. The real off, if one
  // happened while disconnected, arrives via the re-attach marker.
  function scheduleReattach(sid: string): void {
    if (reattachAttempt >= REATTACH_BACKOFF_MS.length) {
      reattachAttempt = 0
      reconnecting.set(false)
      sink?.onInlineError(
        "Lost the connection to the assistant. Please try again.",
      )
      return
    }
    reconnecting.set(true)
    const delay = REATTACH_BACKOFF_MS[reattachAttempt]
    reattachAttempt += 1
    reattachTimer = setTimeout(() => {
      reattachTimer = null
      // Carry the spent-attempt count through this attach — the budget only
      // resets on a direct attach or once the stream delivers an event.
      reattachInProgress = true
      try {
        attach(sid, undefined, false, get(autoModeOn))
      } finally {
        reattachInProgress = false
      }
    }, delay)
  }

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
      // The upstream event's trace id is DROPPED at this boundary: the sink
      // only learns "a turn persisted". Browser code never keys on trace ids.
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
    // down, and so does any scheduled re-attach (a manual attach or a detach
    // supersedes it; the timer's own attach re-enters here with the timer
    // already null).
    clearReattachTimer()
    pendingInflightTurn = false
    attachMarkerPending = false
  }

  // The on→off TRANSITION (user stop / user disable): clear the auto
  // affordances and signal the sink ONCE. This NEVER closes the stream or
  // clears the session id: an off-auto conversation IS the same live
  // interactive conversation, and the observer keeps carrying its turns.
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

  // Client-arm on a brand-new conversation: indicator on, no server call.
  // The first sendMessage creates the conversation.
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
    reattachAttempt = 0
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
  // event:
  //
  //   state=running, auto_flag=true     → auto burst running
  //   state=idle, auto_flag=true        → burst settled, auto stays on
  //   auto_flag true → false            → off TRANSITION (idle_reason carries
  //                                       user_stopped/user_disabled)
  //   first event after attach          → the on-subscribe marker
  //   state=idle, auto_flag=false       → interactive turn settled
  //                                       → onInteractiveIdle
  //   state=awaiting_approval           → approvals fetch (with the replayed
  //                                       tool-calls-pending event)
  //   auto-mode-consent-required        → consent dialog
  function handleControlEvent(event: StreamEvent): boolean {
    if (event.type === "conversation-state") {
      const isAttachMarker = attachMarkerPending
      attachMarkerPending = false
      // Any state event means the attach is established.
      reconnecting.set(false)
      if (event.session_id) sessionId.set(event.session_id)

      const flagOn = event.auto_flag === true
      // A true on→off TRANSITION, including one arriving as the marker of a
      // freshly re-attached OFF record.
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
        // An auto burst, or for the interactive kind a turn in flight.
        setWorking(true)
      } else if (event.state === "awaiting_approval") {
        // The run parked on approvals. The thinking affordance stops; the
        // approval box re-surfaces via the sink's idempotent approvals
        // fetch, marker included, so a refreshed tab recovers the box.
        setWorking(false)
        pendingInflightTurn = false
        sink?.onAwaitingApproval()
      } else {
        // idle
        setWorking(false)
        pendingInflightTurn = false
        // Exactly ONE settle signal per settle: an off transition already
        // signalled onAutoModeOff above, markers signal nothing.
        if (!isAttachMarker && !offTransition) {
          if (flagOn) {
            // Burst settled, flag stays on: flushes queued messages in the
            // session store.
            sink?.onAutoModeIdle(event.idle_reason ?? null)
          } else {
            // Interactive turn settled. idle_reason is deliberately not
            // forwarded (interactive conversations never render it).
            sink?.onInteractiveIdle()
          }
        } else if (isAttachMarker && !offTransition) {
          // A genuinely-idle conversation whose LIVE idle event was missed
          // (the observer was detached/reconnecting at the settle instant)
          // arrives only as this on-subscribe marker. The marker stays
          // settle-silent above, so a CLIENT-HELD queued message would
          // strand, flag-off and flag-on alike. Fire the flush-only hook to
          // unstick it, WITHOUT the full settle semantics. Safe:
          // onIdleMarker → maybeFlush no-ops without a queue, flushing on
          // auto idle is already the designed live behavior, and
          // dispatchQueued clears before sending, so a real live idle racing
          // this marker can never double-send. Excludes off transitions
          // (onAutoModeOff already cleared the queue there).
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
      // approval batch. The box opens off the fetched batch while the run
      // stays parked.
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
    // The re-attach budget is strictly per-stream: a direct attach (new
    // conversation, manual re-attach, resync) starts a fresh budget. The
    // scheduled re-attach is the one exception: it carries its spent
    // attempts through (reattachInProgress).
    if (!reattachInProgress) reattachAttempt = 0

    pendingInflightTurn = openInflightTurn
    attachMarkerPending = true
    flagSeenOn = assumeAutoOn

    sessionId.set(newSessionId)
    if (assumeAutoOn) {
      // Enable / auto-row restore: reflect the on-state immediately; the
      // marker corrects it if stale. Plain interactive attaches wait for the
      // marker instead.
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
      // Deliberately NOT resetting the re-attach budget here: a flapping stream
      // that opens then drops before delivering anything must still burn
      // attempts. The first delivered event (onmessage) resets it.
    }

    source.onmessage = (e: MessageEvent) => {
      if (eventSource !== source) return
      // First byte over the stream means we're truly established: clear the
      // affordance and start a fresh re-attach budget.
      reconnecting.set(false)
      reattachAttempt = 0
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
      // An observer drop is a CONNECTION fact, never a run fact: the
      // desktop-owned run keeps going, so autoModeOn/armed/offReason stay
      // exactly as they are (no fake off-transition; a real off that
      // happened while disconnected arrives via the re-attach marker).
      const droppedMidTurn = get(working)
      closeSource()
      // setWorking(false) doubles as the session store's status reset (it
      // clears a stuck "submitted"/"streaming" without flushing the queue).
      // The client-held queued message survives by construction: no
      // onAutoModeOff fires here.
      setWorking(false)
      connection.set("closed")
      const sid = get(sessionId)
      // reattachAttempt > 0 means a scheduled re-attach chain is mid-flight (an
      // earlier drop mattered and no onmessage/direct attach has settled it
      // since — a scheduled re-attach resets `working`, so droppedMidTurn
      // alone would end an interactive chain after ONE attempt, silently).
      if (sid && (get(autoModeOn) || droppedMidTurn || reattachAttempt > 0)) {
        // The connection still matters (auto run, a turn was visibly in
        // flight, or an unsettled re-attach chain): bounded re-attach with
        // the reconnecting affordance; on exhaustion scheduleReattach
        // surfaces the inline error and the manual paths (next send/ensure)
        // remain the recovery.
        scheduleReattach(sid)
      } else {
        // Idle interactive drop: no request was in flight, so stay silent;
        // the next send/ensure re-attaches.
        reconnecting.set(false)
      }
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
    // POST /api/conversations: flips the SAME conversation record to the
    // auto policy (or creates one for the armed-first-send path).
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
    // client-armed flag.
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
    // Decline resolves enable→declined server-side (POST /{sid}/auto) and
    // streams the interactive continuation on the observer; open a fresh
    // turn for it.
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
    // The resumed execution streams on the observer into the CURRENT turn
    // (the tool outputs belong to the assistant message the pending round
    // left behind), so no beginTurn here.
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
      // resolution either way.
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
    let response: Response
    try {
      response = await fetch(
        `${CONVERSATIONS_BASE_URL}/${encodeURIComponent(id)}/stop`,
        {
          method: "POST",
        },
      )
    } catch {
      /* idempotent; the run keeps going and the user can retry */
      return
    }
    // Stop while "connection lost" (stream closed, no re-attach
    // pending): nothing would ever deliver the resulting off/idle event, so
    // the transition wouldn't render. One-shot re-attach — the on-subscribe
    // marker carries the authoritative state (flag-off arrives as a marker
    // off-transition via flagSeenOn = assumeAutoOn).
    if (
      response.ok &&
      get(connection) === "closed" &&
      reattachTimer === null &&
      get(sessionId) === id
    ) {
      attach(id, false, false, get(autoModeOn))
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
