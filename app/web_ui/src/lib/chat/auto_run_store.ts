/**
 * Owns the auto-run lifecycle for the active conversation.
 *
 * Auto mode lifts the chat loop out of the browser into a server-owned runner
 * (Phase 2/3). This store drives that runner from the UI: enable / decline /
 * stop, and — critically — observes the per-run SSE stream as a pure observer,
 * feeding its bytes into the EXISTING ``StreamEventProcessor`` so the running
 * turn renders exactly like an interactive turn. Connection handling mirrors
 * ``jobs_store.ts``: opening or closing the stream never mutates the run; the
 * authoritative "on/off" state comes from the runner's ``auto-mode-on`` /
 * ``auto-mode-off`` control events, so it is correct on first paint after a
 * re-attach (not just after a local toggle).
 */

import { get, writable, type Readable } from "svelte/store"
import { base_url } from "$lib/api_client"
import type { components } from "$lib/api_schema"
import {
  StreamEventProcessor,
  consumeSseStream,
  type ChatMessage,
  type StreamEvent,
} from "./streaming_chat"

export type EnableAutoRequest = components["schemas"]["EnableAutoRequest"]
export type DeclineAutoRequest = components["schemas"]["DeclineAutoRequest"]

const AUTO_BASE_URL = `${base_url}/api/chat/auto`

// Lifecycle of the per-run events EventSource, surfaced for tests / debugging.
// A pure observer: this only reports the connection, it never mutates the run.
export type AutoConnection = "idle" | "connecting" | "open" | "closed"

/**
 * Callbacks the chat session store registers so the auto runner can drive the
 * same conversation the interactive stream drives. Mirrors the hooks
 * ``streamChat`` already calls, plus turn lifecycle and an off-signal.
 */
export interface AutoRunChatSink {
  /** Begin a fresh assistant turn (append an empty assistant message). */
  beginAssistantTurn: () => void
  onAssistantMessage: (update: (draft: ChatMessage) => void) => void
  onChatTrace: (traceId: string) => void
  onInlineError: (message: string, traceId?: string, code?: string) => void
  onToolExecutionStart: (toolCount: number) => void
  onToolExecutionEnd: (toolCount: number) => void
  onShowActivityIndicator: (show: boolean) => void
  /** Auto mode turned off (done / asked_user / user_stopped / error / max_rounds). */
  onAutoModeOff: (reason: string | null) => void
}

export interface AutoRunStore {
  autoModeOn: Readable<boolean>
  runId: Readable<string | null>
  offReason: Readable<string | null>
  connection: Readable<AutoConnection>
  bind(sink: AutoRunChatSink): void
  requestEnable(
    seed: EnableAutoRequest,
  ): Promise<{ ok: boolean; error?: string }>
  decline(req: DeclineAutoRequest): Promise<void>
  stop(): Promise<void>
  attach(runId: string): void
  /** Stop observing + clear the indicator without ending the run (navigation). */
  detach(): void
  /** Exposed for tests / explicit teardown; not part of normal usage. */
  _close(): void
}

export function createAutoRunStore(): AutoRunStore {
  const autoModeOn = writable<boolean>(false)
  const runId = writable<string | null>(null)
  const offReason = writable<string | null>(null)
  const connection = writable<AutoConnection>("idle")

  let sink: AutoRunChatSink | null = null
  let eventSource: EventSource | null = null

  function bind(newSink: AutoRunChatSink): void {
    sink = newSink
  }

  function buildProcessor(): StreamEventProcessor {
    return new StreamEventProcessor({
      onAssistantMessage: (update) => sink?.onAssistantMessage(update),
      onChatTrace: (tid) => sink?.onChatTrace(tid),
      onInlineError: (message, traceId, code) =>
        sink?.onInlineError(message, traceId, code),
      onToolExecutionStart: (count) => sink?.onToolExecutionStart(count),
      onToolExecutionEnd: (count) => sink?.onToolExecutionEnd(count),
      onShowActivityIndicator: (show) => sink?.onShowActivityIndicator(show),
    })
  }

  function closeSource(): void {
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
  }

  function clearToOff(reason: string | null): void {
    closeSource()
    autoModeOn.set(false)
    runId.set(null)
    offReason.set(reason)
    connection.set("closed")
    sink?.onAutoModeOff(reason)
  }

  // Stop observing the current run and clear the indicator WITHOUT signalling the
  // sink (the run keeps going server-side; the user just navigated away — e.g.
  // New Chat / load another conversation). Re-attach is available from history.
  function detach(): void {
    closeSource()
    autoModeOn.set(false)
    runId.set(null)
    offReason.set(null)
    connection.set("idle")
  }

  // --- Control-event handling on the per-run stream ---------------------------
  // Returns true when it claims the event (so it isn't forwarded to the
  // processor). The control vocabulary is auto-mode-on / auto-mode-off; every
  // other event is normal chat SSE and flows to the processor unchanged.
  function handleControlEvent(event: StreamEvent): boolean {
    if (event.type === "auto-mode-on") {
      autoModeOn.set(true)
      if (event.run_id) runId.set(event.run_id)
      offReason.set(null)
      return true
    }
    if (event.type === "auto-mode-off") {
      clearToOff(event.reason ?? null)
      return true
    }
    return false
  }

  function attach(newRunId: string): void {
    const EventSourceCtor = globalThis.EventSource
    if (!EventSourceCtor) return
    closeSource()

    runId.set(newRunId)
    autoModeOn.set(true)
    offReason.set(null)
    connection.set("connecting")

    const processor = buildProcessor()
    const source = new EventSourceCtor(
      `${AUTO_BASE_URL}/${encodeURIComponent(newRunId)}/events`,
    )
    eventSource = source

    source.onopen = () => {
      if (eventSource !== source) return
      connection.set("open")
    }

    source.onmessage = (e: MessageEvent) => {
      if (eventSource !== source) return
      const data = typeof e.data === "string" ? e.data.trim() : ""
      if (!data || data === "[DONE]") return
      let event: StreamEvent
      try {
        event = JSON.parse(data) as StreamEvent
      } catch {
        return
      }
      if (handleControlEvent(event)) return
      processor.handleEvent(event)
    }

    source.onerror = () => {
      // Only act on the active source (avoid racing a teardown / re-attach).
      if (eventSource !== source) return
      // No reconnect loop. Whether the run was never reachable (GC'd / unknown →
      // events 404, never opened) or it opened then dropped without an explicit
      // off, the conversation is persisted server-side: degrade cleanly to the
      // hydrated-history "off" state — never a hard error (ui_design §5). A run
      // that finished normally already cleared us via auto-mode-off.
      clearToOff(null)
    }
  }

  async function requestEnable(
    seed: EnableAutoRequest,
  ): Promise<{ ok: boolean; error?: string }> {
    let response: Response
    try {
      response = await fetch(`${AUTO_BASE_URL}/enable`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(seed),
      })
    } catch (err) {
      return {
        ok: false,
        error: err instanceof Error ? err.message : String(err),
      }
    }
    if (!response.ok) {
      let message = `Could not enable auto mode (${response.status}).`
      try {
        const parsed = (await response.json()) as { detail?: string }
        if (parsed?.detail) message = parsed.detail
      } catch {
        /* keep default */
      }
      return { ok: false, error: message }
    }
    let data: { run_id?: string }
    try {
      data = (await response.json()) as { run_id?: string }
    } catch {
      return { ok: false, error: "Malformed response from enable auto mode." }
    }
    if (!data.run_id) {
      return { ok: false, error: "Enable auto mode did not return a run id." }
    }
    // A fresh assistant turn renders the runner's first burst.
    sink?.beginAssistantTurn()
    attach(data.run_id)
    return { ok: true }
  }

  async function decline(req: DeclineAutoRequest): Promise<void> {
    // Decline resolves enable→declined server-side and resumes the normal
    // interactive stream; consume it into the same sink as a fresh turn.
    let response: Response
    try {
      response = await fetch(`${AUTO_BASE_URL}/decline`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req),
      })
    } catch (err) {
      sink?.onInlineError(err instanceof Error ? err.message : String(err))
      return
    }
    if (!response.ok) {
      const text = await response.text()
      sink?.onInlineError(
        `Could not resume chat after declining auto mode (${response.status}): ${
          text || response.statusText
        }`,
      )
      return
    }
    const reader = response.body?.getReader()
    if (!reader) {
      sink?.onInlineError("No response body when resuming chat.")
      return
    }
    sink?.beginAssistantTurn()
    try {
      await consumeSseStream(reader, buildProcessor())
    } catch (err) {
      sink?.onInlineError(err instanceof Error ? err.message : String(err))
    }
  }

  async function stop(): Promise<void> {
    const id = get(runId)
    if (!id) return
    // Optimistic only: the authoritative clear arrives as auto-mode-off. We do
    // not flip state here so a failed stop doesn't lie about being off.
    try {
      await fetch(`${AUTO_BASE_URL}/${encodeURIComponent(id)}/stop`, {
        method: "POST",
      })
    } catch {
      /* idempotent; the run keeps going and the user can retry */
    }
  }

  return {
    autoModeOn: { subscribe: autoModeOn.subscribe },
    runId: { subscribe: runId.subscribe },
    offReason: { subscribe: offReason.subscribe },
    connection: { subscribe: connection.subscribe },
    bind,
    requestEnable,
    decline,
    stop,
    attach,
    detach,
    _close: closeSource,
  }
}

export const auto_run_store: AutoRunStore = createAutoRunStore()
