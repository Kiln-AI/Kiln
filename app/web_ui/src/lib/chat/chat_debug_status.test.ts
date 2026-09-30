import { describe, it, expect, beforeEach, vi } from "vitest"
import { get } from "svelte/store"

const getMock = vi.hoisted(() => vi.fn())

vi.mock("$lib/api_client", () => ({
  client: { GET: getMock },
}))

const { chat_debug_log_enabled, load_chat_debug_status } = await import(
  "./chat_debug_status"
)

beforeEach(() => {
  getMock.mockReset()
  chat_debug_log_enabled.set(false)
})

describe("load_chat_debug_status", () => {
  it("reads the debug status endpoint", async () => {
    getMock.mockResolvedValue({ data: { debug_log_enabled: true } })
    await load_chat_debug_status()
    expect(getMock).toHaveBeenCalledWith("/api/chat/debug_status")
    expect(get(chat_debug_log_enabled)).toBe(true)
  })

  it("reads off when the log is off", async () => {
    chat_debug_log_enabled.set(true)
    getMock.mockResolvedValue({ data: { debug_log_enabled: false } })
    await load_chat_debug_status()
    expect(get(chat_debug_log_enabled)).toBe(false)
  })

  it("reads off on an error response", async () => {
    getMock.mockResolvedValue({ data: undefined, error: { detail: "nope" } })
    await load_chat_debug_status()
    expect(get(chat_debug_log_enabled)).toBe(false)
  })

  it("never throws when the request fails", async () => {
    getMock.mockRejectedValue(new TypeError("network down"))
    await expect(load_chat_debug_status()).resolves.toBeUndefined()
    expect(get(chat_debug_log_enabled)).toBe(false)
  })
})
