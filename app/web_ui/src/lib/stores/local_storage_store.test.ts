import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { get } from "svelte/store"

function stubStorage() {
  const store: Record<string, string> = {}
  return {
    store,
    mock: {
      getItem: vi.fn((key: string) => store[key] ?? null),
      setItem: vi.fn((key: string, value: string) => {
        store[key] = value
      }),
      removeItem: vi.fn((key: string) => {
        delete store[key]
      }),
    },
  }
}

describe("localStorageStore", () => {
  let storage: ReturnType<typeof stubStorage>

  beforeEach(() => {
    storage = stubStorage()
    vi.stubGlobal("window", {
      localStorage: storage.mock,
    })
    vi.stubGlobal("localStorage", storage.mock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.resetModules()
  })

  async function importFresh() {
    const mod = await import("./local_storage_store")
    return mod.localStorageStore
  }

  it("falls back to initialValue when storage is empty", async () => {
    const localStorageStore = await importFresh()
    const s = localStorageStore("test_key", { count: 0 })
    expect(get(s)).toEqual({ count: 0 })
  })

  it("restores value from localStorage", async () => {
    storage.store["test_key"] = JSON.stringify({ count: 42 })
    const localStorageStore = await importFresh()
    const s = localStorageStore("test_key", { count: 0 })
    expect(get(s)).toEqual({ count: 42 })
  })

  it("saves to localStorage on update", async () => {
    const localStorageStore = await importFresh()
    const s = localStorageStore("test_key", "initial")
    s.set("updated")
    expect(storage.store["test_key"]).toBe(JSON.stringify("updated"))
  })

  it("handles corrupt JSON by falling back to initialValue", async () => {
    storage.store["test_key"] = "not valid json{{"
    const localStorageStore = await importFresh()
    const s = localStorageStore("test_key", "fallback")
    expect(get(s)).toBe("fallback")
  })

  it("clears stale value and logs error when setItem throws", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {})
    const localStorageStore = await importFresh()
    const s = localStorageStore("big_key", "initial")
    storage.mock.setItem.mockImplementationOnce(() => {
      throw new DOMException("quota exceeded")
    })
    s.set("too_large_value")
    expect(consoleSpy).toHaveBeenCalledWith(
      expect.stringContaining("Failed to save to localStorage"),
    )
    expect(storage.mock.removeItem).toHaveBeenCalledWith("big_key")
    consoleSpy.mockRestore()
  })

  it("uses independent keys without interference", async () => {
    const localStorageStore = await importFresh()
    const a = localStorageStore("key_a", 1)
    const b = localStorageStore("key_b", 2)
    a.set(10)
    expect(get(b)).toBe(2)
    expect(storage.store["key_a"]).toBe("10")
    expect(storage.store["key_b"]).toBe("2")
  })
})

describe("sessionStorageStore", () => {
  let storage: ReturnType<typeof stubStorage>

  beforeEach(() => {
    storage = stubStorage()
    vi.stubGlobal("window", {
      sessionStorage: storage.mock,
    })
    vi.stubGlobal("sessionStorage", storage.mock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.resetModules()
  })

  async function importFresh() {
    const mod = await import("./local_storage_store")
    return mod.sessionStorageStore
  }

  it("falls back to initialValue when storage is empty", async () => {
    const sessionStorageStore = await importFresh()
    const s = sessionStorageStore("test_key", { count: 0 })
    expect(get(s)).toEqual({ count: 0 })
  })

  it("restores value from sessionStorage", async () => {
    storage.store["test_key"] = JSON.stringify({ count: 42 })
    const sessionStorageStore = await importFresh()
    const s = sessionStorageStore("test_key", { count: 0 })
    expect(get(s)).toEqual({ count: 42 })
  })

  it("saves to sessionStorage on update", async () => {
    const sessionStorageStore = await importFresh()
    const s = sessionStorageStore("test_key", "initial")
    s.set("updated")
    expect(storage.store["test_key"]).toBe(JSON.stringify("updated"))
  })

  it("handles corrupt JSON by falling back to initialValue", async () => {
    storage.store["test_key"] = "not valid json{{"
    const sessionStorageStore = await importFresh()
    const s = sessionStorageStore("test_key", "fallback")
    expect(get(s)).toBe("fallback")
  })

  it("clears stale value and logs error when setItem throws", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {})
    const sessionStorageStore = await importFresh()
    const s = sessionStorageStore("big_key", "initial")
    storage.mock.setItem.mockImplementationOnce(() => {
      throw new DOMException("quota exceeded")
    })
    s.set("too_large_value")
    expect(consoleSpy).toHaveBeenCalledWith(
      expect.stringContaining("Failed to save to sessionStorage"),
    )
    expect(storage.mock.removeItem).toHaveBeenCalledWith("big_key")
    consoleSpy.mockRestore()
  })

  it("uses independent keys without interference", async () => {
    const sessionStorageStore = await importFresh()
    const a = sessionStorageStore("key_a", 1)
    const b = sessionStorageStore("key_b", 2)
    a.set(10)
    expect(get(b)).toBe(2)
    expect(storage.store["key_a"]).toBe("10")
    expect(storage.store["key_b"]).toBe("2")
  })

  it("does not write to localStorage", async () => {
    const localStore = stubStorage()
    vi.stubGlobal("localStorage", localStore.mock)
    const sessionStorageStore = await importFresh()
    const s = sessionStorageStore("test_key", "hello")
    s.set("world")
    expect(storage.store["test_key"]).toBe(JSON.stringify("world"))
    expect(localStore.store["test_key"]).toBeUndefined()
  })
})

describe("SSR safety (no window)", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.resetModules()
  })

  it("localStorageStore uses initialValue when window is undefined", async () => {
    vi.stubGlobal("window", undefined)
    const mod = await import("./local_storage_store")
    const s = mod.localStorageStore("key", "default")
    expect(get(s)).toBe("default")
  })

  it("sessionStorageStore uses initialValue when window is undefined", async () => {
    vi.stubGlobal("window", undefined)
    const mod = await import("./local_storage_store")
    const s = mod.sessionStorageStore("key", "default")
    expect(get(s)).toBe("default")
  })
})
