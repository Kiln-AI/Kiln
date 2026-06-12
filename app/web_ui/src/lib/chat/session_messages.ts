import type { components } from "$lib/api_schema"
import {
  chatGenerateId,
  type ChatMessage,
  type ChatMessagePart,
  type ToolCallsPendingItem,
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

// Mirrors the libs/core tool name + the app server's defensive cap so a restored
// snapshot renders the same question card the live stream produced.
const ASK_USER_QUESTION_TOOL_NAME = "ask_user_question"
const MAX_SUGGESTED_ANSWERS = 5

function parseAskUserQuestion(input: unknown): {
  question: string
  suggestedAnswers: { answer: string; explanation: string }[]
} {
  const obj =
    input != null && typeof input === "object"
      ? (input as Record<string, unknown>)
      : {}
  const question = typeof obj.question === "string" ? obj.question : ""
  const raw = Array.isArray(obj.suggested_answers) ? obj.suggested_answers : []
  const suggestedAnswers: { answer: string; explanation: string }[] = []
  for (const item of raw) {
    if (suggestedAnswers.length >= MAX_SUGGESTED_ANSWERS) break
    if (item == null || typeof item !== "object") continue
    const answer = (item as { answer?: unknown }).answer
    if (typeof answer !== "string") continue
    const explanation = (item as { explanation?: unknown }).explanation
    suggestedAnswers.push({
      answer,
      explanation: typeof explanation === "string" ? explanation : "",
    })
  }
  return { question, suggestedAnswers }
}

// Map a persisted ask_user_question tool result back to the card's resolution.
// "Chat about this" resolves with the chat signal {"choice":"chat"}; any other
// content is the picked answer's main line.
function askResolutionFromResult(
  content: string,
): { kind: "pick"; answer: string } | { kind: "chat" } {
  try {
    const parsed = JSON.parse(content)
    if (
      parsed != null &&
      typeof parsed === "object" &&
      (parsed as { choice?: unknown }).choice === "chat"
    ) {
      return { kind: "chat" }
    }
  } catch {
    /* not the chat signal; treat as a picked answer */
  }
  return { kind: "pick", answer: content }
}

function traceToolCallToPart(tc: TraceToolCall): ChatMessagePart {
  let input: unknown
  try {
    input = JSON.parse(tc.function.arguments)
  } catch {
    input = tc.function.arguments
  }
  // The ask_user_question tool is a client-rendered question card (architecture
  // §3), not a normal tool block. Reattach re-renders it from the persisted
  // pending call; a later tool result (answer) collapses it to its summary.
  if (tc.function.name === ASK_USER_QUESTION_TOOL_NAME) {
    const { question, suggestedAnswers } = parseAskUserQuestion(input)
    return {
      type: "ask-user-question",
      toolCallId: tc.id,
      question,
      suggestedAnswers,
    }
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
            prev.parts = prev.parts!.map((p) => {
              if (!("toolCallId" in p) || p.toolCallId !== msg.tool_call_id) {
                return p
              }
              // The answer to an ask_user_question resolves its card (a chat
              // signal → "chat"; any other text → the picked answer), not a
              // normal tool output block.
              if (p.type === "ask-user-question") {
                return { ...p, resolution: askResolutionFromResult(output) }
              }
              return { ...p, output }
            })
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

// Tool names that have their own re-attach handling and must NOT be re-surfaced
// as generic tool approvals when dangling:
//  - ask_user_question is re-rendered as its question card (handled by the
//    ask-user-question part + ``pendingQuestionFromMessages``).
//  - enable_auto_mode / disable_auto_mode are auto-mode signal tools; resolving
//    them via the approval box would be wrong, so they are left out of scope.
const APPROVAL_RESURFACE_EXCLUDED_TOOL_NAMES = new Set([
  ASK_USER_QUESTION_TOOL_NAME,
  "enable_auto_mode",
  "disable_auto_mode",
])

function toolInputAsRecord(input: unknown): Record<string, unknown> {
  if (input !== null && typeof input === "object" && !Array.isArray(input)) {
    return input as Record<string, unknown>
  }
  return {}
}

/**
 * Detect DANGLING client tool calls in the latest assistant turn of a hydrated
 * conversation — client-visible tool calls with NO following tool result in the
 * persisted trace (i.e. a ``tool-*`` part whose ``output`` is undefined). These
 * are reconstructed into the ``ToolCallsPendingItem`` shape the EXISTING approval
 * handler expects so the conversation can re-surface the approval box on reattach
 * (history-restore or hard-refresh) and continue via /api/chat/execute-tools.
 *
 * Only the latest assistant turn can hold a live pending approval, so the scan
 * stops at the first assistant message from the end (mirroring
 * ``pendingQuestionFromMessages``). The special intercept tools
 * (``ask_user_question`` / ``enable_auto_mode`` / ``disable_auto_mode``) are
 * excluded — they have their own reattach handling.
 *
 * The persisted trace already carries each tool call's name + arguments (parsed
 * into ``input`` during hydration), so the payload is reconstructed purely from
 * the hydrated messages with no backend round-trip. ``requiresApproval`` is
 * forced true: a dangling client tool call that was awaiting resolution is, by
 * definition, one the user must approve/deny before it can run.
 */
export function pendingApprovalsFromMessages(
  messages: ChatMessage[],
): ToolCallsPendingItem[] {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i]
    if (m.role !== "assistant") continue
    const items: ToolCallsPendingItem[] = []
    for (const part of m.parts ?? []) {
      if (
        typeof part.type !== "string" ||
        !part.type.startsWith("tool-") ||
        !("toolCallId" in part)
      ) {
        continue
      }
      const toolPart = part as Extract<
        ChatMessagePart,
        { type: `tool-${string}` }
      >
      // A persisted tool result hydrates into ``output``; its presence means the
      // call is resolved and nothing should be re-surfaced.
      if (toolPart.output !== undefined) continue
      const toolName = toolPart.toolName ?? ""
      if (APPROVAL_RESURFACE_EXCLUDED_TOOL_NAMES.has(toolName)) continue
      items.push({
        toolCallId: toolPart.toolCallId,
        toolName,
        input: toolInputAsRecord(toolPart.input),
        requiresApproval: true,
      })
    }
    // Only the latest assistant turn can hold live pending approvals.
    return items
  }
  return []
}
