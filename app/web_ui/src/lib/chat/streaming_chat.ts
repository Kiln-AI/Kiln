/**
 * Custom streaming chat: parses SSE from the backend (AI SDK protocol JSON events).
 * Does not use @ai-sdk/svelte because we use Svelte 4 and @ai-sdk/svelte uses Svelte 5.
 *
 * There is an ancient version of the lib that works with Svelte 4, but then that forces us
 * to use an old version of the protocol on the backend too, which is not a good idea.
 */

export type ChatMessagePart =
  | { type: "text"; text: string }
  | { type: "reasoning"; reasoning: string }
  | {
      type: `tool-${string}`
      toolCallId: string
      toolName?: string
      input?: unknown
      output?: unknown
    }

export interface ChatMessage {
  id: string
  role: "user" | "assistant" | "system"
  content?: string
  parts?: ChatMessagePart[]
  /** Server-issued id from ``kiln_chat_trace`` for this assistant turn */
  traceId?: string
}

/** Body the backend expects: POST /api/chat */
export interface BackendChatRequest {
  messages: Array<{
    role: string
    content?: string
    parts?: Array<Record<string, unknown>>
  }>
  trace_id?: string
}

function toBackendMessage(m: ChatMessage): BackendChatRequest["messages"][0] {
  if (m.role === "user") {
    return { role: "user", content: m.content ?? "" }
  }
  if (m.role === "assistant" && m.parts?.length) {
    return {
      role: "assistant",
      parts: m.parts.map((p) => {
        if (p.type === "text") return { type: "text", text: p.text }
        if (p.type === "reasoning")
          return { type: "reasoning", reasoning: p.reasoning }
        return {
          type: p.type,
          toolCallId: p.toolCallId,
          toolName: p.toolName,
          input: p.input,
          output: p.output,
        }
      }),
    }
  }
  return { role: m.role, content: m.content ?? "" }
}

/** SSE event from backend (AI SDK stream event shape) */
interface StreamEvent {
  type: string
  delta?: string
  id?: string
  messageId?: string
  toolCallId?: string
  toolName?: string
  input?: unknown
  inputTextDelta?: string
  output?: unknown
  errorText?: string
  trace_id?: string
  messageMetadata?: { finishReason?: string; usage?: unknown }
}

export interface StreamChatOptions {
  apiUrl: string
  messages: ChatMessage[]
  /** Send on continuations so the server can tie the request to prior traces */
  traceId?: string
  onAssistantMessage: (update: (draft: ChatMessage) => void) => void
  /** Fired when upstream sends ``kiln_chat_trace`` (typically end of a turn) */
  onChatTrace?: (traceId: string) => void
  onFinish: () => void
  onError: (error: Error) => void
  signal?: AbortSignal
}

function generateId(): string {
  return `msg-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

/** Latest stored assistant ``traceId`` for continuing the conversation. */
export function traceIdForNextChatRequest(
  msgs: ChatMessage[],
): string | undefined {
  for (let i = msgs.length - 1; i >= 0; i--) {
    const m = msgs[i]
    if (m.role === "assistant" && m.traceId) {
      return m.traceId
    }
  }
  return undefined
}

/**
 * POST to apiUrl with messages, then parse SSE stream and call onAssistantMessage
 * for each event that updates the assistant reply. Calls onFinish when stream ends
 * or onError on failure. Respects signal for abort.
 */
export async function streamChat(options: StreamChatOptions): Promise<void> {
  const {
    apiUrl,
    messages,
    traceId,
    onAssistantMessage,
    onChatTrace,
    onFinish,
    onError,
    signal,
  } = options

  const body: BackendChatRequest = {
    messages: messages.map(toBackendMessage),
  }
  if (traceId) {
    body.trace_id = traceId
  }

  let response: Response
  try {
    response = await fetch(apiUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    })
  } catch (err) {
    if ((err as Error).name === "AbortError") {
      onFinish()
      return
    }
    onError(err instanceof Error ? err : new Error(String(err)))
    return
  }

  if (!response.ok) {
    const text = await response.text()
    onError(
      new Error(
        `Chat API error ${response.status}: ${text || response.statusText}`,
      ),
    )
    return
  }

  const reader = response.body?.getReader()
  if (!reader) {
    onError(new Error("No response body"))
    return
  }

  const decoder = new TextDecoder()
  let buffer = ""

  type PartSlot =
    | { kind: "text"; id: string }
    | { kind: "reasoning"; id: string }
    | { kind: "tool"; id: string }
  const partOrder: PartSlot[] = []
  const textBlocks = new Map<string, string>()
  const reasoningBlocks = new Map<string, string>()
  const toolMap = new Map<
    string,
    {
      type: `tool-${string}`
      toolCallId: string
      toolName?: string
      input?: unknown
      output?: unknown
    }
  >()
  const toolInputBuffer = new Map<string, string>()
  let currentTextId: string | null = null
  let currentReasoningId: string | null = null
  let slotIdCounter = 0
  function nextSlotId(): string {
    slotIdCounter += 1
    return `slot-${slotIdCounter}`
  }

  function flushAssistant() {
    onAssistantMessage((draft) => {
      const next: ChatMessagePart[] = []
      for (const slot of partOrder) {
        if (slot.kind === "text") {
          const text = textBlocks.get(slot.id)
          if (text) next.push({ type: "text", text })
        } else if (slot.kind === "reasoning") {
          const reasoning = reasoningBlocks.get(slot.id)
          if (reasoning) next.push({ type: "reasoning", reasoning })
        } else {
          const tool = toolMap.get(slot.id)
          if (tool) next.push(tool)
        }
      }
      draft.parts = next
    })
  }

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split("\n")
      buffer = lines.pop() ?? ""
      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const payload = line.slice(6).trim()
          if (payload === "[DONE]" || payload === "") continue
          let event: StreamEvent
          try {
            event = JSON.parse(payload) as StreamEvent
          } catch {
            continue
          }
          const typ = event.type
          if (
            typ === "text-start" ||
            (typ === "text-delta" && currentTextId === null)
          ) {
            if (typ === "text-start" && currentTextId !== null) {
              currentTextId = null
            }
            if (currentTextId === null) {
              const id = nextSlotId()
              partOrder.push({ kind: "text", id })
              currentTextId = id
              textBlocks.set(id, "")
            }
          }
          if (typ === "text-delta" && event.delta != null) {
            if (currentTextId === null) {
              const id = nextSlotId()
              partOrder.push({ kind: "text", id })
              currentTextId = id
              textBlocks.set(id, "")
            }
            textBlocks.set(
              currentTextId,
              (textBlocks.get(currentTextId) ?? "") + event.delta,
            )
            flushAssistant()
          } else if (typ === "text-end") {
            currentTextId = null
          } else if (
            typ === "reasoning-start" ||
            (typ === "reasoning-delta" && currentReasoningId === null)
          ) {
            if (typ === "reasoning-start" && currentReasoningId !== null) {
              currentReasoningId = null
            }
            if (currentReasoningId === null) {
              const id = nextSlotId()
              partOrder.push({ kind: "reasoning", id })
              currentReasoningId = id
              reasoningBlocks.set(id, "")
            }
          }
          if (typ === "reasoning-delta" && event.delta != null) {
            if (currentReasoningId === null) {
              const id = nextSlotId()
              partOrder.push({ kind: "reasoning", id })
              currentReasoningId = id
              reasoningBlocks.set(id, "")
            }
            reasoningBlocks.set(
              currentReasoningId,
              (reasoningBlocks.get(currentReasoningId) ?? "") + event.delta,
            )
            flushAssistant()
          } else if (typ === "reasoning-end") {
            currentReasoningId = null
          } else if (typ === "tool-input-start" && event.toolCallId) {
            const key = event.toolCallId
            if (!toolMap.has(key)) {
              partOrder.push({ kind: "tool", id: key })
              toolMap.set(key, {
                type: `tool-${event.toolName ?? "unknown"}`,
                toolCallId: event.toolCallId,
                toolName: event.toolName,
              })
            }
            flushAssistant()
          } else if (
            typ === "tool-input-delta" &&
            event.toolCallId &&
            event.inputTextDelta != null
          ) {
            const key = event.toolCallId
            const prev = toolInputBuffer.get(key) ?? ""
            toolInputBuffer.set(key, prev + event.inputTextDelta)
            let entry = toolMap.get(key)
            if (!entry) {
              partOrder.push({ kind: "tool", id: key })
              entry = {
                type: `tool-${event.toolName ?? "unknown"}`,
                toolCallId: event.toolCallId,
                toolName: event.toolName,
              }
              toolMap.set(key, entry)
            }
            try {
              entry.input = JSON.parse(
                toolInputBuffer.get(key) ?? "{}",
              ) as unknown
            } catch {
              entry.input = toolInputBuffer.get(key)
            }
            flushAssistant()
          } else if (typ === "tool-input-available" && event.toolCallId) {
            const key = event.toolCallId
            let entry = toolMap.get(key)
            if (!entry) {
              partOrder.push({ kind: "tool", id: key })
              entry = {
                type: `tool-${event.toolName ?? "unknown"}`,
                toolCallId: event.toolCallId,
                toolName: event.toolName,
                input: event.input,
              }
              toolMap.set(key, entry)
            } else {
              entry.input = event.input
            }
            toolInputBuffer.delete(key)
            flushAssistant()
          } else if (typ === "tool-output-available" && event.toolCallId) {
            const entry = toolMap.get(event.toolCallId)
            if (entry) {
              entry.output = event.output
              flushAssistant()
            }
          } else if (typ === "tool-output-error" && event.toolCallId) {
            const entry = toolMap.get(event.toolCallId)
            if (entry) {
              entry.output = { error: event.errorText }
              flushAssistant()
            }
          } else if (typ === "kiln_chat_trace") {
            const tid = event.trace_id
            if (typeof tid === "string" && tid) {
              onChatTrace?.(tid)
            }
          }
        }
      }
    }
    onFinish()
  } catch (err) {
    if ((err as Error).name === "AbortError") {
      onFinish()
      return
    }
    onError(err instanceof Error ? err : new Error(String(err)))
  }
}

export { generateId as chatGenerateId }
