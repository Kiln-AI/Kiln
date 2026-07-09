import type { ChatMessage, ContextUsage } from "./streaming_chat"

export type LoadedChatSessionDetail = {
  messages: ChatMessage[]
  continuationTraceId: string
  contextUsage: ContextUsage | null
  /** The sessions-list join said this conversation is auto-active: the
   * restore path turns the auto indicator on immediately (assumeAutoOn)
   * instead of waiting for the observer's state marker. */
  autoActive?: boolean
}
