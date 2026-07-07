import { describe, it, expect, vi, beforeEach } from "vitest"
import { get } from "svelte/store"

const mockGet = vi.fn()
const mockPost = vi.fn()
vi.mock("$lib/api_client", () => ({
  client: {
    GET: (...args: unknown[]) => mockGet(...args),
    POST: (...args: unknown[]) => mockPost(...args),
  },
}))

import { createBudgetStore } from "./budget_store"

const CONVERSATION_ID = "1f2e3d4c-5b6a-4789-8abc-def012345678"

function status(overrides: Record<string, unknown> = {}) {
  return {
    conversation_id: CONVERSATION_ID,
    budget_usd: 5,
    spent_usd: 1,
    remaining_usd: 4,
    exhausted: false,
    unpriced_runs: 0,
    unpriced_tokens: 0,
    ...overrides,
  }
}

beforeEach(() => {
  mockGet.mockReset()
  mockPost.mockReset()
})

describe("createBudgetStore", () => {
  it("starts null and stays null with no conversation", async () => {
    const store = createBudgetStore()
    expect(get(store)).toBeNull()
    await store.refresh()
    expect(mockGet).not.toHaveBeenCalled()
  })

  it("fetches status when a conversation is set", async () => {
    mockGet.mockResolvedValue({ data: status(), error: undefined })
    const store = createBudgetStore()
    store.setConversation(CONVERSATION_ID)
    // setConversation fires a background refresh; await an explicit one to
    // deterministically observe the resolved status.
    await store.refresh()
    expect(mockGet).toHaveBeenCalledWith("/api/chat/budget/{conversation_id}", {
      params: { path: { conversation_id: CONVERSATION_ID } },
    })
    expect(get(store)?.budget_usd).toBe(5)
  })

  it("clears status and does not refetch for the same conversation", async () => {
    mockGet.mockResolvedValue({ data: status(), error: undefined })
    const store = createBudgetStore()
    store.setConversation(CONVERSATION_ID)
    await Promise.resolve()
    mockGet.mockClear()
    store.setConversation(CONVERSATION_ID)
    expect(mockGet).not.toHaveBeenCalled()
  })

  it("resets to null when the conversation is cleared", async () => {
    mockGet.mockResolvedValue({ data: status(), error: undefined })
    const store = createBudgetStore()
    store.setConversation(CONVERSATION_ID)
    await Promise.resolve()
    store.setConversation(null)
    expect(get(store)).toBeNull()
  })

  it("setBudget POSTs and updates the store", async () => {
    const store = createBudgetStore()
    store.setConversation(CONVERSATION_ID)
    mockPost.mockResolvedValue({
      data: status({ budget_usd: 10, remaining_usd: 9 }),
      error: undefined,
    })
    const result = await store.setBudget(10)
    expect(result.ok).toBe(true)
    expect(mockPost).toHaveBeenCalledWith(
      "/api/chat/budget/{conversation_id}",
      {
        params: { path: { conversation_id: CONVERSATION_ID } },
        body: { budget_usd: 10 },
      },
    )
    expect(get(store)?.budget_usd).toBe(10)
  })

  it("setBudget fails cleanly with no conversation", async () => {
    const store = createBudgetStore()
    const result = await store.setBudget(10)
    expect(result.ok).toBe(false)
    expect(mockPost).not.toHaveBeenCalled()
  })

  it("setBudget surfaces an API error", async () => {
    const store = createBudgetStore()
    store.setConversation(CONVERSATION_ID)
    mockPost.mockResolvedValue({ data: undefined, error: { detail: "bad" } })
    const result = await store.setBudget(-1)
    expect(result.ok).toBe(false)
  })

  it("setBudget surfaces the server's error detail/message when present", async () => {
    const store = createBudgetStore()
    store.setConversation(CONVERSATION_ID)
    mockPost.mockResolvedValue({
      data: undefined,
      error: { detail: "budget_usd must be a non-negative finite number" },
    })
    const detailResult = await store.setBudget(-1)
    expect(detailResult.error).toBe(
      "budget_usd must be a non-negative finite number",
    )

    // Also handles the desktop `{ message }` shape.
    mockPost.mockResolvedValue({
      data: undefined,
      error: { message: "Invalid conversation id" },
    })
    const messageResult = await store.setBudget(1)
    expect(messageResult.error).toBe("Invalid conversation id")
  })

  it("ignores a stale refresh response for a conversation switched away from", async () => {
    const OTHER = "9e8d7c6b-5a49-4321-9fed-cba987654321"
    // A deferred GET for conversation A that we resolve only after switching to B.
    let resolveA: (v: unknown) => void = () => {}
    const aPending = new Promise((r) => {
      resolveA = r
    })
    mockGet.mockImplementation((_url, opts) => {
      const cid = opts.params.path.conversation_id
      if (cid === CONVERSATION_ID) return aPending
      // B resolves immediately with its own status.
      return Promise.resolve({
        data: status({ conversation_id: OTHER, budget_usd: 99 }),
        error: undefined,
      })
    })

    const store = createBudgetStore()
    store.setConversation(CONVERSATION_ID) // fires the slow A refresh
    // Switch to B before A resolves, then settle B deterministically.
    store.setConversation(OTHER)
    await store.refresh()
    expect(get(store)?.conversation_id).toBe(OTHER)

    // Now A's slow response arrives — it must be dropped, not adopted.
    resolveA({ data: status({ budget_usd: 5 }), error: undefined })
    await aPending
    await Promise.resolve()
    expect(get(store)?.conversation_id).toBe(OTHER)
    expect(get(store)?.budget_usd).toBe(99)
  })
})
