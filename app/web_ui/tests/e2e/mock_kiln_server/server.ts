/**
 * Mock Kiln server for Playwright e2e tests.
 *
 * Stands in for api.kiln.tech (the hosted Kiln server that backs copilot,
 * specs, prompt-optimizer, chat, entitlements, etc.). The Kiln backend's
 * generated client honors KILN_SERVER_BASE_URL — set it to this mock and
 * the entire copilot/auth surface routes here.
 *
 * Phase 2 scope is auth + a single auth-exercising probe (check_entitlements).
 * Future test authors extend this mock with the endpoints their tests need.
 *
 * Endpoints (skeleton):
 *   GET  /ping                  - unauthenticated readiness probe.
 *   GET  /v1/check_entitlements - bearer-auth required; returns the queued
 *                                 entitlements dict, or { code: true } for
 *                                 each requested feature_code if nothing queued.
 *
 * Admin (tests only):
 *   POST /__queue   - push one response to a path-keyed FIFO. Body shape:
 *                     { path: string, status?: number, body?: unknown,
 *                       delayMs?: number }
 *                     Pop matches by path. If no entry is queued for a path,
 *                     the endpoint's default behavior runs.
 *   POST /__reset   - clear queues and recorded requests.
 *   GET  /__state   - return { queues: { [path]: count }, requests }.
 */

import { createServer, IncomingMessage, ServerResponse } from "node:http"

type QueuedResponse = {
  path: string
  status?: number
  body?: unknown
  delayMs?: number
}

type RecordedRequest = {
  method: string
  path: string
  query: Record<string, string>
  body: unknown
  headers: Record<string, string | string[] | undefined>
  authorization: string | undefined
  at: number
}

const queues = new Map<string, QueuedResponse[]>()
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

function popQueued(path: string): QueuedResponse | undefined {
  const q = queues.get(path)
  return q?.shift()
}

function pushQueued(item: QueuedResponse): void {
  const arr = queues.get(item.path) ?? []
  arr.push(item)
  queues.set(item.path, arr)
}

function bearerOrReject(
  res: ServerResponse,
  authHeader: string | undefined,
): string | null {
  if (!authHeader || !authHeader.toLowerCase().startsWith("bearer ")) {
    respond(res, 401, {
      error: { message: "missing or malformed Authorization bearer token" },
    })
    return null
  }
  return authHeader.slice("bearer ".length).trim()
}

const server = createServer(async (req, res) => {
  try {
    const url = new URL(req.url ?? "/", "http://localhost")
    const path = url.pathname
    const method = req.method ?? "GET"
    const query: Record<string, string> = {}
    url.searchParams.forEach((v, k) => {
      query[k] = v
    })
    const raw = method === "GET" || method === "HEAD" ? "" : await readBody(req)
    let parsed: unknown = null
    if (raw) {
      try {
        parsed = JSON.parse(raw)
      } catch {
        parsed = raw
      }
    }
    const authHeader = req.headers["authorization"]
    requests.push({
      method,
      path,
      query,
      body: parsed,
      headers: req.headers,
      authorization: typeof authHeader === "string" ? authHeader : undefined,
      at: Date.now(),
    })

    if (path === "/__queue" && method === "POST") {
      const item = (parsed ?? {}) as QueuedResponse
      if (!item.path || typeof item.path !== "string") {
        return respond(res, 400, {
          error: { message: "__queue requires { path: string, ... }" },
        })
      }
      pushQueued(item)
      return respond(res, 200, {
        queued: queues.get(item.path)?.length ?? 0,
      })
    }
    if (path === "/__reset" && method === "POST") {
      queues.clear()
      requests.length = 0
      return respond(res, 200, { ok: true })
    }
    if (path === "/__state" && method === "GET") {
      const counts: Record<string, number> = {}
      for (const [k, v] of queues.entries()) counts[k] = v.length
      return respond(res, 200, { queues: counts, requests })
    }

    if (path === "/ping" && method === "GET") {
      return respond(res, 200, { pong: true })
    }

    if (path === "/v1/check_entitlements" && method === "GET") {
      const token = bearerOrReject(res, req.headers["authorization"] as string)
      if (token == null) return
      const next = popQueued(path)
      if (next?.delayMs) {
        await new Promise((r) => setTimeout(r, next.delayMs))
      }
      if (next?.status && next.status >= 400) {
        return respond(
          res,
          next.status,
          next.body ?? { error: { message: "mock error" } },
        )
      }
      if (next?.body !== undefined) {
        return respond(res, next.status ?? 200, next.body)
      }
      const codes = (query["feature_codes"] ?? "")
        .split(",")
        .map((c) => c.trim())
        .filter(Boolean)
      const out: Record<string, boolean> = {}
      for (const c of codes) out[c] = true
      return respond(res, 200, out)
    }

    return respond(res, 404, {
      error: {
        message: `mock-kiln-server: no route for ${method} ${path}. Tests should add the endpoint they need to mock_kiln_server/server.ts.`,
      },
    })
  } catch (e) {
    return respond(res, 500, {
      error: { message: e instanceof Error ? e.message : String(e) },
    })
  }
})

const port = Number(process.env.KILN_SERVER_MOCK_PORT ?? 6537)
server.listen(port, () => {
  // eslint-disable-next-line no-console
  console.log(`[mock-kiln-server] listening on :${port}`)
})

process.on("SIGTERM", () => server.close(() => process.exit(0)))
process.on("SIGINT", () => server.close(() => process.exit(0)))
