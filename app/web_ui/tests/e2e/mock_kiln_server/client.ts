import type { APIRequestContext } from "@playwright/test"
import { KILN_SERVER_MOCK_URL } from "../ports"

export type MockKilnQueuedResponse = {
  path: string
  status?: number
  body?: unknown
  delayMs?: number
}

export type MockKilnRecordedRequest = {
  method: string
  path: string
  query: Record<string, string>
  body: unknown
  headers: Record<string, string | string[] | undefined>
  authorization: string | undefined
  at: number
}

export type MockKilnState = {
  queues: Record<string, number>
  requests: MockKilnRecordedRequest[]
}

export class MockKilnServerClient {
  constructor(private readonly ctx: APIRequestContext) {}

  async queue(response: MockKilnQueuedResponse): Promise<void> {
    const r = await this.ctx.post(`${KILN_SERVER_MOCK_URL}/__queue`, {
      data: response,
    })
    if (!r.ok()) {
      throw new Error(
        `mock kiln-server queue failed: ${r.status()} ${await r.text()}`,
      )
    }
  }

  async reset(): Promise<void> {
    const r = await this.ctx.post(`${KILN_SERVER_MOCK_URL}/__reset`)
    if (!r.ok()) {
      throw new Error(
        `mock kiln-server reset failed: ${r.status()} ${await r.text()}`,
      )
    }
  }

  async state(): Promise<MockKilnState> {
    const r = await this.ctx.get(`${KILN_SERVER_MOCK_URL}/__state`)
    if (!r.ok()) {
      throw new Error(
        `mock kiln-server state failed: ${r.status()} ${await r.text()}`,
      )
    }
    return (await r.json()) as MockKilnState
  }
}

/** Stable test API key seeded by the seededCopilotKey fixture. */
export const COPILOT_TEST_API_KEY = "act-mock-copilot-key"
