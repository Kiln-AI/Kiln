import type { ChatMessage } from "./streaming_chat"

export type LoadedChatSessionDetail = {
  messages: ChatMessage[]
  continuationTraceId: string
}
