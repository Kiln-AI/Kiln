import type { ChatMessage } from "./streaming_chat"

export type LoadedChatSessionDetail = {
  messages: ChatMessage[]
  continuationTraceId: string
  /**
   * The restored row has a live, server-owned auto run that the caller will
   * re-attach right after applying. When true, the apply path must NOT
   * re-surface dangling client tool calls as approvals: the live observer
   * stream / buffer-replay is the source of truth (auto mode auto-approves).
   */
  autoActive?: boolean
}
