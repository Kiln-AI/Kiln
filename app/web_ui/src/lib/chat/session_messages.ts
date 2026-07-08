import type { components } from "$lib/api_schema"
import {
  chatGenerateId,
  normalizeContextUsage,
  type ChatMessage,
  type ChatMessagePart,
  type ContextUsage,
  type SubagentReportInfo,
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

// Auto mode wraps a message injected mid-burst in a <system-reminder> "side
// note" (see _SIDE_NOTE_REMINDER in the auto runner) before sending it upstream,
// so the framing is persisted in the trace. Strip it on hydration so a reloaded
// transcript shows the user's actual message — matching the live echo, which
// renders the raw content.
const SYSTEM_REMINDER_RE = /<system-reminder>[\s\S]*?<\/system-reminder>\s*/g

export function stripAppUiContext(text: string): string {
  return text.replace(APP_UI_CONTEXT_RE, "")
}

// Strip the internal framing the client/runner prepend to a user message before
// sending it to the model (app-UI context header + auto-mode side-note), so the
// hydrated transcript shows what the user actually typed.
export function stripInternalFraming(text: string): string {
  return text.replace(APP_UI_CONTEXT_RE, "").replace(SYSTEM_REMINDER_RE, "")
}

// A sub-agent completion report the server injected into the parent
// conversation as a user-role message (format_subagent_report server-side).
// The whole message is the frame: attributes then the report body. The open
// tag is matched attribute-by-attribute (not ``[^>]*``) because attribute
// values may contain a literal ``>`` — the server escapes ``"`` but not ``>``.
const SUBAGENT_REPORT_RE =
  /^\s*<subagent_report((?:\s+\w+="[^"]*")*)\s*>\n?([\s\S]*?)\n?<\/subagent_report>\s*$/

// Reverse of the server's _escape_attr (&amp; last so escaped entities in the
// original text don't double-unescape).
function unescapeReportAttr(value: string): string {
  return value
    .replace(/&quot;/g, '"')
    .replace(/&lt;/g, "<")
    .replace(/&amp;/g, "&")
}

/**
 * Parse a ``<subagent_report …>`` frame. Returns the parsed attributes plus the
 * inner report body, or ``null`` when the text is not a report frame (a normal
 * user message). The transcript renders matches as a collapsed report chip.
 */
export function parseSubagentReport(
  text: string,
): { info: SubagentReportInfo; body: string } | null {
  const match = SUBAGENT_REPORT_RE.exec(text)
  if (!match) return null
  const attrs: Record<string, string> = {}
  const attrRe = /(\w+)="([^"]*)"/g
  let attrMatch: RegExpExecArray | null
  while ((attrMatch = attrRe.exec(match[1])) !== null) {
    attrs[attrMatch[1]] = unescapeReportAttr(attrMatch[2])
  }
  return {
    info: {
      id: attrs.id ?? "",
      agentType: attrs.agent_type ?? "",
      status: attrs.status ?? "",
      title: attrs.title ?? "",
    },
    body: match[2],
  }
}

/**
 * Build the UI message for a user-role trace entry: a report chip message when
 * the content is a sub-agent report frame, otherwise a plain user message.
 * Shared by hydration (below) and the live ``user-message`` echo path.
 */
export function userChatMessageFromContent(
  content: string,
  echoId?: string,
): ChatMessage {
  const report = parseSubagentReport(content)
  if (report) {
    return {
      id: chatGenerateId(),
      role: "user",
      content: report.body,
      subagentReport: report.info,
      echoId,
    }
  }
  return { id: chatGenerateId(), role: "user", content, echoId }
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
  contextUsage: ContextUsage | null
} {
  const trace = snapshot.task_run.trace ?? []
  const messages: ChatMessage[] = []

  for (const msg of trace) {
    switch (msg.role) {
      case "user": {
        messages.push(
          userChatMessageFromContent(
            stripInternalFraming(extractTextContent(msg.content)),
          ),
        )
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

  return {
    messages,
    continuationTraceId: snapshot.id,
    contextUsage: normalizeContextUsage(snapshot.context_usage),
  }
}
