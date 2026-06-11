import { writable, get, type Readable } from "svelte/store"
import posthog from "posthog-js"
import {
  streamChat,
  resumePendingToolCalls,
  chatGenerateId,
  traceIdForNextChatRequest,
  type ChatMessage,
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
import { hydrateSessionFromSnapshot } from "./session_messages"
import { base_url, client } from "$lib/api_client"
import {
  getCurrentAppState,
  buildContextHeader,
  type AppState,
} from "$lib/agent"
import { chat_cost_disclaimer_acknowledged } from "$lib/stores"

const CHAT_API_URL = `${base_url}/api/chat`
const SESSION_STORAGE_KEY = "kiln_chat_session"

export interface PersistedChatSession {
  messages: ChatMessage[]
  collapsedPartKeys: Record<string, boolean>
  lastSentAppState: AppState | null
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
   * A server-owned auto-mode burst is actively running. Decoupled from
   * ``status`` (which tracks the interactive client stream) so the chat view
   * can drive the SAME loading affordances during auto bursts while keeping the
   * input usable for inject-on-send.
   */
  autoWorking: boolean
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
  stop(): void
  retryLastRequest(): void
  reset(): void
  loadSession(messages: ChatMessage[], continuationTraceId: string): void
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
  onConsentNeeded: (() => Promise<boolean>) | null
  onAutoModeConsentNeeded: AutoModeConsentDecision | null
}

const EMPTY_PERSISTED: PersistedChatSession = {
  messages: [],
  collapsedPartKeys: {},
  lastSentAppState: null,
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
    autoWorking: false,
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
    }))
  }

  // Append an echoed (injected) user message, then a fresh assistant turn so the
  // burst it triggers renders into a new turn — mirrors the server's
  // render-immediately + replay model for inject-on-send (functional spec §4.3.2).
  function appendEchoedUserMessage(content: string) {
    removeErrors()
    updateMessages((msgs) => [
      ...msgs,
      { id: chatGenerateId(), role: "user", content },
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
    onInlineError: (message, traceId, code) =>
      pushInlineError(message, traceId, code),
    onToolExecutionStart: () =>
      combined.update((s) => ({ ...s, toolExecuting: true })),
    onToolExecutionEnd: () =>
      combined.update((s) => ({ ...s, toolExecuting: false })),
    onShowActivityIndicator: (show) =>
      combined.update((s) => ({ ...s, showActivityIndicator: show })),
    // Burst liveness drives the same thinking-dots/animated-icon path as the
    // interactive stream (the loading-indicator fix); the input stays usable.
    onWorkingChange: (working) =>
      combined.update((s) => ({ ...s, autoWorking: working })),
    onUserMessage: appendEchoedUserMessage,
    // Idle: a burst ended but the flag stays on. Stop the working affordances;
    // the green indicator persists (it binds to autoModeOn, not autoWorking).
    onAutoModeIdle: () =>
      combined.update((s) => ({
        ...s,
        toolExecuting: false,
        showActivityIndicator: false,
        autoWorking: false,
      })),
    onAutoModeOff: () =>
      combined.update((s) => ({
        ...s,
        toolExecuting: false,
        showActivityIndicator: false,
        autoWorking: false,
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
      onFinish: () => {
        if (isStale()) return
        combined.update((s) => ({
          ...s,
          toolExecuting: false,
          showActivityIndicator: false,
        }))
      },
      onError: (err) => {
        if (isStale()) return
        combined.update((s) => ({
          ...s,
          toolExecuting: false,
          showActivityIndicator: false,
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
      onAutoModeConsentRequired: async (payload) => {
        if (isStale()) return
        await handleAutoModeConsent(payload)
      },
      onInlineError: (message, traceId, code) => {
        if (isStale()) return
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
        }))
        setRuntimeState("ready", null)
      },
      onError: (err) => {
        if (isStale()) return
        combined.update((s) => ({
          ...s,
          toolExecuting: false,
          showActivityIndicator: false,
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
    const traceId = payload.traceId ?? continuationTraceId
    if (!traceId) return
    const accepted = onAutoModeConsentNeeded
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

  async function sendMessage(text: string): Promise<boolean> {
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
    })
    combined.update((s) => ({
      ...s,
      toolExecuting: false,
      showActivityIndicator: false,
    }))
    setRuntimeState("ready", null)
  }

  function loadSession(messages: ChatMessage[], traceId: string): void {
    if (abortController) {
      abortController.abort()
    }
    // Detach any prior run's observer before hydrating a different conversation.
    // If the loaded conversation is itself auto-active, the caller re-attaches
    // right after (chat_history.selectSession), which happens after this.
    autoRunStore.detach()
    clearToolApprovalState()
    continuationTraceId = traceId
    persisted.set({ messages, collapsedPartKeys: {}, lastSentAppState: null })
    combined.update((s) => ({
      ...s,
      toolExecuting: false,
      showActivityIndicator: false,
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

    const resolved = await autoRunStore.resolve(storedTraceId)
    // Not active (404 / error): leave the normal restored-from-sessionStorage
    // state untouched.
    if (!resolved) return

    // We now know it's an active run. Show a transient "reconnecting…" affordance
    // while we hydrate → attach so the transcript doesn't look done/idle before
    // liveness is known. attach() keeps it on through the connecting phase and
    // clears it once the stream is established; off/idle/error paths also clear it.
    autoRunStore.beginReconnect()

    // Hydrate from the run's CURRENT leaf so the user catches up on rounds that
    // completed while the tab was gone, then attach for live events + buffer
    // replay + the indicator/working state.
    try {
      const { data: snapshot, error } = await client.GET(
        "/api/chat/sessions/{session_id}",
        { params: { path: { session_id: resolved.current_trace_id } } },
      )
      // A structured error / empty snapshot must NOT short-circuit the attach:
      // resolve() already proved the run is live, so fall through to attach on
      // the restored (stale) view — same as the thrown-exception fallback below.
      // Returning here would leave the conversation looking dead (no indicator,
      // no live stream) in the snapshot-error case while the throw case
      // correctly re-attaches.
      if (!error && snapshot) {
        const { messages, continuationTraceId: traceId } =
          hydrateSessionFromSnapshot(snapshot)
        // loadSession detaches any prior observer, sets the messages + trace id,
        // and resets runtime state — identical to the history-restore apply path.
        loadSession(messages, traceId)
      }
    } catch {
      // Hydration failed (network/parse). Fall back: still attach so the user at
      // least gets the live indicator + events on the restored (stale) view.
    }
    // Re-assert reconnecting: loadSession() detaches the prior observer, which
    // clears the flag, so re-mark it for the brief connecting window. attach()
    // clears it on open / first event / off.
    autoRunStore.beginReconnect()
    // Drive the working sub-state from the resolved status so the thinking
    // indicator shows immediately when the run is RUNNING (no wait for the first
    // event); the on-subscribe state marker confirms / corrects it.
    autoRunStore.attach(resolved.run_id, resolved.status === "running")
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

  function togglePartCollapsed(key: string, currentlyCollapsed: boolean): void {
    persisted.update((p) => ({
      ...p,
      collapsedPartKeys: { ...p.collapsedPartKeys, [key]: !currentlyCollapsed },
    }))
  }

  return {
    subscribe: combined.subscribe,
    sendMessage,
    stop,
    retryLastRequest,
    reset,
    loadSession,
    resyncOnLoad,
    togglePartCollapsed,
    pushInlineError: (message: string) => pushInlineError(message),
    applyToolApprovalRun,
    applyToolApprovalSkip,
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
