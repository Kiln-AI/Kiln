/**
 * Custom streaming chat: parses SSE from the backend (AI SDK protocol JSON events).
 * Does not use @ai-sdk/svelte because we use Svelte 4 and @ai-sdk/svelte uses Svelte 5.
 *
 * There is an ancient version of the lib that works with Svelte 4, but then that forces us
 * to use an old version of the protocol on the backend too, which is not a good idea.
 */

import { CHAT_CLIENT_VERSION_TOO_OLD } from "$lib/error_codes"

/** One suggested answer the model offers for an ``ask_user_question`` call. */
export interface SuggestedAnswer {
  answer: string
  explanation: string
}

/**
 * How a surfaced ``ask_user_question`` card was resolved. ``pick`` carries the
 * chosen answer's main line; ``chat`` records that the user chose to chat. Absent
 * while the question is still pending.
 */
export type AskUserQuestionResolution =
  | { kind: "pick"; answer: string }
  | { kind: "chat" }

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
  | {
      type: "ask-user-question"
      toolCallId: string
      question: string
      suggestedAnswers: SuggestedAnswer[]
      /** Set once the user picks an answer or chooses to chat. */
      resolution?: AskUserQuestionResolution
    }

export interface ChatMessage {
  id: string
  role: "user" | "assistant" | "system" | "error"
  content?: string
  parts?: ChatMessagePart[]
  /** Server-issued id from ``kiln_chat_trace`` for this assistant turn */
  traceId?: string
  /** Machine-readable error code from upstream (e.g. ``CHAT_CLIENT_VERSION_TOO_OLD``) */
  errorCode?: string
}

/** Body for POST /api/chat: typically one new user message plus optional trace_id for continuation. */
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
      parts: m.parts
        // The ask-user-question card is a client-rendered surface for an
        // intercepted tool call; it is resolved server-side via the answer
        // endpoint (continuation keys off trace_id), so it never round-trips.
        .filter((p) => p.type !== "ask-user-question")
        .map((p) => {
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
export interface StreamEvent {
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
  message?: string
  code?: string
  messageMetadata?: { finishReason?: string; usage?: unknown }
  items?: ToolCallsPendingItem[]
  tool_count?: number
  /** ``auto-mode-consent-required`` carries the enable call + siblings */
  enable_tool_call_id?: string
  reason?: string | null
  sibling_tool_calls?: ToolCallsPendingItem[]
  /** ``auto-mode-on`` / ``auto-mode-off`` / ``auto-mode-idle`` carry the run id (and reason) */
  run_id?: string
  /** ``user-message`` echo carries the injected user message content */
  content?: string
  /** ``auto-mode-state`` (Phase 9) on-subscribe liveness snapshot */
  flag_on?: boolean
  working?: boolean
  /** ``ask-user-question`` carries the question + the model's suggested answers */
  question?: string
  suggested_answers?: Array<{ answer?: unknown; explanation?: unknown }>
}

/** Payload of the ``ask-user-question`` event (architecture §3). */
export interface AskUserQuestionPayload {
  traceId: string | null
  toolCallId: string
  question: string
  suggestedAnswers: SuggestedAnswer[]
}

/** Defensive cap mirroring the app server (functional spec §3.4). */
const MAX_SUGGESTED_ANSWERS = 5

/** Map a raw ``ask-user-question`` event to its typed payload. */
export function askUserQuestionPayloadFromEvent(
  event: StreamEvent,
): AskUserQuestionPayload {
  const raw = Array.isArray(event.suggested_answers)
    ? event.suggested_answers
    : []
  const suggestedAnswers: SuggestedAnswer[] = []
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
  return {
    traceId: event.trace_id ?? null,
    toolCallId: event.toolCallId ?? "",
    question: typeof event.question === "string" ? event.question : "",
    suggestedAnswers,
  }
}

export interface ToolCallsPendingItem {
  toolCallId: string
  toolName: string
  input: unknown
  requiresApproval: boolean
  permission?: string
  approvalDescription?: string
}

export interface ToolCallsPendingPayload {
  items: ToolCallsPendingItem[]
}

/**
 * Payload of the ``auto-mode-consent-required`` event. The interactive stream
 * emits this (then ends) when the model calls ``enable_auto_mode``; the UI must
 * gate auto-mode behind explicit consent.
 */
export interface AutoModeConsentRequiredPayload {
  traceId: string | null
  enableToolCallId: string
  reason: string | null
  siblingToolCalls: ToolCallsPendingItem[]
}

export interface StreamChatOptions {
  apiUrl: string
  messages: ChatMessage[]
  /** Prior-turn id from kiln_chat_trace; send with the new user message only */
  traceId?: string
  onAssistantMessage: (update: (draft: ChatMessage) => void) => void
  /** Fired when upstream sends ``kiln_chat_trace`` (typically end of a turn) */
  onChatTrace?: (traceId: string) => void
  /** Fired when backend sends an inline error event */
  onInlineError?: (message: string, traceId?: string, code?: string) => void
  /**
   * After ``tool-calls-pending`` the stream ends; return whether to run each
   * tool that requires approval (toolCallId → allowed).
   */
  onToolCallsPending?: (
    payload: ToolCallsPendingPayload,
  ) => Promise<Record<string, boolean>>
  onToolExecutionStart?: (toolCount: number) => void
  onToolExecutionEnd?: (toolCount: number) => void
  onShowActivityIndicator?: (show: boolean) => void
  /**
   * After ``auto-mode-consent-required`` the stream ends; the handler decides
   * whether to enable auto mode (accept) or resume interactively (decline).
   * Both outcomes are handled outside this stream, so it simply returns.
   */
  onAutoModeConsentRequired?: (
    payload: AutoModeConsentRequiredPayload,
  ) => void | Promise<void>
  /**
   * After ``ask-user-question`` the interactive stream ends; the handler records
   * the pending question + gates input. Resolution continues out-of-band via
   * ``POST /api/chat/ask/answer`` (architecture §3).
   */
  onAskUserQuestion?: (payload: AskUserQuestionPayload) => void
  onFinish: () => void
  onError: (error: Error) => void
  signal?: AbortSignal
}

/** ``POST /api/chat/execute-tools`` URL for a given ``POST /api/chat`` URL. */
export function chatExecuteToolsUrl(chatApiUrl: string): string {
  const trimmed = chatApiUrl.replace(/\/$/, "")
  return `${trimmed}/execute-tools`
}

function generateId(): string {
  return `msg-${crypto.randomUUID()}`
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

type PartSlot =
  | { kind: "text"; id: string }
  | { kind: "reasoning"; id: string }
  | { kind: "tool"; id: string }
  | { kind: "ask"; id: string }

export interface StreamEventProcessorOptions {
  onAssistantMessage: (update: (draft: ChatMessage) => void) => void
  onChatTrace?: (traceId: string) => void
  onInlineError?: (message: string, traceId?: string, code?: string) => void
  onToolExecutionStart?: (toolCount: number) => void
  onToolExecutionEnd?: (toolCount: number) => void
  onShowActivityIndicator?: (show: boolean) => void
  /**
   * The model called ``ask_user_question`` (architecture §3): a question card is
   * rendered inline and input must be gated until the user answers. Fired from
   * BOTH the interactive ``streamChat`` reader and the auto observer path.
   */
  onAskUserQuestion?: (payload: AskUserQuestionPayload) => void
}

export class StreamEventProcessor {
  private partOrder: PartSlot[] = []
  private textBlocks = new Map<string, string>()
  private reasoningBlocks = new Map<string, string>()
  private toolMap = new Map<
    string,
    {
      type: `tool-${string}`
      toolCallId: string
      toolName?: string
      input?: unknown
      output?: unknown
    }
  >()
  private askMap = new Map<
    string,
    {
      type: "ask-user-question"
      toolCallId: string
      question: string
      suggestedAnswers: SuggestedAnswer[]
      resolution?: AskUserQuestionResolution
    }
  >()
  private toolInputBuffer = new Map<string, string>()
  private currentTextId: string | null = null
  private currentReasoningId: string | null = null
  private slotIdCounter = 0

  private onAssistantMessage: (update: (draft: ChatMessage) => void) => void
  private onChatTrace?: (traceId: string) => void
  private onInlineError?: (
    message: string,
    traceId?: string,
    code?: string,
  ) => void
  private onToolExecutionStart?: (toolCount: number) => void
  private onToolExecutionEnd?: (toolCount: number) => void
  private onShowActivityIndicator?: (show: boolean) => void
  private onAskUserQuestion?: (payload: AskUserQuestionPayload) => void

  private HANDLERS: Record<string, (event: StreamEvent) => void>

  constructor(opts: StreamEventProcessorOptions) {
    this.onAssistantMessage = opts.onAssistantMessage
    this.onChatTrace = opts.onChatTrace
    this.onInlineError = opts.onInlineError
    this.onToolExecutionStart = opts.onToolExecutionStart
    this.onToolExecutionEnd = opts.onToolExecutionEnd
    this.onShowActivityIndicator = opts.onShowActivityIndicator
    this.onAskUserQuestion = opts.onAskUserQuestion

    this.HANDLERS = {
      "text-start": (e) => {
        this.onShowActivityIndicator?.(false)
        this.handleTextStart(e)
      },
      "text-delta": (e) => this.handleTextDelta(e),
      "text-end": () => {
        this.onShowActivityIndicator?.(true)
        this.handleTextEnd()
      },
      "reasoning-start": () => {
        this.onShowActivityIndicator?.(true)
        this.handleReasoningStart()
      },
      "reasoning-delta": (e) => this.handleReasoningDelta(e),
      "reasoning-end": () => this.handleReasoningEnd(),
      "tool-input-start": (e) => {
        this.onShowActivityIndicator?.(true)
        this.handleToolInputStart(e)
      },
      "tool-input-delta": (e) => this.handleToolInputDelta(e),
      "tool-input-available": (e) => {
        this.onShowActivityIndicator?.(true)
        this.handleToolInputAvailable(e)
      },
      "tool-output-available": (e) => this.handleToolOutputAvailable(e),
      "tool-output-error": (e) => this.handleToolOutputError(e),
      "ask-user-question": (e) => {
        this.onShowActivityIndicator?.(false)
        this.handleAskUserQuestion(e)
      },
      kiln_chat_trace: (e) => this.handleChatTrace(e),
      "kiln-tool-execution-start": (e) => {
        this.onShowActivityIndicator?.(true)
        this.onToolExecutionStart?.(e.tool_count ?? 0)
      },
      "kiln-tool-execution-end": (e) =>
        this.onToolExecutionEnd?.(e.tool_count ?? 0),
      error: (e) => this.handleError(e),
    }
  }

  handleEvent(event: StreamEvent): void {
    const handler = this.HANDLERS[event.type]
    if (handler) {
      handler(event)
    }
  }

  private nextSlotId(): string {
    this.slotIdCounter += 1
    return `slot-${this.slotIdCounter}`
  }

  private flushAssistant() {
    this.onAssistantMessage((draft) => {
      const next: ChatMessagePart[] = []
      for (const slot of this.partOrder) {
        if (slot.kind === "text") {
          const text = this.textBlocks.get(slot.id)
          if (text) next.push({ type: "text", text })
        } else if (slot.kind === "reasoning") {
          const reasoning = this.reasoningBlocks.get(slot.id)
          if (reasoning) next.push({ type: "reasoning", reasoning })
        } else if (slot.kind === "ask") {
          const ask = this.askMap.get(slot.id)
          if (ask) next.push(ask)
        } else {
          const tool = this.toolMap.get(slot.id)
          if (tool) next.push(tool)
        }
      }
      draft.parts = next
    })
  }

  private ensureTextSlot(): void {
    if (this.currentTextId === null) {
      const id = this.nextSlotId()
      this.partOrder.push({ kind: "text", id })
      this.currentTextId = id
      this.textBlocks.set(id, "")
    }
  }

  private ensureReasoningSlot(): void {
    if (this.currentReasoningId === null) {
      const id = this.nextSlotId()
      this.partOrder.push({ kind: "reasoning", id })
      this.currentReasoningId = id
      this.reasoningBlocks.set(id, "")
    }
  }

  private ensureToolSlot(key: string, event: StreamEvent): void {
    if (!this.toolMap.has(key)) {
      this.partOrder.push({ kind: "tool", id: key })
      this.toolMap.set(key, {
        type: `tool-${event.toolName ?? "unknown"}`,
        toolCallId: key,
        toolName: event.toolName,
      })
    }
  }

  // -- Individual handlers --

  private handleTextStart(_event: StreamEvent): void {
    if (this.currentTextId !== null) {
      this.currentTextId = null
    }
    this.ensureTextSlot()
  }

  private handleTextDelta(event: StreamEvent): void {
    if (this.currentTextId === null) {
      this.ensureTextSlot()
    }
    if (event.delta != null && this.currentTextId !== null) {
      this.textBlocks.set(
        this.currentTextId,
        (this.textBlocks.get(this.currentTextId) ?? "") + event.delta,
      )
      this.flushAssistant()
    }
  }

  private handleTextEnd(): void {
    this.currentTextId = null
  }

  private handleReasoningStart(): void {
    if (this.currentReasoningId !== null) {
      this.currentReasoningId = null
    }
    this.ensureReasoningSlot()
  }

  private handleReasoningDelta(event: StreamEvent): void {
    if (this.currentReasoningId === null) {
      this.ensureReasoningSlot()
    }
    if (event.delta != null && this.currentReasoningId !== null) {
      this.reasoningBlocks.set(
        this.currentReasoningId,
        (this.reasoningBlocks.get(this.currentReasoningId) ?? "") + event.delta,
      )
      this.flushAssistant()
    }
  }

  private handleReasoningEnd(): void {
    this.currentReasoningId = null
  }

  private handleToolInputStart(event: StreamEvent): void {
    if (!event.toolCallId) return
    this.ensureToolSlot(event.toolCallId, event)
    this.flushAssistant()
  }

  private handleToolInputDelta(event: StreamEvent): void {
    if (!event.toolCallId || event.inputTextDelta == null) return
    const key = event.toolCallId
    const prev = this.toolInputBuffer.get(key) ?? ""
    this.toolInputBuffer.set(key, prev + event.inputTextDelta)
    this.ensureToolSlot(key, event)
    const entry = this.toolMap.get(key)!
    try {
      entry.input = JSON.parse(this.toolInputBuffer.get(key) ?? "{}") as unknown
    } catch {
      entry.input = this.toolInputBuffer.get(key)
    }
    this.flushAssistant()
  }

  private handleToolInputAvailable(event: StreamEvent): void {
    if (!event.toolCallId) return
    const key = event.toolCallId
    let entry = this.toolMap.get(key)
    if (!entry) {
      this.partOrder.push({ kind: "tool", id: key })
      entry = {
        type: `tool-${event.toolName ?? "unknown"}`,
        toolCallId: event.toolCallId,
        toolName: event.toolName,
        input: event.input,
      }
      this.toolMap.set(key, entry)
    } else {
      entry.input = event.input
    }
    this.toolInputBuffer.delete(key)
    this.flushAssistant()
  }

  private handleToolOutputAvailable(event: StreamEvent): void {
    if (!event.toolCallId) return
    const entry = this.toolMap.get(event.toolCallId)
    if (entry) {
      entry.output = event.output
      this.flushAssistant()
    }
  }

  private handleToolOutputError(event: StreamEvent): void {
    if (!event.toolCallId) return
    const entry = this.toolMap.get(event.toolCallId)
    if (entry) {
      entry.output = { error: event.errorText }
      this.flushAssistant()
    }
  }

  private handleAskUserQuestion(event: StreamEvent): void {
    const payload = askUserQuestionPayloadFromEvent(event)
    if (!payload.toolCallId) return
    const key = payload.toolCallId
    if (!this.askMap.has(key)) {
      this.partOrder.push({ kind: "ask", id: key })
    }
    this.askMap.set(key, {
      type: "ask-user-question",
      toolCallId: payload.toolCallId,
      question: payload.question,
      suggestedAnswers: payload.suggestedAnswers,
      resolution: this.askMap.get(key)?.resolution,
    })
    this.flushAssistant()
    this.onAskUserQuestion?.(payload)
  }

  private handleChatTrace(event: StreamEvent): void {
    const tid = event.trace_id
    if (typeof tid === "string" && tid) {
      this.onChatTrace?.(tid)
    }
  }

  private handleError(event: StreamEvent): void {
    this.onInlineError?.(
      event.message ?? "An error occurred.",
      event.trace_id,
      event.code,
    )
  }
}

async function drainReader(
  reader: ReadableStreamDefaultReader<Uint8Array>,
): Promise<void> {
  while (true) {
    const { done } = await reader.read()
    if (done) break
  }
}

function toolInputAsRecord(input: unknown): Record<string, unknown> {
  if (input !== null && typeof input === "object" && !Array.isArray(input)) {
    return input as Record<string, unknown>
  }
  return {}
}

/** Map a raw ``auto-mode-consent-required`` event to its typed payload. */
export function autoModeConsentPayloadFromEvent(
  event: StreamEvent,
): AutoModeConsentRequiredPayload {
  return {
    traceId: event.trace_id ?? null,
    enableToolCallId: event.enable_tool_call_id ?? "",
    reason: event.reason ?? null,
    siblingToolCalls: Array.isArray(event.sibling_tool_calls)
      ? event.sibling_tool_calls
      : [],
  }
}

/**
 * Read an SSE byte stream, JSON-parse ``data:`` lines, and dispatch each event.
 * ``onControlEvent`` is consulted first; if it returns ``true`` the event is
 * considered handled and not forwarded to the processor. Used by the auto-run
 * decline-resume path (interactive stream) and shareable by any reader-based
 * SSE consumer. Resolves when the stream ends (``done``).
 */
export async function consumeSseStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  processor: StreamEventProcessor,
  onControlEvent?: (event: StreamEvent) => boolean,
): Promise<void> {
  const decoder = new TextDecoder()
  let buffer = ""
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split("\n")
    buffer = lines.pop() ?? ""
    for (const line of lines) {
      if (!line.startsWith("data: ")) continue
      const payload = line.slice(6).trim()
      if (payload === "[DONE]" || payload === "") continue
      let event: StreamEvent
      try {
        event = JSON.parse(payload) as StreamEvent
      } catch {
        continue
      }
      if (onControlEvent?.(event)) continue
      processor.handleEvent(event)
    }
  }
}

// ---------------------------------------------------------------------------
// streamChat
// ---------------------------------------------------------------------------

/**
 * POST to apiUrl with the request messages (usually one user turn) and optional trace_id,
 * then parse SSE and call onAssistantMessage for assistant updates. Respects signal for abort.
 */
export async function streamChat(options: StreamChatOptions): Promise<void> {
  const {
    apiUrl,
    messages,
    traceId,
    onAssistantMessage,
    onChatTrace,
    onInlineError,
    onToolCallsPending,
    onToolExecutionStart,
    onToolExecutionEnd,
    onShowActivityIndicator,
    onAutoModeConsentRequired,
    onAskUserQuestion,
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
    let code: string | undefined
    try {
      const parsed = JSON.parse(text)
      code = parsed?.code ?? parsed?.message?.code
    } catch {
      /* not JSON */
    }
    if (code === CHAT_CLIENT_VERSION_TOO_OLD) {
      onInlineError?.(
        "Please update the Kiln desktop app to continue using chat.",
        undefined,
        code,
      )
    } else {
      onError(
        new Error(
          `Chat API error ${response.status}: ${text || response.statusText}`,
        ),
      )
    }
    return
  }

  const initialReader = response.body?.getReader()
  if (!initialReader) {
    onError(new Error("No response body"))
    return
  }

  const decoder = new TextDecoder()
  const executeToolsUrl = chatExecuteToolsUrl(apiUrl)
  let currentTraceId: string | undefined = traceId
  let reader: ReadableStreamDefaultReader<Uint8Array> = initialReader
  let buffer = ""

  const processor = new StreamEventProcessor({
    onAssistantMessage,
    onChatTrace: (tid) => {
      currentTraceId = tid
      onChatTrace?.(tid)
    },
    onInlineError,
    onToolExecutionStart,
    onToolExecutionEnd,
    onShowActivityIndicator,
    onAskUserQuestion,
  })

  try {
    outer: while (true) {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break outer
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
            if (event.type === "auto-mode-consent-required") {
              // The interactive stream ends here; consent (accept → enable,
              // decline → resume) is handled by the caller outside this stream.
              if (onAutoModeConsentRequired) {
                await onAutoModeConsentRequired(
                  autoModeConsentPayloadFromEvent(event),
                )
              }
              onFinish()
              return
            }
            if (event.type === "ask-user-question") {
              // The model asked a question: render the card (via the processor)
              // and END the stream (same pattern as auto-mode-consent-required).
              // Resolution continues out-of-band via /api/chat/ask/answer.
              processor.handleEvent(event)
              onFinish()
              return
            }
            if (event.type === "tool-calls-pending") {
              const items = event.items
              if (!Array.isArray(items) || items.length === 0) {
                onError(
                  new Error("Invalid tool-calls-pending event from server"),
                )
                return
              }
              if (!currentTraceId) {
                onError(
                  new Error(
                    "Missing trace id for tool execution; wait for chat trace before tools.",
                  ),
                )
                return
              }
              let decisions: Record<string, boolean>
              if (onToolCallsPending) {
                decisions = await onToolCallsPending({ items })
              } else {
                decisions = {}
                for (const it of items) {
                  if (
                    it.requiresApproval &&
                    typeof it.toolCallId === "string"
                  ) {
                    decisions[it.toolCallId] = false
                  }
                }
              }
              const decisionsPayload: Record<string, boolean> = {}
              for (const it of items) {
                if (it.requiresApproval && typeof it.toolCallId === "string") {
                  decisionsPayload[it.toolCallId] =
                    decisions[it.toolCallId] ?? false
                }
              }
              const toolCallsPayload = items.map((it) => ({
                toolCallId: it.toolCallId,
                toolName: it.toolName,
                input: toolInputAsRecord(it.input),
                requiresApproval: Boolean(it.requiresApproval),
              }))
              let postRes: Response
              try {
                postRes = await fetch(executeToolsUrl, {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({
                    trace_id: currentTraceId,
                    tool_calls: toolCallsPayload,
                    decisions: decisionsPayload,
                  }),
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
              if (!postRes.ok) {
                const text = await postRes.text()
                onError(
                  new Error(
                    `Tool execute API error ${postRes.status}: ${text || postRes.statusText}`,
                  ),
                )
                return
              }
              const nextReader = postRes.body?.getReader()
              if (!nextReader) {
                onError(new Error("No response body from execute-tools"))
                return
              }
              await drainReader(reader)
              reader = nextReader
              buffer = ""
              continue outer
            }
            processor.handleEvent(event)
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

// ---------------------------------------------------------------------------
// resumePendingToolCalls — graceful-stop handoff
// ---------------------------------------------------------------------------

export interface ResumePendingToolCallsOptions {
  /** ``POST /api/chat`` base URL (execute-tools URL is derived from it). */
  apiUrl: string
  /** Trace id of the conversation the surfaced tool calls belong to. */
  traceId: string
  /** The tool calls surfaced for approval (from a ``tool-calls-pending`` event). */
  items: ToolCallsPendingItem[]
  /** Reuses the normal approval gate: toolCallId → allowed. */
  onToolCallsPending: (
    payload: ToolCallsPendingPayload,
  ) => Promise<Record<string, boolean>>
  onAssistantMessage: (update: (draft: ChatMessage) => void) => void
  onChatTrace?: (traceId: string) => void
  onInlineError?: (message: string, traceId?: string, code?: string) => void
  onToolExecutionStart?: (toolCount: number) => void
  onToolExecutionEnd?: (toolCount: number) => void
  onShowActivityIndicator?: (show: boolean) => void
  onFinish: () => void
  onError: (error: Error) => void
}

/**
 * Resume a conversation that has pending client tool calls awaiting approval,
 * using the EXISTING execute-tools approval contract — NOT a parallel approval
 * UI. Used for the graceful-stop handoff (functional spec §4.4(1)): when the
 * server-owned auto runner surfaces ``tool-calls-pending`` on the observer
 * stream after a Stop, the browser drives the same approve → POST
 * /api/chat/execute-tools → stream-continuation loop the interactive
 * ``streamChat`` path uses, now in normal (approval) mode. Handles only the
 * ``tool-calls-pending`` approval/continuation loop: each subsequent
 * ``tool-calls-pending`` re-prompts via the same gate (multi-round approval).
 * NOTE: a re-``enable_auto_mode`` during a graceful-stop continuation is NOT
 * re-prompted here — its control loop intercepts only ``tool-calls-pending``,
 * and the shared ``StreamEventProcessor`` has no ``auto-mode-consent-required``
 * handler (known minor follow-up).
 */
export async function resumePendingToolCalls(
  options: ResumePendingToolCallsOptions,
): Promise<void> {
  const {
    apiUrl,
    traceId,
    items,
    onToolCallsPending,
    onAssistantMessage,
    onChatTrace,
    onInlineError,
    onToolExecutionStart,
    onToolExecutionEnd,
    onShowActivityIndicator,
    onFinish,
    onError,
  } = options

  const executeToolsUrl = chatExecuteToolsUrl(apiUrl)
  let currentTraceId = traceId

  const processor = new StreamEventProcessor({
    onAssistantMessage,
    onChatTrace: (tid) => {
      currentTraceId = tid
      onChatTrace?.(tid)
    },
    onInlineError,
    onToolExecutionStart,
    onToolExecutionEnd,
    onShowActivityIndicator,
  })

  // POST one execute-tools round for the given pending items; returns the
  // continuation reader. Mirrors the inline logic in ``streamChat``.
  async function executeRound(
    pendingItems: ToolCallsPendingItem[],
  ): Promise<ReadableStreamDefaultReader<Uint8Array> | null> {
    if (!Array.isArray(pendingItems) || pendingItems.length === 0) {
      onError(new Error("Invalid tool-calls-pending event from server"))
      return null
    }
    if (!currentTraceId) {
      onError(
        new Error(
          "Missing trace id for tool execution; wait for chat trace before tools.",
        ),
      )
      return null
    }
    const decisions = await onToolCallsPending({ items: pendingItems })
    const decisionsPayload: Record<string, boolean> = {}
    for (const it of pendingItems) {
      if (it.requiresApproval && typeof it.toolCallId === "string") {
        decisionsPayload[it.toolCallId] = decisions[it.toolCallId] ?? false
      }
    }
    const toolCallsPayload = pendingItems.map((it) => ({
      toolCallId: it.toolCallId,
      toolName: it.toolName,
      input: toolInputAsRecord(it.input),
      requiresApproval: Boolean(it.requiresApproval),
    }))
    let postRes: Response
    try {
      postRes = await fetch(executeToolsUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          trace_id: currentTraceId,
          tool_calls: toolCallsPayload,
          decisions: decisionsPayload,
        }),
      })
    } catch (err) {
      onError(err instanceof Error ? err : new Error(String(err)))
      return null
    }
    if (!postRes.ok) {
      const text = await postRes.text()
      onError(
        new Error(
          `Tool execute API error ${postRes.status}: ${text || postRes.statusText}`,
        ),
      )
      return null
    }
    const nextReader = postRes.body?.getReader()
    if (!nextReader) {
      onError(new Error("No response body from execute-tools"))
      return null
    }
    return nextReader
  }

  try {
    let reader = await executeRound(items)
    while (reader) {
      // Drive one continuation stream. A nested ``tool-calls-pending`` ends this
      // stream and seeds the next execute-tools round (multi-round approval).
      let nextItems: ToolCallsPendingItem[] | null = null
      await consumeSseStream(reader, processor, (event) => {
        if (event.type === "tool-calls-pending") {
          nextItems = Array.isArray(event.items) ? event.items : []
          return true
        }
        return false
      })
      if (!nextItems) break
      reader = await executeRound(nextItems)
    }
    onFinish()
  } catch (err) {
    onError(err instanceof Error ? err : new Error(String(err)))
  }
}

export { generateId as chatGenerateId }
