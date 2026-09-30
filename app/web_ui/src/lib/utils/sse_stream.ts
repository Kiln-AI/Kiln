/**
 * Read a server-sent-events endpoint with fetch, so a refusal is visible.
 *
 * `EventSource` cannot see the status or body of a non-200 response — it fires `onerror`
 * with a bare `Event`, which `createKilnError` renders as "Unknown error". An endpoint
 * that refuses up front with a 4xx naming the reason has that reason thrown away by such
 * a client. Reading the stream ourselves means a non-2xx is an ordinary response whose
 * `{message}` body we can parse and surface. Written for the eval run endpoints, which do
 * exactly that; nothing here is specific to them.
 *
 * What we give up by not using EventSource: automatic reconnection and Last-Event-ID
 * replay. Callers that want either should keep using EventSource.
 */

export type SseStream = {
  /** Stop reading and let the server observe the disconnect. */
  close: () => void
}

export type SseOptions = {
  /** One `data:` payload. Called once per event, in order. */
  on_message: (data: string) => void
  /** A transport failure, or a non-2xx response body. Terminal. */
  on_error: (error: unknown) => void
  /**
   * What this stream is, named in the error shown when a body ends early. Defaults to
   * "stream". This module is domain-neutral — anything with an SSE endpoint can use it —
   * so the one message it composes itself takes its noun from the caller rather than
   * telling a RAG-indexing user their eval failed.
   */
  subject?: string
}

/** The most useful error value the server gave us for a non-2xx response. */
async function response_error(response: Response): Promise<unknown> {
  try {
    const body = await response.json()
    if (body && typeof body === "object") {
      return body
    }
  } catch (_) {
    // Not JSON (a proxy error page, an empty body); fall through to the status.
  }
  return { message: `Server error: [${response.status}]` }
}

/** Split off every complete event in `buffer`, returning them and the remainder. */
function take_events(buffer: string): { events: string[]; rest: string } {
  const parts = buffer.split("\n\n")
  return { events: parts.slice(0, -1), rest: parts[parts.length - 1] ?? "" }
}

/** The `data:` payload of one SSE event, joining multi-line data as the spec requires. */
function event_data(event: string): string | null {
  const lines = event
    .split("\n")
    .map((line) => line.trimEnd())
    .filter((line) => line.startsWith("data:"))
  if (lines.length === 0) {
    return null
  }
  return lines.map((line) => line.slice("data:".length).trimStart()).join("\n")
}

export function stream_sse(url: string, options: SseOptions): SseStream {
  const subject = options.subject ?? "stream"
  const controller = new AbortController()
  let closed = false

  const close = () => {
    closed = true
    controller.abort()
  }

  const run = async () => {
    const response = await fetch(url, {
      signal: controller.signal,
      headers: { Accept: "text/event-stream" },
    })
    if (!response.ok) {
      throw await response_error(response)
    }
    if (!response.body) {
      throw { message: "The server returned no response body." }
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ""
    for (;;) {
      const { done, value } = await reader.read()
      if (done) {
        // Not a normal exit. Callers end their streams with a terminal message whose
        // handler closes the stream — so the `if (closed)` check below is the only way
        // out on the happy path, and reaching `done` means the body ended early (an
        // intermediary cutting the response, a 200 with an empty body). Reporting
        // nothing would pin the caller in its "running" state forever, with no error
        // shown and no retry offered: worse than the bad message this reader replaced.
        throw { message: `The ${subject} ended without completing.` }
      }
      // stream: true so a multi-byte character split across chunks isn't mangled.
      buffer += decoder.decode(value, { stream: true })
      const { events, rest } = take_events(buffer)
      buffer = rest
      for (const event of events) {
        const data = event_data(event)
        if (data !== null) {
          options.on_message(data)
        }
        if (closed) {
          return
        }
      }
    }
  }

  run().catch((error) => {
    // Every terminal path disconnects. Without this, a throw from on_message leaves
    // the fetch live and its reader abandoned, and the server keeps doing work for a
    // client that has stopped listening.
    controller.abort()
    // close() aborts on purpose; that is not something to report.
    if (closed) {
      return
    }
    options.on_error(error)
  })

  return { close }
}
