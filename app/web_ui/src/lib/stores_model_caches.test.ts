import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { get } from "svelte/store"
import { LOAD_RETRY_DELAY_MS } from "./stores/retrying_loader"

const mockGET = vi.hoisted(() => vi.fn())

vi.mock("$lib/api_client", () => ({
  client: { GET: mockGET },
  base_url: "http://localhost:8757",
}))

type StoresModule = typeof import("./stores")

async function import_fresh(): Promise<StoresModule> {
  return await import("./stores")
}

const model_lists = [
  {
    name: "available_models",
    path: "/api/available_models",
    load: (m: StoresModule) => m.load_available_models(),
    value: (m: StoresModule) => get(m.available_models),
  },
  {
    name: "available_embedding_models",
    path: "/api/available_embedding_models",
    load: (m: StoresModule) => m.load_available_embedding_models(),
    value: (m: StoresModule) => get(m.available_embedding_models),
  },
  {
    name: "available_reranker_models",
    path: "/api/available_reranker_models",
    load: (m: StoresModule) => m.load_available_reranker_models(),
    value: (m: StoresModule) => get(m.available_reranker_models),
  },
]

function calls_to(path: string): number {
  return mockGET.mock.calls.filter((call) => call[0] === path).length
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((r) => {
    resolve = r
  })
  return { promise, resolve }
}

describe("provider-dependent model list caches", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockGET.mockReset()
    vi.spyOn(console, "error").mockImplementation(() => {})
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
    vi.resetModules()
  })

  describe.each(model_lists)("$name", ({ path, load, value }) => {
    it("fetches once and serves the cached list afterwards", async () => {
      const m = await import_fresh()
      mockGET.mockResolvedValue({ data: [{ id: "a" }], error: undefined })

      await load(m)
      await load(m)

      expect(calls_to(path)).toBe(1)
      expect(value(m)).toEqual([{ id: "a" }])
    })

    it("shares one request between concurrent loads", async () => {
      const m = await import_fresh()
      const pending = deferred<{ data: { id: string }[]; error: undefined }>()
      mockGET.mockReturnValueOnce(pending.promise)

      const first = load(m)
      const second = load(m)
      pending.resolve({ data: [{ id: "a" }], error: undefined })
      await Promise.all([first, second])

      expect(calls_to(path)).toBe(1)
      expect(value(m)).toEqual([{ id: "a" }])
    })

    it("does not retry immediately after an error", async () => {
      const m = await import_fresh()
      mockGET.mockResolvedValue({ data: undefined, error: { detail: "boom" } })

      await load(m)
      await load(m)

      expect(calls_to(path)).toBe(1)
      expect(value(m)).toEqual([])
    })

    it("retries after an error once the retry delay has passed", async () => {
      const m = await import_fresh()
      mockGET.mockResolvedValueOnce({
        data: undefined,
        error: { detail: "boom" },
      })
      await load(m)

      vi.advanceTimersByTime(LOAD_RETRY_DELAY_MS)
      mockGET.mockResolvedValueOnce({ data: [{ id: "b" }], error: undefined })
      await load(m)

      expect(calls_to(path)).toBe(2)
      expect(value(m)).toEqual([{ id: "b" }])
    })

    it("retries after a thrown network error", async () => {
      const m = await import_fresh()
      mockGET.mockRejectedValueOnce(new Error("Load failed"))
      await load(m)

      vi.advanceTimersByTime(LOAD_RETRY_DELAY_MS)
      mockGET.mockResolvedValueOnce({ data: [{ id: "c" }], error: undefined })
      await load(m)

      expect(calls_to(path)).toBe(2)
      expect(value(m)).toEqual([{ id: "c" }])
    })

    it("refetches after clear_available_models_cache", async () => {
      const m = await import_fresh()
      mockGET.mockResolvedValueOnce({ data: [{ id: "old" }], error: undefined })
      await load(m)

      m.clear_available_models_cache()
      expect(value(m)).toEqual([])

      mockGET.mockResolvedValueOnce({ data: [{ id: "new" }], error: undefined })
      await load(m)

      expect(calls_to(path)).toBe(2)
      expect(value(m)).toEqual([{ id: "new" }])
    })

    it("refetches right away after clear_available_models_cache following an error", async () => {
      const m = await import_fresh()
      mockGET.mockResolvedValueOnce({
        data: undefined,
        error: { detail: "boom" },
      })
      await load(m)

      m.clear_available_models_cache()
      mockGET.mockResolvedValueOnce({ data: [{ id: "d" }], error: undefined })
      await load(m)

      expect(calls_to(path)).toBe(2)
      expect(value(m)).toEqual([{ id: "d" }])
    })

    it("drops a response that arrives after clear_available_models_cache", async () => {
      const m = await import_fresh()
      const stale = deferred<{ data: { id: string }[]; error: undefined }>()
      mockGET.mockReturnValueOnce(stale.promise)
      const in_flight = load(m)

      m.clear_available_models_cache()
      stale.resolve({ data: [{ id: "stale" }], error: undefined })
      await in_flight

      expect(value(m)).toEqual([])

      mockGET.mockResolvedValueOnce({
        data: [{ id: "fresh" }],
        error: undefined,
      })
      await load(m)

      expect(calls_to(path)).toBe(2)
      expect(value(m)).toEqual([{ id: "fresh" }])
    })
  })

  it("clear_available_models_cache resets every provider-dependent list", async () => {
    const m = await import_fresh()
    const { available_tuning_models } = await import("./stores/fine_tune_store")
    mockGET.mockResolvedValue({ data: [{ id: "x" }], error: undefined })
    await m.load_available_models()
    await m.load_available_embedding_models()
    await m.load_available_reranker_models()
    available_tuning_models.set([])

    m.clear_available_models_cache()

    expect(get(m.available_models)).toEqual([])
    expect(get(m.available_embedding_models)).toEqual([])
    expect(get(m.available_reranker_models)).toEqual([])
    expect(get(available_tuning_models)).toBeNull()
  })
})
