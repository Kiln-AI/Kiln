import type { ChatMessage, ToolCallsPendingPayload } from "./streaming_chat"

export type LoadedChatSessionDetail = {
  messages: ChatMessage[]
  continuationTraceId: string
}

export type ChatStatePatch = {
  messages: ChatMessage[]
  continuationTraceId: string | undefined
  input: string
  collapsedPartKeys: Record<string, boolean>
  reasoningPartStartTimes: Record<string, number>
  reasoningPartEndTimes: Record<string, number>
  lastSeenLastPartKey: null
  toolApprovalWaiter: {
    payload: ToolCallsPendingPayload
    resolve: (d: Record<string, boolean>) => void
  } | null
  toolApprovalPicks: Record<string, boolean | undefined>
  status: "ready"
  abortController: null
}

export function patchChatFromLoadedSession(
  detail: LoadedChatSessionDetail,
): ChatStatePatch {
  return {
    messages: detail.messages,
    continuationTraceId: detail.continuationTraceId,
    input: "",
    collapsedPartKeys: {},
    reasoningPartStartTimes: {},
    reasoningPartEndTimes: {},
    lastSeenLastPartKey: null,
    toolApprovalWaiter: null,
    toolApprovalPicks: {},
    status: "ready",
    abortController: null,
  }
}
