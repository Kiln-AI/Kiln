import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"

const pricing = {
  openai: { models: { "gpt-x": { cost: { input: 1, output: 2 } } } },
}

function ok_response(body: unknown) {
  return { ok: true, json: async () => body }
}

async function import_fresh() {
  return await import("./price")
}

describe("fetchPricingData", () => {
  const fetch_mock = vi.fn()

  beforeEach(() => {
    fetch_mock.mockReset()
    vi.stubGlobal("fetch", fetch_mock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.resetModules()
  })

  it("caches a successful fetch", async () => {
    const { fetchPricingData, getModelPrice } = await import_fresh()
    fetch_mock.mockResolvedValue(ok_response(pricing))

    expect(await fetchPricingData()).toEqual(pricing)
    expect(await fetchPricingData()).toEqual(pricing)

    expect(fetch_mock).toHaveBeenCalledTimes(1)
    expect(getModelPrice("openai", "gpt-x")).toEqual({
      inputPrice: 1,
      outputPrice: 2,
    })
  })

  it("shares one request between concurrent callers", async () => {
    const { fetchPricingData } = await import_fresh()
    fetch_mock.mockResolvedValue(ok_response(pricing))

    const [a, b] = await Promise.all([fetchPricingData(), fetchPricingData()])

    expect(fetch_mock).toHaveBeenCalledTimes(1)
    expect(a).toEqual(pricing)
    expect(b).toEqual(pricing)
  })

  it.each([
    ["a network error", () => Promise.reject(new Error("offline"))],
    ["a non-ok response", () => Promise.resolve({ ok: false })],
    ["an invalid body", () => Promise.resolve(ok_response(null))],
  ])("retries on the next call after %s", async (_label, fail) => {
    const { fetchPricingData, getModelPrice } = await import_fresh()
    fetch_mock.mockImplementationOnce(fail)

    expect(await fetchPricingData()).toBeNull()

    fetch_mock.mockResolvedValueOnce(ok_response(pricing))
    expect(await fetchPricingData()).toEqual(pricing)

    expect(fetch_mock).toHaveBeenCalledTimes(2)
    expect(getModelPrice("openai", "gpt-x").inputPrice).toBe(1)
  })
})
