/**
 * Chat SSE plumbing: parses SSE events (AI SDK protocol JSON events) and
 * accumulates them into UI messages (StreamEventProcessor). Does not use
 * @ai-sdk/svelte because we use Svelte 4 and @ai-sdk/svelte uses Svelte 5.
 *
 * Phase 4 note: the request-driving halves that used to live here —
 * `streamChat` (POST /api/chat + the execute-tools continuation loop) and
 * `resumePendingToolCalls` (the graceful-stop handoff) — are GONE with the
 * old interactive surface. The main conversation is now a desktop-owned run
 * observed through `conversation_store.ts` (`/api/conversations`); the
 * observer feeds the same `StreamEventProcessor`, so everything below is
 * transport-agnostic parsing/accumulation shared by every transcript.
 */

export type ChatMessagePart =
  | { type: "text"; text: string }
  | {
      type: `tool-${string}`
      toolCallId: string
      toolName?: string
      input?: unknown
      output?: unknown
    }

/**
 * Parsed attributes of a ``<subagent_report …>`` frame — the user-role message
 * the server injects into a parent conversation when a sub-agent finishes. The
 * transcript renders these as a collapsed report chip instead of a user bubble.
 */
export interface SubagentReportInfo {
  id: string
  agentType: string
  status: string
  title: string
}

export interface ChatMessage {
  id: string
  role: "user" | "assistant" | "system" | "error"
  content?: string
  parts?: ChatMessagePart[]
  /**
   * Diagnostic trace id riding an ERROR message (from the upstream error
   * event's payload). Never rendered and never a key — phase 5 removed all
   * trace-id KEYING from the browser (assistant messages no longer carry
   * one; the desktop record owns continuation state).
   */
  traceId?: string
  /**
   * Set when this user-role message is a sub-agent completion report frame
   * (``<subagent_report …>``). ``content`` then holds the report BODY (the
   * frame is stripped on hydration / echo detection, like other internal
   * framings) and the transcript renders a report chip instead of a bubble.
   */
  subagentReport?: SubagentReportInfo
  /**
   * Stable id from the ``user-message`` echo for an auto-mode injected message.
   * Lets the client render the echo idempotently — a buffer replay on re-attach
   * re-emits the echo for an in-flight message the transcript already shows.
   */
  echoId?: string
  /** Machine-readable error code from upstream (e.g. ``CHAT_CLIENT_VERSION_TOO_OLD``) */
  errorCode?: string
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
  /** ``kiln-chat-retry`` on a desktop-owned run carries the session id under
   * the legacy ``run_id`` key */
  run_id?: string
  /** ``user-message`` echo carries the injected user message content */
  content?: string
  /** ``conversation-state`` (the unified lifecycle event that replaced
   * auto-mode-on/off/idle/state and kiln-subagent-status): session_id is the
   * conversation handle; ``state`` reuses the field the compaction event
   * declares above; auto_flag/idle_reason carry the auto-mode axis (reasons:
   * armed/asked_user/done/error/max_rounds while on, user_stopped/
   * user_disabled when the flag just cleared); ``kind`` is
   * interactive|auto|subagent. */
  session_id?: string
  kind?: string
  auto_flag?: boolean
  idle_reason?: string
  /** ``kiln-chat-retry`` carries the current/limit attempt + the upstream status */
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
 * Payload of the ``auto-mode-consent-required`` event. The engine emits this
 * (then idles the turn) when the model calls ``enable_auto_mode``; the UI must
 * gate auto-mode behind explicit consent. Phase 5: the payload carries no
 * trace id — accept/decline is keyed by the observed conversation's session
 * id (functional spec §4).
 */
export interface AutoModeConsentRequiredPayload {
  enableToolCallId: string
  reason: string | null
  siblingToolCalls: ToolCallsPendingItem[]
}

function generateId(): string {
  return `msg-${crypto.randomUUID()}`
}

// Phase 5 note: ``traceIdForNextChatRequest`` (the browser's continuation
// key, scanned off assistant messages) is DELETED — conversations are keyed
// by session id end-to-end and the desktop record owns the current leaf.

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
  /**
   * A transient upstream failure is being retried with backoff (kiln-chat-retry).
   * Drives the "retrying N/M…" affordance. ``onRetryClear`` fires on the next
   * non-retry event (the recovered round, or the terminal error).
   */
  onRetry?: (attempt: number, maxAttempts: number) => void
  onRetryClear?: () => void
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
  private onRetry?: (attempt: number, maxAttempts: number) => void
  private onRetryClear?: () => void
  // True while a kiln-chat-retry is the most recent event, so we clear the
  // affordance exactly once on the next non-retry event (not per streamed token).
  private retryActive = false

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
    this.onRetry = opts.onRetry
    this.onRetryClear = opts.onRetryClear

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
      "kiln-chat-retry": (e) => {
        this.retryActive = true
        this.onRetry?.(e.attempt ?? 0, e.max_attempts ?? 0)
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
    // The retry affordance clears as soon as the round recovers (or fails) — the
    // next event of any other kind. Guarded so it fires once, not per token.
    if (this.retryActive && event.type !== "kiln-chat-retry") {
      this.retryActive = false
      this.onRetryClear?.()
    }
    const handler = this.HANDLERS[event.type]
    if (handler) {
      handler(event)
    }
  }

  /**
   * Drop all accumulated parts so the next events render into a FRESH assistant
   * turn. Call this when a new assistant message has been opened mid-stream
   * (e.g. an injected user message during an auto burst calls
   * ``beginAssistantTurn``). Without it, ``flushAssistant`` keeps re-writing the
   * prior turn's parts into the newly opened message, duplicating it.
   */
  reset(): void {
    this.partOrder = []
    this.textBlocks.clear()
    this.toolMap.clear()
    this.toolInputBuffer.clear()
    this.currentTextId = null
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
    // Desktop-shaped errors carry `message`; backend/provider errors forwarded
    // through the stream carry `errorText`. Surface whichever exists instead of
    // swallowing the reason behind a generic fallback.
    this.onInlineError?.(
      event.message ?? event.errorText ?? "An error occurred.",
      event.trace_id,
      event.code,
    )
  }
}

/** Map a raw ``auto-mode-consent-required`` event to its typed payload. */
export function autoModeConsentPayloadFromEvent(
  event: StreamEvent,
): AutoModeConsentRequiredPayload {
  return {
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

export { generateId as chatGenerateId }
