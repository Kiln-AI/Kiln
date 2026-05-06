/**
 * Mock OpenAI-compatible inference provider for Playwright e2e tests.
 *
 * Speaks just enough of the OpenAI REST surface for Kiln's litellm-backed
 * inference path to route through a localhost URL instead of a real provider.
 *
 * Endpoints:
 *   POST /v1/chat/completions  - returns the next queued response, or a
 *                                generic "mock response" if the queue is empty.
 *   GET  /v1/models            - lists the mock model ids (used by Kiln's
 *                                custom-provider model-discovery flow).
 *
 * Admin (tests only):
 *   POST /__queue   - push one response to the FIFO queue. Body shape:
 *                     { content?, status?, body?, delayMs? }
 *                     If `body` is set, it's returned as-is. Otherwise the
 *                     response is an OpenAI chat.completion with `content`.
 *   POST /__reset   - clear the queue and recorded requests.
 *   GET  /__state   - return { queueLength, requests } for debugging/assertions.
 */

import { createServer, IncomingMessage, ServerResponse } from "node:http"

type QueuedResponse = {
  content?: string
  status?: number
  body?: unknown
  delayMs?: number
}

type RecordedRequest = {
  method: string
  path: string
  body: unknown
  headers: Record<string, string | string[] | undefined>
  at: number
}

const queue: QueuedResponse[] = []
const requests: RecordedRequest[] = []

function readBody(req: IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = []
    req.on("data", (c: Buffer) => chunks.push(c))
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")))
    req.on("error", reject)
  })
}

function respond(res: ServerResponse, status: number, body: unknown): void {
  const payload = JSON.stringify(body)
  res.writeHead(status, {
    "Content-Type": "application/json",
    "Content-Length": Buffer.byteLength(payload),
  })
  res.end(payload)
}

function completionBody(content: string, requestedModel: string): unknown {
  return {
    id: `chatcmpl-mock-${Date.now()}`,
    object: "chat.completion",
    created: Math.floor(Date.now() / 1000),
    model: requestedModel,
    choices: [
      {
        index: 0,
        message: { role: "assistant", content },
        finish_reason: "stop",
      },
    ],
    usage: { prompt_tokens: 1, completion_tokens: 1, total_tokens: 2 },
  }
}

const server = createServer(async (req, res) => {
  try {
    const url = new URL(req.url ?? "/", "http://localhost")
    const path = url.pathname
    const method = req.method ?? "GET"
    const raw = method === "GET" || method === "HEAD" ? "" : await readBody(req)
    let parsed: unknown = null
    if (raw) {
      try {
        parsed = JSON.parse(raw)
      } catch {
        parsed = raw
      }
    }
    requests.push({
      method,
      path,
      body: parsed,
      headers: req.headers,
      at: Date.now(),
    })

    if (path === "/__queue" && method === "POST") {
      queue.push((parsed ?? {}) as QueuedResponse)
      return respond(res, 200, { queued: queue.length })
    }
    if (path === "/__reset" && method === "POST") {
      queue.length = 0
      requests.length = 0
      return respond(res, 200, { ok: true })
    }
    if (path === "/__state" && method === "GET") {
      return respond(res, 200, { queueLength: queue.length, requests })
    }

    if (path === "/v1/chat/completions" && method === "POST") {
      const next = queue.shift()
      const requestedModel =
        typeof (parsed as { model?: string } | null)?.model === "string"
          ? (parsed as { model: string }).model
          : "mock-chat"
      if (next?.delayMs) {
        await new Promise((r) => setTimeout(r, next.delayMs))
      }
      if (next?.status && next.status >= 400) {
        return respond(
          res,
          next.status,
          next.body ?? {
            error: { message: "mock error", type: "mock_error" },
          },
        )
      }
      if (next?.body !== undefined) {
        return respond(res, next.status ?? 200, next.body)
      }
      const content = next?.content ?? "mock response"
      return respond(res, 200, completionBody(content, requestedModel))
    }

    if (path === "/v1/models" && method === "GET") {
      return respond(res, 200, {
        object: "list",
        data: [{ id: "mock-chat", object: "model" }],
      })
    }

    return respond(res, 404, {
      error: { message: `mock-provider: no route for ${method} ${path}` },
    })
  } catch (e) {
    return respond(res, 500, {
      error: { message: e instanceof Error ? e.message : String(e) },
    })
  }
})

const port = Number(process.env.MOCK_PROVIDER_PORT ?? 6536)
server.listen(port, () => {
  // eslint-disable-next-line no-console
  console.log(`[mock-provider] listening on :${port}`)
})

process.on("SIGTERM", () => server.close(() => process.exit(0)))
process.on("SIGINT", () => server.close(() => process.exit(0)))
