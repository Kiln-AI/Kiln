import type { ChatMessage, ContextUsage } from "./streaming_chat"

export type LoadedChatSessionDetail = {
  messages: ChatMessage[]
  /**
   * The history row's conversation key (a live session id or an upstream
   * root id). The apply handler passes it to loadSession/ensure; the desktop
   * resolves it.
   */
  sessionId: string
  /** The session's durable upstream id (`session_meta.root_id`) when known —
   * persisted as the restart-recovery key. */
  rootId: string | null
  contextUsage: ContextUsage | null
  /** The sessions-list join said this conversation is auto-active: the
   * restore path turns the auto indicator on immediately (assumeAutoOn)
   * instead of waiting for the observer's state marker. */
  autoActive?: boolean
}
