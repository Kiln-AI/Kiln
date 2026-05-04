import type { APIRequestContext } from "@playwright/test"
import { MOCK_PROVIDER_URL } from "../ports"

export type MockQueuedResponse = {
  content?: string
  status?: number
  body?: unknown
  delayMs?: number
}

export type MockRecordedRequest = {
  method: string
  path: string
  body: unknown
  headers: Record<string, string | string[] | undefined>
  at: number
}

export type MockState = {
  queueLength: number
  requests: MockRecordedRequest[]
}

export class MockProviderClient {
  constructor(private readonly ctx: APIRequestContext) {}

  async queue(response: MockQueuedResponse): Promise<void> {
    const r = await this.ctx.post(`${MOCK_PROVIDER_URL}/__queue`, {
      data: response,
    })
    if (!r.ok()) {
      throw new Error(`mock queue failed: ${r.status()} ${await r.text()}`)
    }
  }

  async reset(): Promise<void> {
    const r = await this.ctx.post(`${MOCK_PROVIDER_URL}/__reset`)
    if (!r.ok()) {
      throw new Error(`mock reset failed: ${r.status()} ${await r.text()}`)
    }
  }

  async state(): Promise<MockState> {
    const r = await this.ctx.get(`${MOCK_PROVIDER_URL}/__state`)
    if (!r.ok()) {
      throw new Error(`mock state failed: ${r.status()} ${await r.text()}`)
    }
    return (await r.json()) as MockState
  }
}

export const MOCK_PROVIDER_NAME = "mock"
export const MOCK_MODEL_ID = "mock-chat"
export const MOCK_MODEL_NAME = `${MOCK_PROVIDER_NAME}::${MOCK_MODEL_ID}`
