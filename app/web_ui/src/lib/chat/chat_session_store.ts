import { writable, get, type Readable } from "svelte/store"
import {
  streamChat,
  chatGenerateId,
  traceIdForNextChatRequest,
  type ChatMessage,
  type ToolCallsPendingPayload,
} from "./streaming_chat"
import { sessionStorageStore } from "$lib/stores/local_storage_store"
import { base_url } from "$lib/api_client"
import {
  getCurrentAppState,
  buildContextHeader,
  type AppState,
} from "$lib/agent"

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
}

export interface ChatSessionStore extends Readable<ChatSessionState> {
  sendMessage(text: string): void
  stop(): void
  retryLastRequest(): void
  reset(): void
  togglePartCollapsed(key: string, currentlyCollapsed: boolean): void
  applyToolApprovalRun(toolCallId: string): void
  applyToolApprovalSkip(toolCallId: string): void
}

const EMPTY_PERSISTED: PersistedChatSession = {
  messages: [],
  collapsedPartKeys: {},
  lastSentAppState: null,
}

export function createChatSessionStore(
  sessionStorageKey?: string,
): ChatSessionStore {
  const persisted = sessionStorageKey
    ? sessionStorageStore<PersistedChatSession>(sessionStorageKey, {
        ...EMPTY_PERSISTED,
      })
    : writable<PersistedChatSession>({ ...EMPTY_PERSISTED })

  let status: ChatSessionState["status"] = "ready"
  let abortController: AbortController | null = null
  let toolApprovalResolver:
    | ((decisions: Record<string, boolean>) => void)
    | null = null

  const combined = writable<ChatSessionState>({
    ...get(persisted),
    status,
    abortController,
    toolApprovalWaiter: null,
    toolApprovalPicks: {},
  })

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

  function beginStreaming(text: string) {
    removeErrors()
    const currentMessages = get(persisted).messages
    const traceId = traceIdForNextChatRequest(currentMessages)
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

    const controller = new AbortController()
    setRuntimeState("submitted", controller)

    streamChat({
      apiUrl: CHAT_API_URL,
      messages: [apiMessage],
      traceId,
      onToolCallsPending: handleToolCallsPending,
      onAssistantMessage: (update) => {
        if (status !== "streaming") {
          setRuntimeState("streaming", controller)
        }
        updateLastAssistant(update)
      },
      onChatTrace: (traceId) => {
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
      },
      onInlineError: (message, traceId) => {
        const errorMsg: ChatMessage = {
          id: chatGenerateId(),
          role: "error",
          content: message,
          traceId,
        }
        updateMessages((msgs) => [...msgs, errorMsg])
        setRuntimeState("ready", null)
      },
      onFinish: () => {
        setRuntimeState("ready", null)
      },
      onError: (err) => {
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

  function sendMessage(text: string): void {
    const trimmed = text.trim()
    if (!trimmed || status !== "ready") return
    beginStreaming(trimmed)
  }

  function stop(): void {
    if (abortController) {
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
    const userText = msgs[lastUserIdx].content ?? ""
    persisted.update((p) => ({
      ...p,
      messages: p.messages.slice(0, lastUserIdx),
    }))
    beginStreaming(userText)
  }

  function reset(): void {
    if (abortController) {
      abortController.abort()
    }
    clearToolApprovalState()
    persisted.set({
      messages: [],
      collapsedPartKeys: {},
      lastSentAppState: null,
    })
    setRuntimeState("ready", null)
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

  function applyToolApprovalRun(toolCallId: string): void {
    if (!get(combined).toolApprovalWaiter) return
    combined.update((s) => ({
      ...s,
      toolApprovalPicks: { ...s.toolApprovalPicks, [toolCallId]: true },
    }))
    maybeFinishToolApproval()
  }

  function applyToolApprovalSkip(toolCallId: string): void {
    if (!get(combined).toolApprovalWaiter) return
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
    togglePartCollapsed,
    applyToolApprovalRun,
    applyToolApprovalSkip,
  }
}

export const chatSessionStore: ChatSessionStore =
  createChatSessionStore(SESSION_STORAGE_KEY)
