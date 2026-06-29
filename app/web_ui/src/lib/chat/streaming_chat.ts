/**
 * Custom streaming chat: parses SSE from the backend (AI SDK protocol JSON events).
 * Does not use @ai-sdk/svelte because we use Svelte 4 and @ai-sdk/svelte uses Svelte 5.
 *
 * There is an ancient version of the lib that works with Svelte 4, but then that forces us
 * to use an old version of the protocol on the backend too, which is not a good idea.
 */

import { CHAT_CLIENT_VERSION_TOO_OLD } from "$lib/error_codes"

export type ChatMessagePart =
  | { type: "text"; text: string }
  | {
      type: `tool-${string}`
      toolCallId: string
      toolName?: string
      input?: unknown
      output?: unknown
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
      parts: m.parts.map((p) => {
        if (p.type === "text") return { type: "text", text: p.text }
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

/**
 * Approximate context-window usage for the conversation, surfaced by the server
 * on the ``kiln_chat_trace`` snapshot event (and on the session GET). Numbers
 * and a boolean only — never any trace content. Values are intentionally
 * approximate (the gauge frames them with "≈").
 */
export interface ContextUsage {
  context_tokens: number
  context_limit: number
  context_percent: number
  compacted: boolean
}

/** Raw (optional/partial) ``context_usage`` shape as it arrives over the wire. */
export interface RawContextUsage {
  context_tokens?: number | null
  context_limit?: number | null
  context_percent?: number | null
  compacted?: boolean | null
}

/**
 * Normalize a raw (possibly partial) ``context_usage`` payload into a strict
 * ``ContextUsage``, or ``null`` when the payload is absent / carries no numbers.
 * Missing numbers default to 0 and ``compacted`` to ``false`` so an older or
 * partial upstream never crashes the gauge.
 */
export function normalizeContextUsage(
  raw: RawContextUsage | null | undefined,
): ContextUsage | null {
  if (!raw || typeof raw !== "object") return null
  const hasAnyNumber =
    typeof raw.context_tokens === "number" ||
    typeof raw.context_limit === "number" ||
    typeof raw.context_percent === "number"
  if (!hasAnyNumber) return null
  return {
    context_tokens:
      typeof raw.context_tokens === "number" ? raw.context_tokens : 0,
    context_limit:
      typeof raw.context_limit === "number" ? raw.context_limit : 0,
    context_percent:
      typeof raw.context_percent === "number" ? raw.context_percent : 0,
    compacted: raw.compacted === true,
  }
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
  /** ``auto-mode-retry`` carries the current/limit attempt + the upstream status */
  attempt?: number
  max_attempts?: number
  status_code?: number
  /** Approximate context usage carried on the ``kiln_chat_trace`` snapshot event */
  context_usage?: RawContextUsage
  /** ``kiln_compaction_status`` carries the lifecycle state ("started" / "finished") */
  state?: string
  /** Preferred client version from a ``kiln_client_upgrade_nudge`` event */
  preferred_version?: string
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
  /**
   * Fired when the ``kiln_chat_trace`` snapshot event carries ``context_usage``;
   * drives the context gauge. Shared by ``StreamChatOptions`` (interactive
   * stream) and the resume/auto paths via the processor.
   */
  onContextUsage?: (usage: ContextUsage) => void
  /**
   * Fired when the server emits ``kiln_compaction_status`` (Phase 5): ``true``
   * when compaction starts (so the UI shows a "summarizing…" indicator), and
   * ``false`` when it finishes or the first normal content event arrives.
   */
  onCompactionStatus?: (compacting: boolean) => void
  /** Fired when backend sends an inline error event */
  onInlineError?: (message: string, traceId?: string, code?: string) => void
  /**
   * Fired when the server nudges the client to upgrade (non-blocking): the
   * client is older than the server's preferred version but still above the
   * enforced minimum. ``preferredVersion`` is the version to suggest.
   */
  onVersionNudge?: (preferredVersion: string) => void
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

type PartSlot = { kind: "text"; id: string } | { kind: "tool"; id: string }

export interface StreamEventProcessorOptions {
  onAssistantMessage: (update: (draft: ChatMessage) => void) => void
  onChatTrace?: (traceId: string) => void
  onContextUsage?: (usage: ContextUsage) => void
  onCompactionStatus?: (compacting: boolean) => void
  onInlineError?: (message: string, traceId?: string, code?: string) => void
  onVersionNudge?: (preferredVersion: string) => void
  onToolExecutionStart?: (toolCount: number) => void
  onToolExecutionEnd?: (toolCount: number) => void
  onShowActivityIndicator?: (show: boolean) => void
}

export class StreamEventProcessor {
  private partOrder: PartSlot[] = []
  private textBlocks = new Map<string, string>()
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
  private toolInputBuffer = new Map<string, string>()
  private currentTextId: string | null = null
  private slotIdCounter = 0

  private onAssistantMessage: (update: (draft: ChatMessage) => void) => void
  private onChatTrace?: (traceId: string) => void
  private onContextUsage?: (usage: ContextUsage) => void
  private onCompactionStatus?: (compacting: boolean) => void
  private onInlineError?: (
    message: string,
    traceId?: string,
    code?: string,
  ) => void
  private onVersionNudge?: (preferredVersion: string) => void
  private onToolExecutionStart?: (toolCount: number) => void
  private onToolExecutionEnd?: (toolCount: number) => void
  private onShowActivityIndicator?: (show: boolean) => void

  private HANDLERS: Record<string, (event: StreamEvent) => void>

  constructor(opts: StreamEventProcessorOptions) {
    this.onAssistantMessage = opts.onAssistantMessage
    this.onChatTrace = opts.onChatTrace
    this.onContextUsage = opts.onContextUsage
    this.onCompactionStatus = opts.onCompactionStatus
    this.onInlineError = opts.onInlineError
    this.onVersionNudge = opts.onVersionNudge
    this.onToolExecutionStart = opts.onToolExecutionStart
    this.onToolExecutionEnd = opts.onToolExecutionEnd
    this.onShowActivityIndicator = opts.onShowActivityIndicator

    this.HANDLERS = {
      "text-start": (e) => {
        this.clearCompacting()
        this.onShowActivityIndicator?.(false)
        this.handleTextStart(e)
      },
      "text-delta": (e) => {
        this.clearCompacting()
        this.handleTextDelta(e)
      },
      "text-end": () => {
        this.onShowActivityIndicator?.(true)
        this.handleTextEnd()
      },
      "tool-input-start": (e) => {
        this.clearCompacting()
        this.onShowActivityIndicator?.(true)
        this.handleToolInputStart(e)
      },
      "tool-input-delta": (e) => this.handleToolInputDelta(e),
      "tool-input-available": (e) => {
        this.clearCompacting()
        this.onShowActivityIndicator?.(true)
        this.handleToolInputAvailable(e)
      },
      "tool-output-available": (e) => this.handleToolOutputAvailable(e),
      "tool-output-error": (e) => this.handleToolOutputError(e),
      kiln_chat_trace: (e) => {
        this.clearCompacting()
        this.handleChatTrace(e)
      },
      kiln_compaction_status: (e) => this.handleCompactionStatus(e),
      kiln_client_upgrade_nudge: (e) => this.handleVersionNudge(e),
      "kiln-tool-execution-start": (e) => {
        this.clearCompacting()
        this.onShowActivityIndicator?.(true)
        this.onToolExecutionStart?.(e.tool_count ?? 0)
      },
      "kiln-tool-execution-end": (e) =>
        this.onToolExecutionEnd?.(e.tool_count ?? 0),
      error: (e) => {
        this.clearCompacting()
        this.handleError(e)
      },
    }
  }

  /**
   * Clear the compaction indicator. Called when the first normal content event
   * of the turn arrives (text/tool/snapshot) or on error — compaction is a
   * brief pre-turn step, so any real turn output means it's done.
   */
  private clearCompacting(): void {
    this.onCompactionStatus?.(false)
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

  private handleChatTrace(event: StreamEvent): void {
    const tid = event.trace_id
    if (typeof tid === "string" && tid) {
      this.onChatTrace?.(tid)
    }
    const usage = normalizeContextUsage(event.context_usage)
    if (usage) {
      this.onContextUsage?.(usage)
    }
  }

  private handleCompactionStatus(event: StreamEvent): void {
    // Only "started" drives the indicator ON. We deliberately do NOT clear on
    // "finished": the summarization LLM call can complete and its bytes flush
    // so fast (or buffered together) that a started→finished pair would collapse
    // to nothing visible. Instead the indicator stays up until the FIRST real
    // assistant content of the turn (text/tool/exec-start/snapshot) arrives —
    // see ``clearCompacting``. A "finished" with no content yet is ignored.
    if (event.state === "started") {
      this.onCompactionStatus?.(true)
    }
  }

  private handleVersionNudge(event: StreamEvent): void {
    const preferred = event.preferred_version
    if (typeof preferred === "string" && preferred) {
      this.onVersionNudge?.(preferred)
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
    onContextUsage,
    onCompactionStatus,
    onInlineError,
    onVersionNudge,
    onToolCallsPending,
    onToolExecutionStart,
    onToolExecutionEnd,
    onShowActivityIndicator,
    onAutoModeConsentRequired,
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
    onContextUsage,
    onCompactionStatus,
    onInlineError,
    onVersionNudge,
    onToolExecutionStart,
    onToolExecutionEnd,
    onShowActivityIndicator,
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
  onContextUsage?: (usage: ContextUsage) => void
  onCompactionStatus?: (compacting: boolean) => void
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
    onContextUsage,
    onCompactionStatus,
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
    onContextUsage,
    onCompactionStatus,
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
