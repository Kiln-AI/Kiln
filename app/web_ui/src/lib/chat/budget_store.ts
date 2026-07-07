import { writable, get, type Readable } from "svelte/store"
import { client } from "$lib/api_client"
import type { components } from "$lib/api_schema"

export type BudgetStatus = components["schemas"]["BudgetStatusResponse"]

export interface BudgetStore extends Readable<BudgetStatus | null> {
  /** Point the store at a conversation. Clears state + refreshes when it changes. */
  setConversation(conversationId: string | null): void
  /** Re-fetch the current conversation's budget status. No-op without one. */
  refresh(): Promise<void>
  /** Set/extend (absolute) the budget; ``null`` clears it. Refreshes on success. */
  setBudget(budgetUsd: number | null): Promise<{ ok: boolean; error?: string }>
}

/**
 * Tracks the active conversation's spend-budget status (from the local ledger
 * on the desktop server). Read-through cache: the chat store refreshes it after
 * tool rounds / trace events, and a light poll keeps the meter live during long
 * assistant-triggered operations (see chat.svelte).
 */
export function createBudgetStore(): BudgetStore {
  const status = writable<BudgetStatus | null>(null)
  let conversationId: string | null = null

  function setConversation(next: string | null): void {
    if (next === conversationId) return
    conversationId = next
    status.set(null)
    if (next) void refresh()
  }

  async function refresh(): Promise<void> {
    const cid = conversationId
    if (!cid) return
    try {
      const { data, error } = await client.GET(
        "/api/chat/budget/{conversation_id}",
        { params: { path: { conversation_id: cid } } },
      )
      // Ignore a response for a conversation we've since switched away from.
      if (cid !== conversationId) return
      if (error) return
      status.set(data ?? null)
    } catch {
      /* network/desktop error — keep the last known status */
    }
  }

  async function setBudget(
    budgetUsd: number | null,
  ): Promise<{ ok: boolean; error?: string }> {
    const cid = conversationId
    if (!cid) return { ok: false, error: "No active conversation" }
    try {
      const { data, error } = await client.POST(
        "/api/chat/budget/{conversation_id}",
        {
          params: { path: { conversation_id: cid } },
          body: { budget_usd: budgetUsd },
        },
      )
      if (error) {
        // Surface the server's own message when it sent one (e.g. a validation
        // detail), falling back to a generic message. The desktop error shape
        // is `{ message }` or FastAPI's `{ detail }`.
        const detail =
          (error as { detail?: unknown; message?: unknown })?.detail ??
          (error as { message?: unknown })?.message
        return {
          ok: false,
          error:
            typeof detail === "string" ? detail : "Couldn't update the budget",
        }
      }
      if (cid === conversationId && data) status.set(data)
      return { ok: true }
    } catch (e) {
      return { ok: false, error: e instanceof Error ? e.message : String(e) }
    }
  }

  return {
    subscribe: status.subscribe,
    setConversation,
    refresh,
    setBudget,
  }
}

export const budget_store: BudgetStore = createBudgetStore()

/** True when a budget is set and fully spent. */
export function isBudgetExhausted(status: BudgetStatus | null): boolean {
  return !!status?.exhausted
}

/** True when some model calls couldn't be priced (partial tracking). */
export function isBudgetPartiallyTracked(status: BudgetStatus | null): boolean {
  return (status?.unpriced_runs ?? 0) > 0
}

// Re-export get for consumers that need a one-shot read.
export { get as getBudgetSnapshot }
