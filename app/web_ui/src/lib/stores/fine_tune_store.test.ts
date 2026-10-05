import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { get } from "svelte/store"
import { LOAD_RETRY_DELAY_MS } from "./retrying_loader"

const mockGET = vi.hoisted(() => vi.fn())

vi.mock("$lib/api_client", () => ({
  client: { GET: mockGET },
  base_url: "http://localhost:8757",
}))

type Response = { data?: { name: string }[]; error?: unknown }

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((r) => {
    resolve = r
  })
  return { promise, resolve }
}

async function import_fresh() {
  return await import("./fine_tune_store")
}

describe("fine_tune_store", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockGET.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.resetModules()
  })

  it("loads once and serves the cached list afterwards", async () => {
    const m = await import_fresh()
    mockGET.mockResolvedValue({ data: [{ name: "a" }], error: undefined })

    await m.get_available_models()
    await m.get_available_models()

    expect(mockGET).toHaveBeenCalledTimes(1)
    expect(mockGET).toHaveBeenCalledWith("/api/finetune_providers", {})
    expect(get(m.available_tuning_models)).toEqual([{ name: "a" }])
    expect(get(m.available_models_loading)).toBe(false)
  })

  it("shares one request between concurrent loads", async () => {
    const m = await import_fresh()
    const pending = deferred<Response>()
    mockGET.mockReturnValueOnce(pending.promise)

    const first = m.get_available_models()
    const second = m.get_available_models()
    expect(get(m.available_models_loading)).toBe(true)

    pending.resolve({ data: [{ name: "a" }], error: undefined })
    await Promise.all([first, second])

    expect(mockGET).toHaveBeenCalledTimes(1)
    expect(get(m.available_tuning_models)).toEqual([{ name: "a" }])
  })

  it("drops a response that arrives after a reset and refetches", async () => {
    const m = await import_fresh()
    const stale = deferred<Response>()
    mockGET.mockReturnValueOnce(stale.promise)
    const in_flight = m.get_available_models()

    m.reset_available_tuning_models()
    stale.resolve({ data: [{ name: "stale" }], error: undefined })
    await in_flight

    expect(get(m.available_tuning_models)).toBeNull()
    expect(get(m.available_models_loading)).toBe(false)

    mockGET.mockResolvedValueOnce({
      data: [{ name: "fresh" }],
      error: undefined,
    })
    await m.get_available_models()

    expect(mockGET).toHaveBeenCalledTimes(2)
    expect(get(m.available_tuning_models)).toEqual([{ name: "fresh" }])
  })

  it("reports an error and retries only after the retry delay", async () => {
    const m = await import_fresh()
    mockGET.mockResolvedValueOnce({
      data: undefined,
      error: { message: "boom" },
    })
    await m.get_available_models()

    expect(get(m.available_models_error)).not.toBeNull()
    expect(get(m.available_models_loading)).toBe(false)

    await m.get_available_models()
    expect(mockGET).toHaveBeenCalledTimes(1)

    vi.advanceTimersByTime(LOAD_RETRY_DELAY_MS)
    mockGET.mockResolvedValueOnce({ data: [{ name: "b" }], error: undefined })
    await m.get_available_models()

    expect(mockGET).toHaveBeenCalledTimes(2)
    expect(get(m.available_tuning_models)).toEqual([{ name: "b" }])
    expect(get(m.available_models_error)).toBeNull()
  })

  it("shows a fine-tune message when the request cannot reach the server", async () => {
    const m = await import_fresh()
    mockGET.mockRejectedValueOnce(new TypeError("Load failed"))

    await m.get_available_models()

    expect(get(m.available_models_error)?.getMessage()).toBe(
      "Could not load available models for fine-tuning.",
    )
  })
})
