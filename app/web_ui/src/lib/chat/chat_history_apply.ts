import type { ChatMessage, ContextUsage } from "./streaming_chat"

export type LoadedChatSessionDetail = {
  messages: ChatMessage[]
  continuationTraceId: string
  contextUsage: ContextUsage | null
}
