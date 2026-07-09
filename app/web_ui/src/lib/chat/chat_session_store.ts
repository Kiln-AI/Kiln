/**
 * UI-session state for the MAIN conversation (architecture §7).
 *
 * Phase 4 shrank this store to exactly the concerns the browser owns:
 * which conversation is the main one, the composer / queued-message UX, the
 * consent-dialog and approval-box state, history hydration, and the version
 * banners. ALL streaming is delegated to `conversation_store.ts`'s
 * `main_conversation_store` — the main conversation is a desktop-owned run
 * observed over `/api/conversations` like any other, and this store merely
 * renders what the observer sink reports (the old `streamChat` /
 * `resumePendingToolCalls` request-driving machinery is gone).
 *
 * sessionStorage persists ONLY `{sessionId, traceId, ui prefs}` — the
 * transcript ALWAYS rebuilds from hydrate+observe (functional spec §7 /
 * architecture §7: this removes the persisted message-cache divergence
 * class). `traceId` is the hydration key until phases 5/6 key everything on
 * session ids (it also recovers the conversation across a desktop restart,
 * where the in-memory session id dies but the trace survives upstream).
 */

import { writable, get, type Readable } from "svelte/store"
import posthog from "posthog-js"
import {
  chatGenerateId,
  traceIdForNextChatRequest,
  type ChatMessage,
  type ContextUsage,
  type ToolCallsPendingItem,
  type ToolCallsPendingPayload,
  type AutoModeConsentRequiredPayload,
} from "./streaming_chat"
import {
  main_conversation_store,
  type MainConversationStore,
  type CreateAutoConversationRequest,
  type DeclineAutoModeContext,
} from "./conversation_store"
import { sessionStorageStore } from "$lib/stores/local_storage_store"
import {
  hydrateSessionFromSnapshot,
  stripInternalFraming,
  userChatMessageFromContent,
} from "./session_messages"
import { base_url, client } from "$lib/api_client"
import {
  getCurrentAppState,
  buildContextHeader,
  type AppState,
} from "$lib/agent"
import { chat_cost_disclaimer_acknowledged } from "$lib/stores"
import { CHAT_CLIENT_VERSION_TOO_OLD } from "$lib/error_codes"

const SESSION_STORAGE_KEY = "kiln_chat_session"

/**
 * The sessionStorage shape (functional spec §7): the conversation HANDLES
 * plus ui prefs — never messages. `lastSentAppState` rides along so the
 * app-context header's delta encoding stays stable across a refresh.
 */
export interface PersistedChatSession {
  /** The main conversation's supervisor session id (in-memory server-side —
   * dies with a desktop restart; `traceId` is the durable fallback). */
  sessionId: string | null
  /** The conversation's last known leaf trace id (the hydration key until
   * phase 5/6). */
  traceId: string | null
  collapsedPartKeys: Record<string, boolean>
  lastSentAppState: AppState | null
}

export interface ToolApprovalWaiter {
  payload: ToolCallsPendingPayload
}

export interface ChatSessionState extends PersistedChatSession {
  messages: ChatMessage[]
  /**
   * Approximate context-window usage for the gauge (runtime-only now —
   * rebuilt from the snapshot on hydrate; `null` before the first turn).
   */
  contextUsage: ContextUsage | null
  status: "ready" | "submitted" | "streaming"
  toolApprovalWaiter: ToolApprovalWaiter | null
  toolApprovalPicks: Record<string, boolean | undefined>
  toolExecuting: boolean
  showActivityIndicator: boolean
  /**
   * The server is summarizing earlier messages (compaction) for this turn.
   * Runtime-only — set by ``kiln_compaction_status`` and cleared on the
   * first content event / turn end / reset.
   */
  compacting: boolean
  /**
   * A server-owned auto-mode burst is actively running. Decoupled from
   * ``status`` (which tracks interactive turns) so the chat view can drive
   * the SAME loading affordances during auto bursts while keeping the input
   * usable for inject-on-send.
   */
  autoWorking: boolean
  /**
   * A transient upstream failure is being retried with backoff during an
   * interactive turn (``kiln-chat-retry``): ``{ attempt, max }`` while
   * retrying, else null. (Auto bursts surface the same affordance via the
   * main conversation store's own `retry`.) Runtime-only.
   */
  retry: { attempt: number; max: number } | null
  /**
   * Preferred version from a server upgrade nudge (non-blocking), or null when
   * no nudge is active or the user dismissed it. Runtime-only, not persisted.
   */
  upgradeNudgeVersion: string | null
  /**
   * True when the server rejected the request because the client is below the
   * required minimum version (HTTP 426 / its error event). Surfaced as a
   * blocking banner above the composer. Runtime-only.
   */
  versionRequired: boolean
  /**
   * A user message typed while a turn was in flight (interactive turn or auto
   * burst), held client-side until the turn yields — then auto-sent — or sent
   * immediately via send-now. ``null`` when nothing is queued. A second send
   * while one is queued appends to it. Runtime-only, not persisted.
   *
   * Deliberately CLIENT-side (not the server inbox) for the primary tab:
   * dispatching mid-turn would inject the message into the SAME turn's
   * continuation — a persisted-trace change the old world never made — and
   * would lose the edit/discard affordances. The server inbox still accepts
   * mid-turn sends from other tabs (functional spec §2).
   */
  queuedMessage: string | null
}

/**
 * Asked of the UI when the model requests auto mode. Returns ``true`` to enable
 * (accept) or ``false`` to decline; the store then drives the conversation store.
 */
export type AutoModeConsentDecision = (
  payload: AutoModeConsentRequiredPayload,
) => Promise<boolean>

export interface ChatSessionStore extends Readable<ChatSessionState> {
  sendMessage(text: string): Promise<boolean>
  /**
   * Send the currently queued message right now instead of waiting for the
   * in-flight turn to end. Interactive: stops the turn (it then auto-sends on
   * the ready transition). Auto mode: injects immediately, keeping auto mode
   * running (the run picks it up at the next round boundary). No-op when
   * nothing is queued.
   */
  sendQueuedNow(): void
  /** Discard the queued message without sending it. */
  clearQueued(): void
  stop(): void
  retryLastRequest(): void
  reset(): void
  loadSession(
    messages: ChatMessage[],
    continuationTraceId: string,
    contextUsage?: ContextUsage | null,
    opts?: {
      /** From the history row's sessions-list join: reflect the auto
       * indicator immediately on re-attach (the old attach's behavior)
       * instead of waiting for the observer's state marker. */
      autoActive?: boolean
    },
  ): void
  /**
   * Reconnect the conversation after a hard refresh: sessionStorage holds
   * only the handles now, so hydrate the transcript from the persisted
   * snapshot and re-attach the observer (in-flight turns and pending
   * approvals converge via replay + the state marker — functional spec §5).
   * No-op when nothing is stored. Idempotent / safe to call on every load.
   */
  resyncOnLoad(): Promise<void>
  togglePartCollapsed(key: string, currentlyCollapsed: boolean): void
  /** Surface an inline chat error (e.g. a failed manual auto-mode enable). */
  pushInlineError(message: string): void
  applyToolApprovalRun(toolCallId: string): void
  applyToolApprovalSkip(toolCallId: string): void
  dismissUpgradeNudge(): void
  /** Fetch the server's version verdict and set the banner state up front. */
  checkVersionPolicy(): Promise<void>
  onConsentNeeded: (() => Promise<boolean>) | null
  onAutoModeConsentNeeded: AutoModeConsentDecision | null
}

const EMPTY_PERSISTED: PersistedChatSession = {
  sessionId: null,
  traceId: null,
  collapsedPartKeys: {},
  lastSentAppState: null,
}

export function createChatSessionStore(
  sessionStorageKey?: string,
  // The main conversation store (conversation_store.ts); injectable for
  // tests exactly like the old auto store was.
  conversationStore: MainConversationStore = main_conversation_store,
): ChatSessionStore {
  const persisted = sessionStorageKey
    ? sessionStorageStore<PersistedChatSession>(sessionStorageKey, {
        ...EMPTY_PERSISTED,
      })
    : writable<PersistedChatSession>({ ...EMPTY_PERSISTED })

  let status: ChatSessionState["status"] = "ready"
  // Synchronous in-flight guard for the armed-first-send enable (a second
  // Enter during the requestEnable round-trip must not fire a second enable).
  let armedEnablePending = false
  // A consent dialog (accept/decline flow) is resolving: the turn is not
  // over yet — queued sends hold, flushes wait (the old await-inside-the-
  // stream ordering, preserved).
  let consentFlowPending = false
  // The open approval box's batch id (decisions must echo it back).
  let approvalBatchId: string | null = null
  // Own-echo dedupe (phase 4): content the user just sent from THIS tab —
  // rendered locally at send time — matched against the run's user-message
  // echo (by server message id when the 202 already returned, by stripped
  // content otherwise) so it isn't appended twice. The echoed content
  // carries the app-context header; other observers render it stripped.
  const pendingOwnEchoes: { id?: string; content: string; localId: string }[] =
    []
  let generation = 0

  const combined = writable<ChatSessionState>({
    ...get(persisted),
    messages: [],
    contextUsage: null,
    status,
    toolApprovalWaiter: null,
    toolApprovalPicks: {},
    toolExecuting: false,
    showActivityIndicator: false,
    compacting: false,
    autoWorking: false,
    retry: null,
    upgradeNudgeVersion: null,
    versionRequired: false,
    queuedMessage: null,
  })

  // Intentionally never unsubscribed — this store is a module-level singleton
  // that lives for the lifetime of the app.
  persisted.subscribe(($persisted) => {
    combined.update((s) => ({
      ...s,
      sessionId: $persisted.sessionId,
      traceId: $persisted.traceId,
      collapsedPartKeys: $persisted.collapsedPartKeys,
      lastSentAppState: $persisted.lastSentAppState,
    }))
  })

  function setStatus(newStatus: ChatSessionState["status"]) {
    status = newStatus
    combined.update((s) => ({ ...s, status }))
  }

  function updateMessages(updater: (messages: ChatMessage[]) => ChatMessage[]) {
    combined.update((s) => ({ ...s, messages: updater(s.messages) }))
  }

  function updateLastAssistant(update: (draft: ChatMessage) => void) {
    combined.update((s) => {
      const msgs = s.messages
      const last = msgs[msgs.length - 1]
      if (last?.role === "assistant") {
        const draft = { ...last, parts: last.parts ? [...last.parts] : [] }
        update(draft)
        return { ...s, messages: [...msgs.slice(0, -1), draft] }
      }
      return s
    })
  }

  function removeErrors() {
    combined.update((s) => ({
      ...s,
      messages: s.messages.filter((m) => m.role !== "error"),
    }))
  }

  // Append an inline error message — the single error-surfacing mechanism
  // shared by the observer stream and the enable-failure paths.
  function pushInlineError(
    message: string,
    traceId?: string,
    code?: string,
  ): void {
    const errorMsg: ChatMessage = {
      id: chatGenerateId(),
      role: "error",
      content: message,
      traceId,
      errorCode: code,
    }
    updateMessages((msgs) => [...msgs, errorMsg])
  }

  function setLastAssistantTraceId(traceId: string) {
    combined.update((s) => {
      const msgs = s.messages
      const last = msgs[msgs.length - 1]
      if (last?.role === "assistant") {
        return {
          ...s,
          messages: [...msgs.slice(0, -1), { ...last, traceId }],
        }
      }
      return s
    })
    // Track the conversation's leaf for hydration/recovery (phase 5 keys
    // everything on session ids and drops this).
    persisted.update((p) => ({ ...p, traceId }))
  }

  function setContextUsage(usage: ContextUsage) {
    combined.update((s) => ({ ...s, contextUsage: usage }))
  }

  function setCompacting(compacting: boolean) {
    combined.update((s) => ({ ...s, compacting }))
  }

  // Append a fresh empty assistant message so the next streamed burst renders
  // into a new turn rather than the prior one.
  function beginAssistantTurn() {
    removeErrors()
    updateMessages((msgs) => [
      ...msgs,
      { id: chatGenerateId(), role: "assistant", parts: [] },
    ])
    combined.update((s) => ({
      ...s,
      toolExecuting: false,
      showActivityIndicator: false,
      compacting: false,
    }))
  }

  // Append an echoed user message, then a fresh assistant turn so the burst it
  // triggers renders into a new turn. Idempotent by echo id (buffer replays on
  // re-attach re-emit echoes the transcript already shows).
  function appendEchoedUserMessage(content: string, echoId?: string) {
    if (echoId && get(combined).messages.some((m) => m.echoId === echoId)) {
      return
    }
    removeErrors()
    // Reports arrive framed; other tabs' sends carry the app-context header —
    // strip internal framing for display, exactly like hydration does.
    updateMessages((msgs) => [
      ...msgs,
      userChatMessageFromContent(stripInternalFraming(content), echoId),
    ])
    beginAssistantTurn()
  }

  // The run echoed a user message. Three cases:
  // - our own just-sent message (rendered locally already): attach the echo
  //   id to the local bubble and skip the append;
  // - an echo id the transcript already shows (replay): skip;
  // - anything else (another tab's send, an injected report): render it.
  function handleUserMessageEcho(content: string, echoId?: string) {
    const stripped = stripInternalFraming(content)
    const ownIdx = pendingOwnEchoes.findIndex(
      (e) => (echoId && e.id === echoId) || e.content === stripped,
    )
    if (ownIdx >= 0) {
      const own = pendingOwnEchoes.splice(ownIdx, 1)[0]
      if (echoId) {
        updateMessages((msgs) =>
          msgs.map((m) => (m.id === own.localId ? { ...m, echoId } : m)),
        )
      }
      return
    }
    appendEchoedUserMessage(content, echoId)
  }

  // ── Approval box (phase 4: parked batches) ─────────────────────────────────
  //
  // The run PARKS on gated tool calls (AWAITING_APPROVAL) instead of ending
  // the stream; the box opens off the fetched batch and decisions resolve it.
  // Keyed off both the `tool-calls-pending` event (also replayed to
  // re-attaching tabs while parked) and the awaiting_approval state marker —
  // idempotent by batch id, so refresh recovery and live parks share one path.
  async function openApprovalBox(): Promise<void> {
    const batch = await conversationStore.fetchApprovals()
    if (!batch) return // already resolved (e.g. another tab decided)
    if (approvalBatchId === batch.batchId && get(combined).toolApprovalWaiter) {
      return
    }
    const approvalOnly = batch.items.filter((i) => i.requiresApproval)
    if (approvalOnly.length === 0) {
      // Nothing needs a human decision (defensive — the engine only parks
      // when something does): unpark with an empty decision set.
      approvalBatchId = null
      void conversationStore.decide(batch.batchId, {})
      return
    }
    approvalBatchId = batch.batchId
    const picks: Record<string, boolean | undefined> = {}
    for (const it of approvalOnly) {
      picks[it.toolCallId] = undefined
    }
    combined.update((s) => ({
      ...s,
      toolApprovalWaiter: { payload: { items: approvalOnly } },
      toolApprovalPicks: picks,
    }))
  }

  function clearToolApprovalState(): void {
    approvalBatchId = null
    combined.update((s) => ({
      ...s,
      toolApprovalWaiter: null,
      toolApprovalPicks: {},
    }))
  }

  function maybeFinishToolApproval(): void {
    const state = get(combined)
    if (!state.toolApprovalWaiter || !approvalBatchId) return
    const allDone = state.toolApprovalWaiter.payload.items.every(
      (it) => state.toolApprovalPicks[it.toolCallId] !== undefined,
    )
    if (!allDone) return
    const decisions: Record<string, boolean> = {}
    for (const it of state.toolApprovalWaiter.payload.items) {
      decisions[it.toolCallId] = state.toolApprovalPicks[it.toolCallId] ?? false
    }
    const batchId = approvalBatchId
    clearToolApprovalState()
    void conversationStore.decide(batchId, decisions).then((result) => {
      // conflict = another tab decided first; the stream carries the
      // resolution either way (functional spec §5) — stay quiet.
      if (!result.ok && !result.conflict) {
        pushInlineError(
          `Couldn't submit the tool decisions: ${result.error ?? "unknown error"}`,
        )
      }
    })
  }

  // ── Observer sink: the desktop-owned run drives this conversation ──────────

  conversationStore.bind({
    beginAssistantTurn,
    onAssistantMessage: (update) => {
      // First assistant content of an interactive turn: submitted → streaming
      // (the same transition the old streamChat drove).
      if (status === "submitted") setStatus("streaming")
      updateLastAssistant(update)
    },
    onChatTrace: setLastAssistantTraceId,
    onContextUsage: setContextUsage,
    onCompactionStatus: setCompacting,
    onInlineError: (message, traceId, code) => {
      // Blocking "client too old" rejection: banner above the composer, not a
      // conversation message (the upstream 426 arrives as an error event on
      // the observer now that the engine owns the POST).
      if (code === CHAT_CLIENT_VERSION_TOO_OLD) {
        combined.update((s) => ({ ...s, versionRequired: true }))
        setStatus("ready")
        return
      }
      pushInlineError(message, traceId, code)
    },
    onVersionNudge: (preferredVersion) => {
      // Set unconditionally: repeated nudges collapse to a single banner, and
      // a new server preference re-surfaces it even if dismissed.
      combined.update((s) => ({ ...s, upgradeNudgeVersion: preferredVersion }))
    },
    onToolExecutionStart: () =>
      combined.update((s) => ({ ...s, toolExecuting: true })),
    onToolExecutionEnd: () => {
      combined.update((s) => ({ ...s, toolExecuting: false }))
      // Round boundary: flush a queued message so it rides the next request
      // (auto mode injects at boundaries; interactive turns stay guarded by
      // interactiveTurnActive).
      maybeFlush()
    },
    onShowActivityIndicator: (show) =>
      combined.update((s) => ({ ...s, showActivityIndicator: show })),
    onWorkingChange: (working) => {
      const autoOn = get(conversationStore.autoModeOn)
      combined.update((s) => ({ ...s, autoWorking: autoOn && working }))
      if (!autoOn) {
        if (working) {
          // A turn is in flight (a send from this tab, another tab, or a
          // resumed approval batch). If the approval box is open, the batch
          // was just decided (possibly by another tab) — clear it.
          if (get(combined).toolApprovalWaiter) clearToolApprovalState()
          if (status === "ready") setStatus("submitted")
        } else if (status !== "ready") {
          // Authoritative not-working signal WITHOUT a settle hook: the
          // on-subscribe marker of an idle/parked conversation, an approval
          // park, a consent event, an observer error, or a failed dispatch.
          // Reset the composer to ready — but deliberately do NOT flush the
          // queued message here: flushing is the settle hooks' job
          // (onInteractiveIdle / onAutoModeIdle), and a marker is not a
          // settle. Without this reset, re-attaching to a conversation
          // whose last turn ended in a terminal upstream error (no trace
          // persisted) bricks the composer: the buffered user-message echo
          // replays, marks the turn working, and no settle event ever
          // follows (markers are silent by design).
          setStatus("ready")
          combined.update((s) => ({
            ...s,
            toolExecuting: false,
            showActivityIndicator: false,
            compacting: false,
          }))
        }
      }
    },
    onUserMessage: handleUserMessageEcho,
    // NOTE: retry ("retrying N/M…") is not mirrored here — the main
    // conversation store's own `retry` readable carries it for both kinds
    // (chat.svelte reads it first), so this store's `retry` field stays null.
    // A burst ended but auto mode stays on: stop the working affordances; the
    // green indicator persists (it binds to autoModeOn).
    onAutoModeIdle: () => {
      combined.update((s) => ({
        ...s,
        toolExecuting: false,
        showActivityIndicator: false,
        compacting: false,
        autoWorking: false,
      }))
      maybeFlush()
    },
    // Auto mode turned off — drop any pending queued message (stopping clears
    // the queue; the user can re-send if they still want it).
    onAutoModeOff: () =>
      combined.update((s) => ({
        ...s,
        toolExecuting: false,
        showActivityIndicator: false,
        compacting: false,
        autoWorking: false,
        queuedMessage: null,
      })),
    // An interactive turn settled — the old streamChat onFinish moment.
    // Deliberately reasonless: idle_reason must never render for interactive
    // conversations (the phase-1 rendering rule).
    onInteractiveIdle: () => {
      combined.update((s) => ({
        ...s,
        toolExecuting: false,
        showActivityIndicator: false,
        compacting: false,
        retry: null,
      }))
      setStatus("ready")
      maybeFlush()
    },
    onAwaitingApproval: () => {
      // The run parked. The old stream ended here (status went ready with the
      // box open); the observer stays attached.
      setStatus("ready")
      combined.update((s) => ({
        ...s,
        toolExecuting: false,
        showActivityIndicator: false,
        compacting: false,
      }))
      void openApprovalBox()
    },
    onToolCallsPending: () => {
      void openApprovalBox()
    },
    onConsentRequired: (payload) => {
      void handleAutoModeConsent(payload)
    },
  })

  let onConsentNeeded: (() => Promise<boolean>) | null = null
  let onAutoModeConsentNeeded: AutoModeConsentDecision | null = null

  // The model called enable_auto_mode (the consent control event arrived on
  // the observer; the turn is over server-side). Ask the UI; accept flips the
  // SAME conversation to auto mode, decline resumes interactively with the
  // enable call resolved as declined.
  async function handleAutoModeConsent(
    payload: AutoModeConsentRequiredPayload,
  ): Promise<void> {
    consentFlowPending = true
    try {
      const traceId = payload.traceId ?? get(persisted).traceId
      // If auto mode is already on/armed — the user turned it on themselves
      // while the model's enable call was streaming — accept silently.
      const alreadyOn =
        get(conversationStore.autoModeOn) || get(conversationStore.armed)
      const accepted = alreadyOn
        ? true
        : onAutoModeConsentNeeded
          ? await onAutoModeConsentNeeded(payload)
          : false
      const siblings = payload.siblingToolCalls.map((s) => ({
        toolCallId: s.toolCallId,
        toolName: s.toolName,
        input:
          s.input && typeof s.input === "object" && !Array.isArray(s.input)
            ? (s.input as Record<string, unknown>)
            : {},
        requiresApproval: Boolean(s.requiresApproval),
      }))
      if (accepted) {
        const seed: CreateAutoConversationRequest = {
          kind: "auto",
          trace_id: traceId ?? undefined,
          enable_tool_call_id: payload.enableToolCallId,
          pending_tool_calls: siblings,
          reason: payload.reason,
        }
        // Surface enable failures (e.g. 429 "Too many auto runs") — the
        // dialog has already closed, so the inline error is the only signal.
        const result = await conversationStore.requestEnable(seed)
        if (!result.ok) {
          pushInlineError(
            `Couldn't start auto mode: ${result.error ?? "unknown error"}`,
          )
        }
      } else {
        const ctx: DeclineAutoModeContext = {
          enable_tool_call_id: payload.enableToolCallId,
          siblings,
        }
        await conversationStore.decline(ctx)
      }
    } finally {
      consentFlowPending = false
      maybeFlush()
    }
  }

  // An interactive turn is "in flight" — sending should queue rather than
  // dispatch — while the observer reports a turn, a tool approval is open, or
  // a consent flow is resolving. Auto mode is intentionally NOT consulted:
  // messages sent during an auto burst inject at the next round boundary.
  function interactiveTurnActive(): boolean {
    if (status !== "ready") return true
    if (get(combined).toolApprovalWaiter) return true
    if (consentFlowPending) return true
    return false
  }

  // Hold a message client-side while a turn is in flight. A second send while
  // one is queued appends (blank line between) so the coalesced text sends as
  // one.
  function enqueue(text: string): void {
    combined.update((s) => ({
      ...s,
      queuedMessage: s.queuedMessage ? `${s.queuedMessage}\n\n${text}` : text,
    }))
  }

  function clearQueued(): void {
    combined.update((s) => ({ ...s, queuedMessage: null }))
  }

  // Dispatch a queued message: clear it, then send. If the send is rejected,
  // restore it to the FRONT of whatever has queued since, so a failed/declined
  // send never silently drops the user's typed text.
  async function dispatchQueued(queued: string): Promise<void> {
    clearQueued()
    const sent = await actuallySend(queued)
    if (!sent) {
      combined.update((s) => ({
        ...s,
        queuedMessage: s.queuedMessage
          ? `${queued}\n\n${s.queuedMessage}`
          : queued,
      }))
    }
  }

  // Auto-send the queued message at the next safe point: an interactive turn
  // finishing, or — in auto mode — a round boundary / the burst going idle.
  function maybeFlush(): void {
    const queued = get(combined).queuedMessage
    if (!queued) return
    if (interactiveTurnActive()) return
    if (get(combined).versionRequired) return
    void dispatchQueued(queued)
  }

  // Send the queued message right away instead of waiting for the turn to end.
  function sendQueuedNow(): void {
    const queued = get(combined).queuedMessage
    if (!queued) return
    if (get(combined).versionRequired) return
    // Auto mode: inject immediately and keep auto mode running — the run picks
    // the message up at its next round boundary.
    if (get(conversationStore.autoModeOn) || get(conversationStore.armed)) {
      void dispatchQueued(queued)
      return
    }
    // Interactive turn in flight: stop it. The resulting idle transition
    // flushes the queued message via ``maybeFlush``.
    if (status !== "ready") {
      stop()
      return
    }
    // An approval box (or a consent dialog) can be open while ``status`` is
    // "ready" — that's an in-flight turn too; the message flushes when it
    // resolves.
    if (get(combined).toolApprovalWaiter || consentFlowPending) return
    // Nothing in flight (e.g. the turn already finished/errored): just send.
    void dispatchQueued(queued)
  }

  async function sendMessage(text: string): Promise<boolean> {
    const trimmed = text.trim()
    if (!trimmed) return false
    // Coalesce into an existing queued message so rapid sends accumulate
    // rather than racing each other out.
    if (get(combined).queuedMessage !== null) {
      enqueue(trimmed)
      return true
    }
    // Auto mode with a burst running: hold the message and inject it at the
    // run's next round boundary (or immediately via send-now). Auto idle /
    // armed has no in-flight round, so dispatch now.
    if (get(conversationStore.autoModeOn)) {
      if (get(conversationStore.working)) {
        enqueue(trimmed)
        return true
      }
      return actuallySend(trimmed)
    }
    if (get(conversationStore.armed)) {
      return actuallySend(trimmed)
    }
    // Interactive: hold while a turn is in flight; it auto-sends when the turn
    // yields.
    if (interactiveTurnActive()) {
      enqueue(trimmed)
      return true
    }
    return actuallySend(trimmed)
  }

  // Dispatch a message to its real transport: armed-first-send (creates the
  // conversation in auto mode), inject-on-send (auto flag on), or a normal
  // interactive turn via ensure + POST /{sid}/messages.
  async function actuallySend(text: string): Promise<boolean> {
    const trimmed = text.trim()
    if (!trimmed) return false
    const autoOn = get(conversationStore.autoModeOn)
    const armed = get(conversationStore.armed)
    const autoActive = autoOn || armed
    if (!autoActive && status !== "ready") return false
    if (!get(chat_cost_disclaimer_acknowledged)) {
      if (!onConsentNeeded) return false
      const approved = await onConsentNeeded()
      if (!approved) return false
      if (!autoActive && status !== "ready") return false
    }
    // Armed-first-send (Revision R2): auto mode was armed client-side on a
    // brand-new conversation. The FIRST send creates the conversation via
    // enable seeded with this message, so the very first turn runs in auto
    // mode.
    if (armed && !autoOn) {
      return beginArmedAutoRun(trimmed)
    }
    // Inject-on-send (Revision R1): while the flag is on, a user message is
    // injected into the server-owned run — it never stops auto mode and
    // triggers no new consent. The run echoes the message + streams the burst
    // on the observer (which is why nothing is rendered locally here).
    if (autoOn) {
      const result = await conversationStore.sendMessage(trimmed)
      if (!result.ok) {
        pushInlineError(
          `Couldn't send the message: ${result.error ?? "unknown error"}`,
        )
        return false
      }
      return true
    }
    return beginInteractiveTurn(trimmed)
  }

  // Start an interactive turn: ensure the conversation exists (create/adopt —
  // the replacement for the old conversation-per-request POST /api/chat),
  // render the typed message locally, open a fresh assistant turn, and POST
  // the message (the server starts the turn task; the observer streams it).
  async function beginInteractiveTurn(
    text: string,
    isRetry = false,
  ): Promise<boolean> {
    removeErrors()
    const currentMessages = get(combined).messages
    const priorTraceId =
      traceIdForNextChatRequest(currentMessages) ?? get(persisted).traceId

    const ensured = await conversationStore.ensure(priorTraceId)
    if (!ensured.ok || !ensured.sessionId) {
      pushInlineError(
        `Couldn't reach the assistant: ${ensured.error ?? "unknown error"}`,
      )
      return false
    }
    persisted.update((p) => ({ ...p, sessionId: ensured.sessionId ?? null }))

    // The browser still composes the message content: the app-context header
    // is prepended to the first message of a turn (architecture §7 note —
    // the runtime just carries it).
    const currentAppState = getCurrentAppState()
    const header = buildContextHeader(
      currentAppState,
      get(persisted).lastSentAppState,
    )
    const apiContent = header ? header + "\n" + text : text
    persisted.update((p) => ({ ...p, lastSentAppState: currentAppState }))

    posthog.capture("chat_message_sent", {
      is_new_conversation: !priorTraceId && !isRetry,
      message_length: text.length,
      has_app_context_header: !!header,
      message_count: currentMessages.length,
    })
    if (!priorTraceId && !isRetry) {
      posthog.capture("chat_conversation_started")
    }

    // Render the typed message immediately (zero-latency, like the old local
    // append) and register it for own-echo dedupe; then a fresh assistant
    // placeholder for the reply.
    const localId = chatGenerateId()
    updateMessages((msgs) => [
      ...msgs,
      { id: localId, role: "user", content: text },
    ])
    pendingOwnEchoes.push({ content: text, localId })
    combined.update((s) => ({
      ...s,
      toolExecuting: false,
      showActivityIndicator: false,
      compacting: false,
    }))
    // beginTurn appends the assistant placeholder AND resets the observer's
    // processor so the previous turn's parts aren't re-flushed into it.
    conversationStore.beginTurn()
    setStatus("submitted")

    const thisGeneration = ++generation
    const result = await conversationStore.sendMessage(apiContent)
    if (!result.ok) {
      if (thisGeneration !== generation) return false
      pushInlineError(result.error ?? "Couldn't send the message.")
      setStatus("ready")
      return false
    }
    // Attach the server-minted id to the pending own-echo entry so the echo
    // dedupes by id even if the content matcher misses.
    const entry = pendingOwnEchoes.find((e) => e.localId === localId && !e.id)
    if (entry && result.messageId) entry.id = result.messageId
    return true
  }

  // Armed-first-send (Revision R2): create the server-owned run seeded with
  // the user's first message and NO trace_id. The server does not echo a
  // seed's extra_messages, so the user message renders locally.
  async function beginArmedAutoRun(text: string): Promise<boolean> {
    if (armedEnablePending) return false
    armedEnablePending = true
    try {
      return await beginArmedAutoRunInner(text)
    } finally {
      armedEnablePending = false
    }
  }

  async function beginArmedAutoRunInner(text: string): Promise<boolean> {
    removeErrors()
    const currentAppState = getCurrentAppState()
    const header = buildContextHeader(
      currentAppState,
      get(persisted).lastSentAppState,
    )
    const userMessage: ChatMessage = {
      id: chatGenerateId(),
      role: "user",
      content: text,
    }
    updateMessages((msgs) => [...msgs, userMessage])
    persisted.update((p) => ({ ...p, lastSentAppState: currentAppState }))
    const apiContent = header ? header + "\n" + text : text
    const seed: CreateAutoConversationRequest = {
      kind: "auto",
      extra_messages: [{ role: "user", content: apiContent }],
    }
    const result = await conversationStore.requestEnable(seed)
    if (!result.ok) {
      pushInlineError(
        `Couldn't start auto mode: ${result.error ?? "unknown error"}`,
      )
      return false
    }
    return true
  }

  function stop(): void {
    // POST /{sid}/stop cancels the in-flight turn server-side; the idle state
    // event settles the UI (status ready + queued flush) — replacing the old
    // client-side stream abort.
    posthog.capture("chat_stopped")
    void conversationStore.stop()
  }

  function retryLastRequest(): void {
    if (status !== "ready") return
    const msgs = get(combined).messages
    let lastUserIdx = -1
    for (let i = msgs.length - 1; i >= 0; i--) {
      if (msgs[i].role === "user") {
        lastUserIdx = i
        break
      }
    }
    if (lastUserIdx === -1) return
    posthog.capture("chat_retry")
    const userText = msgs[lastUserIdx].content ?? ""
    updateMessages((m) => m.slice(0, lastUserIdx))
    void beginInteractiveTurn(userText, true)
  }

  function clearRuntimeAffordances() {
    combined.update((s) => ({
      ...s,
      toolExecuting: false,
      showActivityIndicator: false,
      compacting: false,
      autoWorking: false,
      retry: null,
      queuedMessage: null,
    }))
  }

  function reset(): void {
    generation++
    // Stop observing (the run survives server-side; the user is starting a
    // new conversation). Clears the stale "on" indicator.
    conversationStore.detach()
    clearToolApprovalState()
    pendingOwnEchoes.length = 0
    persisted.set({ ...EMPTY_PERSISTED })
    combined.update((s) => ({ ...s, messages: [], contextUsage: null }))
    clearRuntimeAffordances()
    setStatus("ready")
  }

  function loadSession(
    messages: ChatMessage[],
    traceId: string,
    contextUsage: ContextUsage | null = null,
    opts?: { autoActive?: boolean },
  ): void {
    generation++
    // Detach any prior conversation's observer before showing a different one.
    conversationStore.detach()
    clearToolApprovalState()
    pendingOwnEchoes.length = 0
    persisted.set({
      sessionId: null,
      traceId,
      collapsedPartKeys: {},
      lastSentAppState: null,
    })
    combined.update((s) => ({ ...s, messages, contextUsage }))
    clearRuntimeAffordances()
    setStatus("ready")
    // Re-attach the conversation's observer (create-or-adopt by trace):
    // in-flight turns replay into a fresh assistant turn, the state marker
    // restores working/auto affordances, and a parked approval re-surfaces
    // (replayed pending event → approvals fetch). Best-effort async — the
    // hydrated transcript is already showing.
    void conversationStore
      .ensure(traceId, {
        openInflightTurn: true,
        assumeAutoOn: opts?.autoActive ?? false,
      })
      .then((r) => {
        if (r.ok && r.sessionId) {
          persisted.update((p) => ({ ...p, sessionId: r.sessionId ?? null }))
        }
      })
  }

  // Reconnect after a hard refresh: sessionStorage holds only the handles, so
  // hydrate the transcript from the persisted snapshot, then re-attach.
  async function resyncOnLoad(): Promise<void> {
    const { sessionId: storedSid, traceId: storedTrace } = get(persisted)
    if (!storedSid && !storedTrace) return
    const thisGeneration = ++generation
    const isStale = () => thisGeneration !== generation

    // Freshest leaf wins: a live record knows rounds the tab never saw. A 404
    // means the desktop restarted or evicted the record — the trace id still
    // recovers the conversation (create-or-adopt + trace-tail rehydration).
    let leaf = storedTrace
    let initialWorking: boolean | undefined
    if (storedSid) {
      try {
        const response = await fetch(
          `${base_url}/api/conversations/${encodeURIComponent(storedSid)}`,
        )
        if (response.ok) {
          const item = (await response.json()) as {
            current_trace_id?: string | null
            state?: string
          }
          if (item?.current_trace_id) leaf = item.current_trace_id
          initialWorking = item?.state === "running"
        }
      } catch {
        /* desktop unreachable — fall through to the trace-keyed path */
      }
    }
    if (isStale()) return

    // Show the reconnecting affordance while we hydrate → attach so the
    // conversation doesn't look empty/dead before liveness is known.
    conversationStore.beginReconnect()
    if (leaf) {
      try {
        const { data: snapshot, error } = await client.GET(
          "/api/chat/sessions/{session_id}",
          { params: { path: { session_id: leaf } } },
        )
        if (isStale()) return
        if (!error && snapshot) {
          const hydrated = hydrateSessionFromSnapshot(snapshot)
          combined.update((s) => ({
            ...s,
            messages: hydrated.messages,
            contextUsage: hydrated.contextUsage,
          }))
          persisted.update((p) => ({
            ...p,
            traceId: hydrated.continuationTraceId,
          }))
        }
      } catch {
        /* hydration failed — still attach so live events come back */
      }
    }
    if (isStale()) return
    conversationStore.beginReconnect()
    const ensured = await conversationStore.ensure(leaf, {
      openInflightTurn: true,
      initialWorking,
    })
    if (isStale()) return
    if (ensured.ok && ensured.sessionId) {
      persisted.update((p) => ({ ...p, sessionId: ensured.sessionId ?? null }))
    }
  }

  function toolNameForCallId(toolCallId: string): string | undefined {
    return get(combined).toolApprovalWaiter?.payload.items.find(
      (i) => i.toolCallId === toolCallId,
    )?.toolName
  }

  function applyToolApprovalRun(toolCallId: string): void {
    if (!get(combined).toolApprovalWaiter) return
    posthog.capture("chat_tool_approval_run", {
      tool_name: toolNameForCallId(toolCallId),
    })
    combined.update((s) => ({
      ...s,
      toolApprovalPicks: { ...s.toolApprovalPicks, [toolCallId]: true },
    }))
    maybeFinishToolApproval()
  }

  function applyToolApprovalSkip(toolCallId: string): void {
    if (!get(combined).toolApprovalWaiter) return
    posthog.capture("chat_tool_approval_skip", {
      tool_name: toolNameForCallId(toolCallId),
    })
    combined.update((s) => ({
      ...s,
      toolApprovalPicks: { ...s.toolApprovalPicks, [toolCallId]: false },
    }))
    maybeFinishToolApproval()
  }

  function dismissUpgradeNudge(): void {
    combined.update((s) => ({ ...s, upgradeNudgeVersion: null }))
  }

  async function checkVersionPolicy(): Promise<void> {
    // Surface the upgrade banners on load, before the user sends anything.
    // Best-effort: any failure just leaves the banners as-is.
    try {
      const res = await fetch(`${base_url}/api/chat/version_policy`)
      if (!res.ok) return
      const data = (await res.json()) as {
        required?: boolean
        upgrade_nudge_version?: string | null
      }
      combined.update((s) => ({
        ...s,
        versionRequired: !!data.required,
        upgradeNudgeVersion:
          typeof data.upgrade_nudge_version === "string"
            ? data.upgrade_nudge_version
            : null,
      }))
    } catch {
      /* network/desktop error — leave banner state untouched */
    }
  }

  function togglePartCollapsed(key: string, currentlyCollapsed: boolean): void {
    persisted.update((p) => ({
      ...p,
      collapsedPartKeys: { ...p.collapsedPartKeys, [key]: !currentlyCollapsed },
    }))
  }

  return {
    subscribe: combined.subscribe,
    sendMessage,
    sendQueuedNow,
    clearQueued,
    stop,
    retryLastRequest,
    reset,
    loadSession,
    resyncOnLoad,
    togglePartCollapsed,
    pushInlineError: (message: string) => pushInlineError(message),
    applyToolApprovalRun,
    applyToolApprovalSkip,
    dismissUpgradeNudge,
    checkVersionPolicy,
    get onConsentNeeded() {
      return onConsentNeeded
    },
    set onConsentNeeded(fn: (() => Promise<boolean>) | null) {
      onConsentNeeded = fn
    },
    get onAutoModeConsentNeeded() {
      return onAutoModeConsentNeeded
    },
    set onAutoModeConsentNeeded(fn: AutoModeConsentDecision | null) {
      onAutoModeConsentNeeded = fn
    },
  }
}

export const chatSessionStore: ChatSessionStore =
  createChatSessionStore(SESSION_STORAGE_KEY)
