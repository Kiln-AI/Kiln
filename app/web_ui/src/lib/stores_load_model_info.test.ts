import { get } from "svelte/store"
import { describe, it, expect, beforeEach, vi } from "vitest"

const GET = vi.fn()
vi.mock("$lib/api_client", () => ({ client: { GET } }))

const { load_model_info, model_info } = await import("./stores")

describe("load_model_info", () => {
  beforeEach(() => {
    GET.mockReset()
    model_info.set(null)
  })

  it("shares one request between concurrent callers", async () => {
    let resolve!: (value: unknown) => void
    GET.mockReturnValue(new Promise((r) => (resolve = r)))

    const calls = [load_model_info(), load_model_info(), load_model_info()]
    resolve({ data: { family: [] }, error: undefined })
    await Promise.all(calls)

    expect(GET).toHaveBeenCalledTimes(1)
    expect(get(model_info)).toEqual({ family: [] })
  })

  it("does not request again once the list is loaded", async () => {
    GET.mockResolvedValue({ data: { family: [] }, error: undefined })
    await load_model_info()
    await load_model_info()
    expect(GET).toHaveBeenCalledTimes(1)
  })

  it("allows a new request after a failed one", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {})
    GET.mockResolvedValueOnce({ data: undefined, error: { message: "down" } })
    await load_model_info()
    expect(get(model_info)).toBeNull()

    GET.mockResolvedValueOnce({ data: { family: [] }, error: undefined })
    await load_model_info()
    expect(GET).toHaveBeenCalledTimes(2)
    expect(get(model_info)).toEqual({ family: [] })
    consoleError.mockRestore()
  })
})
