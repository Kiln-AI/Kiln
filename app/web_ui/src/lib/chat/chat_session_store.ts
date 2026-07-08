import { writable, get, type Readable } from "svelte/store"
import posthog from "posthog-js"
import {
  streamChat,
  resumePendingToolCalls,
  chatGenerateId,
  traceIdForNextChatRequest,
  type ChatMessage,
  type ContextUsage,
  type ToolCallsPendingItem,
  type ToolCallsPendingPayload,
} from "./streaming_chat"
import {
  auto_run_store,
  type AutoRunStore,
  type EnableAutoRequest,
  type DeclineAutoRequest,
} from "./auto_run_store"
import type { AutoModeConsentRequiredPayload } from "./streaming_chat"
import { sessionStorageStore } from "$lib/stores/local_storage_store"
import {
  hydrateSessionFromSnapshot,
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

const CHAT_API_URL = `${base_url}/api/chat`
const SESSION_STORAGE_KEY = "kiln_chat_session"

export interface PersistedChatSession {
  messages: ChatMessage[]
  collapsedPartKeys: Record<string, boolean>
  lastSentAppState: AppState | null
  /**
   * Approximate context-window usage for the gauge. Persisted so a
   * sessionStorage reload keeps the gauge. ``null`` before the first turn.
   */
  contextUsage: ContextUsage | null
}

export interface ToolApprovalWaiter {
  payload: ToolCallsPendingPayload
}

export interface ChatSessionState extends PersistedChatSession {
  status: "ready" | "submitted" | "streaming"
  abortController: AbortController | null
  toolApprovalWaiter: ToolApprovalWaiter | null
  toolApprovalPicks: Record<string, boolean | undefined>
  toolExecuting: boolean
  showActivityIndicator: boolean
  /**
   * The server is summarizing earlier messages (compaction) for this turn
   * (Phase 5). Runtime-only — NOT persisted. Set by ``kiln_compaction_status``
   * and cleared on the first content event / turn end / reset.
   */
  compacting: boolean
  /**
   * A server-owned auto-mode burst is actively running. Decoupled from
   * ``status`` (which tracks the interactive client stream) so the chat view
   * can drive the SAME loading affordances during auto bursts while keeping the
   * input usable for inject-on-send.
   */
  autoWorking: boolean
  /**
   * A transient upstream failure is being retried with backoff during the
   * interactive stream (``kiln-chat-retry``): ``{ attempt, max }`` while retrying,
   * else null. Drives the "retrying N/M…" affordance for non-auto chat. (Auto
   * mode surfaces the same affordance via ``auto_run_store.retry``.) Runtime-only.
   */
  retry: { attempt: number; max: number } | null
  /**
   * Preferred version from a server upgrade nudge (non-blocking), or null when
   * no nudge is active or the user dismissed it. Runtime-only, not persisted.
   */
  upgradeNudgeVersion: string | null
  /**
   * True when the server rejected the request because the client is below the
   * required minimum version (HTTP 426). Surfaced as a blocking banner above
   * the composer rather than as a conversation message. Runtime-only.
   */
  versionRequired: boolean
  /**
   * A user message typed while a turn was in flight (interactive stream or auto
   * burst), held client-side until the turn yields — then auto-sent — or sent
   * immediately via send-now. ``null`` when nothing is queued. A second send
   * while one is queued appends to it. Runtime-only, not persisted.
   */
  queuedMessage: string | null
}

/**
 * Asked of the UI when the model requests auto mode. Returns ``true`` to enable
 * (accept) or ``false`` to decline; the store then drives the auto-run store.
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
   * running (the runner picks it up at the next round boundary). No-op when
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
  ): void
  /**
   * Resync the restored-from-sessionStorage conversation back to its true
   * auto-mode state after a hard refresh. If the conversation has an active
   * server-owned auto run, hydrate from the run's CURRENT leaf (catching up on
   * rounds completed while the tab was gone) and re-attach the live observer —
   * mirroring the History → Chat History restore path. No-op when there is no
   * stored trace id or no active run. Idempotent / safe to call on every load.
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
  messages: [],
  collapsedPartKeys: {},
  lastSentAppState: null,
  contextUsage: null,
}

export function createChatSessionStore(
  sessionStorageKey?: string,
  autoRunStore: AutoRunStore = auto_run_store,
): ChatSessionStore {
  const persisted = sessionStorageKey
    ? sessionStorageStore<PersistedChatSession>(sessionStorageKey, {
        ...EMPTY_PERSISTED,
      })
    : writable<PersistedChatSession>({ ...EMPTY_PERSISTED })

  let status: ChatSessionState["status"] = "ready"
  let abortController: AbortController | null = null
  // Synchronous in-flight guard for the armed-first-send enable. Local `status`
  // stays "ready" and `armed` stays set during the requestEnable round-trip, so
  // without this a second Enter in that window would fire a second /enable POST
  // (two server-owned auto runs for one conversation, both bypassing consent).
  let armedEnablePending = false
  let continuationTraceId: string | undefined = undefined
  let generation = 0
  let toolApprovalResolver:
    | ((decisions: Record<string, boolean>) => void)
    | null = null

  const combined = writable<ChatSessionState>({
    ...get(persisted),
    status,
    abortController,
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
  // that lives for the lifetime of the app. Do not use createChatSessionStore
  // for short-lived contexts.
  persisted.subscribe(($persisted) => {
    combined.update((s) => ({
      ...s,
      messages: $persisted.messages,
      collapsedPartKeys: $persisted.collapsedPartKeys,
      lastSentAppState: $persisted.lastSentAppState,
      contextUsage: $persisted.contextUsage,
    }))
  })

  function setRuntimeState(
    newStatus: ChatSessionState["status"],
    newAbort: AbortController | null,
  ) {
    status = newStatus
    abortController = newAbort
    combined.update((s) => ({
      ...s,
      status,
      abortController,
    }))
  }

  function updateMessages(updater: (messages: ChatMessage[]) => ChatMessage[]) {
    persisted.update((p) => ({
      ...p,
      messages: updater(p.messages),
    }))
  }

  function updateLastAssistant(update: (draft: ChatMessage) => void) {
    persisted.update((p) => {
      const msgs = p.messages
      const last = msgs[msgs.length - 1]
      if (last?.role === "assistant") {
        const draft = { ...last, parts: last.parts ? [...last.parts] : [] }
        update(draft)
        return { ...p, messages: [...msgs.slice(0, -1), draft] }
      }
      return p
    })
  }

  function removeErrors() {
    persisted.update((p) => ({
      ...p,
      messages: p.messages.filter((m) => m.role !== "error"),
    }))
  }

  // Append an inline error message — the single error-surfacing mechanism shared
  // by the interactive stream, the auto-run observer, and the enable-failure
  // paths (so a failed enable, e.g. 429, is never silently dropped).
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
    persisted.update((p) => {
      const msgs = p.messages
      const last = msgs[msgs.length - 1]
      if (last?.role === "assistant") {
        return {
          ...p,
          messages: [...msgs.slice(0, -1), { ...last, traceId }],
        }
      }
      return p
    })
  }

  function setContextUsage(usage: ContextUsage) {
    persisted.update((p) => ({ ...p, contextUsage: usage }))
  }

  // Runtime-only (not persisted): drives the "Summarizing earlier messages…"
  // indicator while the server compacts the conversation for this turn.
  function setCompacting(compacting: boolean) {
    combined.update((s) => ({ ...s, compacting }))
  }

  // Append a fresh empty assistant message so the next streamed burst (auto run
  // or declined-resume) renders into a new turn rather than the prior one.
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

  // Append an echoed (injected) user message, then a fresh assistant turn so the
  // burst it triggers renders into a new turn — mirrors the server's
  // render-immediately + replay model for inject-on-send (functional spec §4.3.2).
  // Idempotent by echo id: a buffer replay on re-attach (hard-refresh resync /
  // History restore) re-emits the echo for an in-flight injected message the
  // restored transcript already shows — skip it (and don't open another assistant
  // turn) instead of appending a duplicate that would compound on each refresh.
  function appendEchoedUserMessage(content: string, echoId?: string) {
    if (echoId && get(persisted).messages.some((m) => m.echoId === echoId)) {
      return
    }
    removeErrors()
    // A sub-agent report injected mid-run is echoed as a user message wrapped in
    // a <subagent_report> frame; detect it here (same rule as hydration) so the
    // live transcript renders the report chip instead of a raw framed bubble.
    updateMessages((msgs) => [
      ...msgs,
      userChatMessageFromContent(content, echoId),
    ])
    beginAssistantTurn()
  }

  // Wire the auto-run store to drive the same conversation as the interactive
  // stream. The auto runner is server-owned and survives reloads/re-attach; here
  // we only render what it streams (and the on/off indicator state it reports).
  autoRunStore.bind({
    beginAssistantTurn,
    onAssistantMessage: updateLastAssistant,
    onChatTrace: setLastAssistantTraceId,
    onContextUsage: setContextUsage,
    onCompactionStatus: setCompacting,
    onInlineError: (message, traceId, code) =>
      pushInlineError(message, traceId, code),
    onToolExecutionStart: () =>
      combined.update((s) => ({ ...s, toolExecuting: true })),
    onToolExecutionEnd: () => {
      combined.update((s) => ({ ...s, toolExecuting: false }))
      // Round boundary: the runner just finished a tool round and is about to
      // make its next request — flush a queued message so it rides that request
      // (and its echo lands here, at the pause, rather than mid-round).
      maybeFlush()
    },
    onShowActivityIndicator: (show) =>
      combined.update((s) => ({ ...s, showActivityIndicator: show })),
    // Burst liveness drives the same thinking-dots/animated-icon path as the
    // interactive stream (the loading-indicator fix); the input stays usable.
    onWorkingChange: (working) =>
      combined.update((s) => ({ ...s, autoWorking: working })),
    onUserMessage: appendEchoedUserMessage,
    // Idle: a burst ended but the flag stays on. Stop the working affordances;
    // the green indicator persists (it binds to autoModeOn, not autoWorking).
    onAutoModeIdle: () => {
      combined.update((s) => ({
        ...s,
        toolExecuting: false,
        showActivityIndicator: false,
        compacting: false,
        autoWorking: false,
      }))
      // The burst settled and auto mode is waiting for the user — the moment to
      // flush a queued message (injects it, which starts the next burst).
      maybeFlush()
    },
    onAutoModeOff: () =>
      // Auto mode stopped — drop any pending queued message (stopping clears the
      // queue; the user can re-send if they still want it).
      combined.update((s) => ({
        ...s,
        toolExecuting: false,
        showActivityIndicator: false,
        compacting: false,
        autoWorking: false,
        queuedMessage: null,
      })),
    onToolCallsPending: handleAutoToolCallsPending,
  })

  // Graceful-stop handoff (functional spec §4.4(1)): the runner finished the
  // in-flight turn and surfaced its client tool calls instead of auto-executing
  // them. Auto mode is now off (the observer published auto-mode-off), so the
  // conversation is back in NORMAL mode — drive the EXISTING approval gate
  // (handleToolCallsPending → the same toolApprovalWaiter UI) and the EXISTING
  // /api/chat/execute-tools continuation (resumePendingToolCalls). No parallel
  // approval UI; reuse the interactive machinery.
  function handleAutoToolCallsPending(items: ToolCallsPendingItem[]): void {
    if (!Array.isArray(items) || items.length === 0) return
    const traceId = traceIdForNextChatRequest(get(persisted).messages)
    if (!traceId) {
      pushInlineError(
        "Couldn't resume after stopping auto mode: missing conversation id.",
      )
      return
    }
    // A fresh assistant turn renders the approved tools' continuation.
    beginAssistantTurn()
    const thisGeneration = ++generation
    const isStale = () => thisGeneration !== generation
    void resumePendingToolCalls({
      apiUrl: CHAT_API_URL,
      traceId,
      items,
      onToolCallsPending: (payload) => {
        if (isStale()) return Promise.resolve({})
        return handleToolCallsPending(payload)
      },
      onAssistantMessage: (update) => {
        if (isStale()) return
        updateLastAssistant(update)
      },
      onChatTrace: (tid) => {
        if (isStale()) return
        setLastAssistantTraceId(tid)
      },
      onContextUsage: (usage) => {
        if (isStale()) return
        setContextUsage(usage)
      },
      onCompactionStatus: (compacting) => {
        if (isStale()) return
        setCompacting(compacting)
      },
      onInlineError: (message, traceId, code) => {
        if (isStale()) return
        pushInlineError(message, traceId, code)
      },
      onToolExecutionStart: () => {
        if (isStale()) return
        combined.update((s) => ({ ...s, toolExecuting: true }))
      },
      onToolExecutionEnd: () => {
        if (isStale()) return
        combined.update((s) => ({ ...s, toolExecuting: false }))
      },
      onShowActivityIndicator: (show) => {
        if (isStale()) return
        combined.update((s) => ({ ...s, showActivityIndicator: show }))
      },
      onUserMessage: (content, echoId) => {
        if (isStale()) return
        // A sub-agent report echoed at a continuation boundary; render it as a
        // report chip and continue into the fresh assistant turn it opens.
        appendEchoedUserMessage(content, echoId)
      },
      onFinish: () => {
        if (isStale()) return
        combined.update((s) => ({
          ...s,
          toolExecuting: false,
          showActivityIndicator: false,
          compacting: false,
        }))
      },
      onError: (err) => {
        if (isStale()) return
        combined.update((s) => ({
          ...s,
          toolExecuting: false,
          showActivityIndicator: false,
          compacting: false,
        }))
        pushInlineError(err.message)
      },
    })
  }

  function beginStreaming(text: string, isRetry = false) {
    removeErrors()
    const currentMessages = get(persisted).messages
    const traceId =
      traceIdForNextChatRequest(currentMessages) ?? continuationTraceId
    const userMessage: ChatMessage = {
      id: chatGenerateId(),
      role: "user",
      content: text,
    }
    const assistantMessage: ChatMessage = {
      id: chatGenerateId(),
      role: "assistant",
      parts: [],
    }
    updateMessages((msgs) => [...msgs, userMessage, assistantMessage])

    const currentAppState = getCurrentAppState()
    const header = buildContextHeader(
      currentAppState,
      get(persisted).lastSentAppState,
    )
    let apiMessage = userMessage
    if (header) {
      apiMessage = { ...userMessage, content: header + "\n" + text }
    }
    persisted.update((p) => ({
      ...p,
      lastSentAppState: currentAppState,
    }))

    posthog.capture("chat_message_sent", {
      is_new_conversation: !traceId && !isRetry,
      message_length: text.length,
      has_app_context_header: !!header,
      message_count: currentMessages.length,
    })
    if (!traceId && !isRetry) {
      posthog.capture("chat_conversation_started")
    }

    combined.update((s) => ({
      ...s,
      toolExecuting: false,
      showActivityIndicator: false,
      compacting: false,
    }))

    const controller = new AbortController()
    setRuntimeState("submitted", controller)

    const thisGeneration = ++generation

    const isStale = () => thisGeneration !== generation

    streamChat({
      apiUrl: CHAT_API_URL,
      messages: [apiMessage],
      traceId,
      onToolCallsPending: (payload) => {
        if (isStale()) return Promise.resolve({})
        return handleToolCallsPending(payload)
      },
      onToolExecutionStart: () => {
        if (isStale()) return
        combined.update((s) => ({
          ...s,
          toolExecuting: true,
        }))
      },
      onToolExecutionEnd: () => {
        if (isStale()) return
        combined.update((s) => ({
          ...s,
          toolExecuting: false,
        }))
      },
      onShowActivityIndicator: (show) => {
        if (isStale()) return
        combined.update((s) => ({
          ...s,
          showActivityIndicator: show,
        }))
      },
      onRetry: (attempt, max) => {
        if (isStale()) return
        combined.update((s) => ({ ...s, retry: { attempt, max } }))
      },
      onRetryClear: () => {
        if (isStale()) return
        combined.update((s) => ({ ...s, retry: null }))
      },
      onAssistantMessage: (update) => {
        if (isStale()) return
        if (status !== "streaming") {
          setRuntimeState("streaming", controller)
        }
        updateLastAssistant(update)
      },
      onChatTrace: (traceId) => {
        if (isStale()) return
        setLastAssistantTraceId(traceId)
      },
      onContextUsage: (usage) => {
        if (isStale()) return
        setContextUsage(usage)
      },
      onCompactionStatus: (compacting) => {
        if (isStale()) return
        setCompacting(compacting)
      },
      onAutoModeConsentRequired: async (payload) => {
        if (isStale()) return
        await handleAutoModeConsent(payload)
      },
      onUserMessage: (content, echoId) => {
        if (isStale()) return
        // A sub-agent report echoed on the interactive stream — at the start of
        // this next-turn stream (the persisted order is: the user's typed
        // message, then reports) or at a mid-stream continuation boundary.
        // appendEchoedUserMessage renders it (report frames become chips via
        // userChatMessageFromContent) and opens a fresh assistant turn for the
        // rest of the stream; the prior empty placeholder stays hidden.
        appendEchoedUserMessage(content, echoId)
      },
      onVersionNudge: (preferredVersion) => {
        if (isStale()) return
        // Set unconditionally: repeated nudges across tool rounds collapse to a
        // single banner, and a new server preference re-surfaces it even if a
        // prior nudge was dismissed.
        combined.update((s) => ({
          ...s,
          upgradeNudgeVersion: preferredVersion,
        }))
      },
      onInlineError: (message, traceId, code) => {
        if (isStale()) return
        // Blocking "client too old" rejection: show it as a banner above the
        // composer (like the upgrade nudge) instead of a conversation message.
        if (code === CHAT_CLIENT_VERSION_TOO_OLD) {
          combined.update((s) => ({ ...s, versionRequired: true }))
          setRuntimeState("ready", null)
          return
        }
        const errorMsg: ChatMessage = {
          id: chatGenerateId(),
          role: "error",
          content: message,
          traceId,
          errorCode: code,
        }
        updateMessages((msgs) => [...msgs, errorMsg])
        setRuntimeState("ready", null)
      },
      onFinish: () => {
        if (isStale()) return
        combined.update((s) => ({
          ...s,
          toolExecuting: false,
          showActivityIndicator: false,
          compacting: false,
          retry: null,
        }))
        setRuntimeState("ready", null)
        // The interactive turn ended (normal completion or a Stop/abort, which
        // streamChat reports as a finish) — flush any queued message now.
        maybeFlush()
      },
      onError: (err) => {
        if (isStale()) return
        combined.update((s) => ({
          ...s,
          toolExecuting: false,
          showActivityIndicator: false,
          compacting: false,
          retry: null,
        }))
        const errorMsg: ChatMessage = {
          id: chatGenerateId(),
          role: "error",
          content: err.message,
        }
        updateMessages((msgs) => [...msgs, errorMsg])
        setRuntimeState("ready", null)
      },
      signal: controller.signal,
    })
  }

  let onConsentNeeded: (() => Promise<boolean>) | null = null
  let onAutoModeConsentNeeded: AutoModeConsentDecision | null = null

  // The interactive stream ended on ``auto-mode-consent-required``. Ask the UI;
  // accept hands off to the server-owned auto runner, decline resumes the normal
  // interactive stream with the enable call resolved as declined.
  async function handleAutoModeConsent(
    payload: AutoModeConsentRequiredPayload,
  ): Promise<void> {
    // payload.traceId is nullable; continuationTraceId is only set by
    // loadSession(), so in a normal live chat fall back to the trace
    // setLastAssistantTraceId() wrote onto the last assistant message before
    // using continuationTraceId.
    const traceId =
      payload.traceId ??
      traceIdForNextChatRequest(get(persisted).messages) ??
      continuationTraceId
    if (!traceId) return
    // If auto mode is already on/armed — the user turned it on themselves (e.g.
    // clicked the footer toggle) while this interactive stream was still
    // resolving the model's enable call — there is nothing to ask: accept
    // silently so the pending enable tool call resolves without re-showing the
    // consent dialog.
    const alreadyOn = get(autoRunStore.autoModeOn) || get(autoRunStore.armed)
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
      const seed: EnableAutoRequest = {
        trace_id: traceId,
        enable_tool_call_id: payload.enableToolCallId,
        pending_tool_calls: siblings,
        reason: payload.reason,
      }
      // Surface enable failures (e.g. 429 "Too many auto runs") instead of
      // silently dropping them — the dialog has already closed, so the inline
      // chat error is the only signal the user gets.
      const result = await autoRunStore.requestEnable(seed)
      if (!result.ok) {
        pushInlineError(
          `Couldn't start auto mode: ${result.error ?? "unknown error"}`,
        )
      }
    } else {
      const req: DeclineAutoRequest = {
        trace_id: traceId,
        enable_tool_call_id: payload.enableToolCallId,
        siblings,
      }
      await autoRunStore.decline(req)
    }
  }

  // An interactive turn is "in flight" — sending should queue rather than
  // dispatch — when the client stream is active or a tool approval is open
  // (waiting on the user mid-turn). Auto mode is intentionally NOT consulted
  // here: it never holds client-side. A message sent during an auto burst is
  // injected immediately so the runner appends it to its next request (its next
  // round boundary), rather than waiting for the whole auto run to finish.
  function interactiveTurnActive(): boolean {
    if (status !== "ready") return true
    if (get(combined).toolApprovalWaiter) return true
    return false
  }

  // Hold a message client-side while a turn is in flight. A second send while one
  // is queued appends (blank line between) so the coalesced text sends as one.
  function enqueue(text: string): void {
    combined.update((s) => ({
      ...s,
      queuedMessage: s.queuedMessage ? `${s.queuedMessage}\n\n${text}` : text,
    }))
  }

  function clearQueued(): void {
    combined.update((s) => ({ ...s, queuedMessage: null }))
  }

  // Dispatch a queued message: clear it, then send. If the send is rejected
  // (declined consent, a failed auto-mode injection, an armed enable already
  // pending, …) restore it to the FRONT of whatever has queued since, so a
  // failed/declined send never silently drops the user's typed text.
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
  // Guards on ``interactiveTurnActive`` (never flush mid interactive turn; a
  // flush hook can fire mid-transition) and ``versionRequired`` (sending would
  // just be rejected).
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
    // Auto mode: inject immediately and keep auto mode running — the runner
    // picks the message up at its next round boundary. (Auto sends already
    // dispatch immediately, so a queued message here only exists if auto turned
    // on after it was queued interactively; inject it now.)
    if (get(autoRunStore.autoModeOn) || get(autoRunStore.armed)) {
      void dispatchQueued(queued)
      return
    }
    // Interactive turn in flight: terminate it. The resulting ready transition
    // (abort → onFinish) flushes the queued message via ``maybeFlush``.
    if (status !== "ready") {
      stop()
      return
    }
    // A tool approval can be open while ``status`` is "ready" (a pending-tool
    // continuation handed off from a graceful auto stop). That's an in-flight
    // turn too — leave the message queued rather than starting a competing
    // request; it flushes when that continuation yields.
    if (get(combined).toolApprovalWaiter) return
    // Nothing in flight (e.g. the turn already finished/errored): just send it.
    void dispatchQueued(queued)
  }

  async function sendMessage(text: string): Promise<boolean> {
    const trimmed = text.trim()
    if (!trimmed) return false
    // Coalesce into an existing queued message (the queue holds one squashed
    // entry) so rapid sends accumulate rather than racing each other out.
    if (get(combined).queuedMessage !== null) {
      enqueue(trimmed)
      return true
    }
    // Auto mode with a burst running: hold the message in the queue and inject it
    // at the runner's next round boundary (or immediately via send-now), so it
    // rides the next request instead of jumping into the transcript mid-round.
    // Auto idle / armed has no in-flight round, so dispatch now (which starts a
    // burst immediately — the "as soon as possible" path).
    if (get(autoRunStore.autoModeOn)) {
      if (get(autoRunStore.working)) {
        enqueue(trimmed)
        return true
      }
      return actuallySend(trimmed)
    }
    if (get(autoRunStore.armed)) {
      return actuallySend(trimmed)
    }
    // Interactive: hold while a turn is in flight; it auto-sends when the turn
    // yields. The composer surfaces it above the input with send-now/edit/cancel.
    if (interactiveTurnActive()) {
      enqueue(trimmed)
      return true
    }
    return actuallySend(trimmed)
  }

  // Dispatch a message to its real transport: armed-first-send (creates the
  // run), inject-on-send (auto flag on), or the interactive stream. The
  // interactive stream assumes no client turn is in flight — callers gate on
  // ``interactiveTurnActive`` or flush on a turn ending.
  async function actuallySend(text: string): Promise<boolean> {
    const trimmed = text.trim()
    if (!trimmed) return false
    const autoOn = get(autoRunStore.autoModeOn)
    const armed = get(autoRunStore.armed)
    // The interactive path requires an idle client stream; the auto paths
    // (inject / armed-first-send) do not (auto bursts run server-side, leaving
    // the local status "ready").
    const autoActive = autoOn || armed
    if (!autoActive && status !== "ready") return false
    if (!get(chat_cost_disclaimer_acknowledged)) {
      if (!onConsentNeeded) return false
      const approved = await onConsentNeeded()
      if (!approved) return false
      if (!autoActive && status !== "ready") return false
    }
    // Armed-first-send (Revision R2): auto mode was armed client-side on a
    // brand-new conversation (no trace_id yet, no server run). The FIRST send
    // creates the run via enable seeded with this message (no trace_id), so the
    // very first turn runs in auto mode. armed is checked before autoOn because
    // an armed conversation has no run yet to inject into.
    if (armed && !autoOn) {
      return beginArmedAutoRun(trimmed)
    }
    // Inject-on-send (Revision R1): while the conversation's auto-mode flag is on
    // (RUNNING or IDLE) a user message is injected into the server-owned run, not
    // sent interactively — it never stops auto mode and triggers no new auto-mode
    // consent. The runner echoes the message + streams the burst on the observer
    // stream (ui_design §2; architecture §13.2/§13.4).
    if (autoOn) {
      const traceId = traceIdForNextChatRequest(get(persisted).messages)
      const result = await autoRunStore.sendMessage(trimmed, traceId)
      if (!result.ok) {
        pushInlineError(
          `Couldn't send the message: ${result.error ?? "unknown error"}`,
        )
        return false
      }
      return true
    }
    beginStreaming(trimmed)
    return true
  }

  // Armed-first-send (Revision R2): create the server-owned auto run seeded with
  // the user's first message and NO trace_id, so the backend starts a fresh
  // conversation and the first turn runs in auto mode. The server does not echo
  // a seed's extra_messages (only the /message inject path echoes), so we render
  // the user message locally — mirroring beginStreaming. requestEnable opens the
  // assistant turn, attaches the live observer, and clears the armed flag.
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
    const seed: EnableAutoRequest = {
      extra_messages: [{ role: "user", content: apiContent }],
    }
    const result = await autoRunStore.requestEnable(seed)
    if (!result.ok) {
      pushInlineError(
        `Couldn't start auto mode: ${result.error ?? "unknown error"}`,
      )
      return false
    }
    return true
  }

  function stop(): void {
    if (abortController) {
      posthog.capture("chat_stopped")
      abortController.abort()
    }
  }

  function retryLastRequest(): void {
    if (status !== "ready") return
    const msgs = get(persisted).messages
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
    persisted.update((p) => ({
      ...p,
      messages: p.messages.slice(0, lastUserIdx),
    }))
    beginStreaming(userText, true)
  }

  function reset(): void {
    if (abortController) {
      abortController.abort()
    }
    // Stop observing any active auto run (the run survives server-side; the user
    // is starting a new conversation). Clears the stale "on" indicator.
    autoRunStore.detach()
    clearToolApprovalState()
    continuationTraceId = undefined
    persisted.set({
      messages: [],
      collapsedPartKeys: {},
      lastSentAppState: null,
      contextUsage: null,
    })
    combined.update((s) => ({
      ...s,
      toolExecuting: false,
      showActivityIndicator: false,
      compacting: false,
      queuedMessage: null,
    }))
    setRuntimeState("ready", null)
  }

  function loadSession(
    messages: ChatMessage[],
    traceId: string,
    contextUsage: ContextUsage | null = null,
  ): void {
    if (abortController) {
      abortController.abort()
    }
    // Detach any prior run's observer before hydrating a different conversation.
    // If the loaded conversation is itself auto-active, the caller re-attaches
    // right after (chat_history.selectSession), which happens after this.
    autoRunStore.detach()
    clearToolApprovalState()
    continuationTraceId = traceId
    persisted.set({
      messages,
      collapsedPartKeys: {},
      lastSentAppState: null,
      contextUsage,
    })
    combined.update((s) => ({
      ...s,
      toolExecuting: false,
      showActivityIndicator: false,
      compacting: false,
      queuedMessage: null,
    }))
    setRuntimeState("ready", null)
  }

  // Resync after a hard refresh. The page restored stale messages from
  // sessionStorage but never re-attached, so an auto-mode conversation looks
  // dead (no indicator, no live events). Resolve the stored (possibly stale)
  // leaf trace id to an active run via the registry's whole-chain index; if one
  // exists, hydrate from the run's CURRENT leaf and attach — the EXACT
  // hydrate+attach the History restore path uses (loadSession + attach).
  async function resyncOnLoad(): Promise<void> {
    // The stored continuation trace id is the last assistant message's traceId
    // restored from sessionStorage (continuationTraceId is a fresh closure var
    // after a reload, so derive it from the persisted messages).
    const storedTraceId =
      traceIdForNextChatRequest(get(persisted).messages) ?? continuationTraceId
    if (!storedTraceId) return

    // Guard against the user switching conversations while an await below is in
    // flight. loadSession() (history restore / New Chat) swaps persisted +
    // continuationTraceId, so if the active trace no longer matches the one we
    // started resyncing, this resync is for a conversation that's no longer
    // showing. Bail with a plain return — never detach()/loadSession(), since
    // the shared auto_run_store may already be owned by the newly-selected
    // session and we must not clobber its observer or its messages.
    const isStillCurrent = () =>
      (traceIdForNextChatRequest(get(persisted).messages) ??
        continuationTraceId) === storedTraceId

    const resolved = await autoRunStore.resolve(storedTraceId)
    // Not active (404 / error): leave the normal restored-from-sessionStorage
    // state untouched.
    if (!resolved) return
    if (!isStillCurrent()) return

    // We now know it's an active run. Show a transient "reconnecting…" affordance
    // while we hydrate → attach so the transcript doesn't look done/idle before
    // liveness is known. attach() keeps it on through the connecting phase and
    // clears it once the stream is established; off/idle/error paths also clear it.
    autoRunStore.beginReconnect()

    // Hydrate from the run's CURRENT leaf so the user catches up on rounds that
    // completed while the tab was gone (the server is authoritative for completed
    // rounds), then attach for live events + buffer replay + the indicator state.
    // The in-flight round comes from the buffer replay into a fresh turn (see the
    // openInflightTurn attach arg below), so this snapshot adoption never clobbers
    // an in-flight response.
    try {
      const { data: snapshot, error } = await client.GET(
        "/api/chat/sessions/{session_id}",
        { params: { path: { session_id: resolved.current_trace_id } } },
      )
      // Switched conversations while the snapshot was fetching: bail before the
      // destructive loadSession() so we don't overwrite the now-current session.
      if (!isStillCurrent()) return
      // A structured error / empty snapshot must NOT short-circuit the attach:
      // resolve() already proved the run is live, so fall through to attach on
      // the restored (stale) view — same as the thrown-exception fallback below.
      // Returning here would leave the conversation looking dead (no indicator,
      // no live stream) in the snapshot-error case while the throw case
      // correctly re-attaches.
      if (!error && snapshot) {
        const {
          messages,
          continuationTraceId: traceId,
          contextUsage,
        } = hydrateSessionFromSnapshot(snapshot)
        // loadSession detaches any prior observer, sets the messages + trace
        // id, and resets runtime state — identical to the history-restore path.
        loadSession(messages, traceId, contextUsage)
      }
    } catch {
      // Hydration failed (network/parse). Fall back: still attach so the user at
      // least gets the live indicator + events on the restored (stale) view.
      if (!isStillCurrent()) return
    }
    // Re-assert reconnecting: loadSession() detaches the prior observer, which
    // clears the flag, so re-mark it for the brief connecting window. attach()
    // clears it on open / first event / off.
    autoRunStore.beginReconnect()
    // initialWorking drives the thinking indicator immediately when RUNNING (no
    // wait for the first event); openInflightTurn=true renders the replayed
    // in-flight round into its own assistant turn so it doesn't overwrite the
    // last hydrated bubble (the buffer replay carries only the current round).
    autoRunStore.attach(resolved.run_id, resolved.status === "running", true)
  }

  function handleToolCallsPending(
    payload: ToolCallsPendingPayload,
  ): Promise<Record<string, boolean>> {
    const approvalOnly = payload.items.filter((i) => i.requiresApproval)
    if (approvalOnly.length === 0) {
      return Promise.resolve({})
    }
    return new Promise((resolve) => {
      toolApprovalResolver = resolve
      const picks: Record<string, boolean | undefined> = {}
      for (const it of approvalOnly) {
        picks[it.toolCallId] = undefined
      }
      combined.update((s) => ({
        ...s,
        toolApprovalWaiter: { payload: { items: approvalOnly } },
        toolApprovalPicks: picks,
      }))
    })
  }

  function clearToolApprovalState(resolveWithEmpty = true): void {
    if (resolveWithEmpty && toolApprovalResolver) {
      toolApprovalResolver({})
    }
    toolApprovalResolver = null
    combined.update((s) => ({
      ...s,
      toolApprovalWaiter: null,
      toolApprovalPicks: {},
    }))
  }

  function maybeFinishToolApproval(): void {
    const state = get(combined)
    if (!state.toolApprovalWaiter || !toolApprovalResolver) return
    const allDone = state.toolApprovalWaiter.payload.items.every(
      (it) => state.toolApprovalPicks[it.toolCallId] !== undefined,
    )
    if (!allDone) return
    const decisions: Record<string, boolean> = {}
    for (const it of state.toolApprovalWaiter.payload.items) {
      decisions[it.toolCallId] = state.toolApprovalPicks[it.toolCallId] ?? false
    }
    const resolver = toolApprovalResolver
    clearToolApprovalState(false)
    resolver(decisions)
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
