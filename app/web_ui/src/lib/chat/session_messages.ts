import type { components } from "$lib/api_schema"
import {
  chatGenerateId,
  type ChatMessage,
  type ChatMessagePart,
} from "./streaming_chat"

type TraceMessage = components["schemas"]["TraceMessage"]
type TraceToolCall = components["schemas"]["TraceToolCall"]
export type ChatSessionSnapshot = components["schemas"]["ChatSessionSnapshot"]

function extractTextContent(content: TraceMessage["content"]): string {
  if (content == null) return ""
  if (typeof content === "string") return content
  return content
    .map((part) => {
      if (typeof part === "object" && "text" in part) return String(part.text)
      return ""
    })
    .join("")
}

const APP_UI_CONTEXT_RE =
  /<new_app_ui_context>[\s\S]*?<\/new_app_ui_context>\s*/g

export function stripAppUiContext(text: string): string {
  return text.replace(APP_UI_CONTEXT_RE, "")
}

function traceToolCallToPart(tc: TraceToolCall): ChatMessagePart {
  let input: unknown
  try {
    input = JSON.parse(tc.function.arguments)
  } catch {
    input = tc.function.arguments
  }
  return {
    type: `tool-${tc.function.name}`,
    toolCallId: tc.id,
    toolName: tc.function.name,
    input,
  }
}

function buildAssistantParts(msg: TraceMessage): ChatMessagePart[] {
  const parts: ChatMessagePart[] = []
  if (msg.reasoning_content) {
    parts.push({ type: "reasoning", reasoning: msg.reasoning_content })
  }
  const text = extractTextContent(msg.content)
  if (text) {
    parts.push({ type: "text", text })
  }
  if (msg.tool_calls) {
    for (const tc of msg.tool_calls) {
      parts.push(traceToolCallToPart(tc))
    }
  }
  return parts
}

/**
 * Converts a typed ChatSessionSnapshot into UI messages.
 * Sets ``traceId`` on the last assistant message so
 * ``traceIdForNextChatRequest`` can continue the thread.
 */
export function hydrateSessionFromSnapshot(snapshot: ChatSessionSnapshot): {
  messages: ChatMessage[]
  continuationTraceId: string
} {
  const trace = snapshot.task_run.trace ?? []
  const messages: ChatMessage[] = []

  for (const msg of trace) {
    switch (msg.role) {
      case "user": {
        messages.push({
          id: chatGenerateId(),
          role: "user",
          content: stripAppUiContext(extractTextContent(msg.content)),
        })
        break
      }
      case "assistant": {
        const parts = buildAssistantParts(msg)
        if (parts.length === 0) break
        messages.push({
          id: chatGenerateId(),
          role: "assistant",
          parts,
        })
        break
      }
      case "tool": {
        if (!msg.tool_call_id) break
        const output = extractTextContent(msg.content)
        for (let i = messages.length - 1; i >= 0; i--) {
          const prev = messages[i]
          if (prev.role !== "assistant" || !prev.parts) continue
          const toolPart = prev.parts.find(
            (p): p is Extract<ChatMessagePart, { toolCallId: string }> =>
              "toolCallId" in p && p.toolCallId === msg.tool_call_id,
          )
          if (toolPart) {
            prev.parts = prev.parts!.map((p) =>
              "toolCallId" in p && p.toolCallId === msg.tool_call_id
                ? { ...p, output }
                : p,
            )
            break
          }
        }
        break
      }
    }
  }

  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === "assistant") {
      messages[i] = { ...messages[i], traceId: snapshot.id }
      break
    }
  }

  return { messages, continuationTraceId: snapshot.id }
}
