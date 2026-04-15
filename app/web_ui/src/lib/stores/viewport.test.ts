// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from "vitest"
import { get } from "svelte/store"

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnySpy = any

describe("viewport store (browser)", () => {
  let addListenerSpy: AnySpy
  let removeListenerSpy: AnySpy

  afterEach(() => {
    vi.resetModules()
    vi.doUnmock("$app/environment")
    addListenerSpy?.mockRestore()
    removeListenerSpy?.mockRestore()
  })

  async function importFreshWithWidth(initialWidth: number) {
    vi.resetModules()
    vi.doMock("$app/environment", () => ({ browser: true }))
    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      writable: true,
      value: initialWidth,
    })
    addListenerSpy = vi.spyOn(window, "addEventListener")
    removeListenerSpy = vi.spyOn(window, "removeEventListener")
    return await import("./viewport")
  }

  function setWidthAndDispatch(width: number) {
    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      writable: true,
      value: width,
    })
    window.dispatchEvent(new Event("resize"))
  }

  it("isLg is false when width < 1024", async () => {
    const mod = await importFreshWithWidth(800)
    const unsub = mod.viewportWidth.subscribe(() => {})
    expect(get(mod.isLg)).toBe(false)
    unsub()
  })

  it("isLg is true when width >= 1024", async () => {
    const mod = await importFreshWithWidth(1200)
    const unsub = mod.viewportWidth.subscribe(() => {})
    expect(get(mod.isLg)).toBe(true)
    unsub()
  })

  it("isNarrowViewport is true when width < 1550", async () => {
    const mod = await importFreshWithWidth(1500)
    const unsub = mod.viewportWidth.subscribe(() => {})
    expect(get(mod.isNarrowViewport)).toBe(true)
    unsub()
  })

  it("isNarrowViewport is false when width >= 1550", async () => {
    const mod = await importFreshWithWidth(2100)
    const unsub = mod.viewportWidth.subscribe(() => {})
    expect(get(mod.isNarrowViewport)).toBe(false)
    unsub()
  })

  it("isNarrowViewport is true at the 1549 boundary (just below threshold)", async () => {
    const mod = await importFreshWithWidth(1549)
    const unsub = mod.viewportWidth.subscribe(() => {})
    expect(get(mod.isNarrowViewport)).toBe(true)
    unsub()
  })

  it("isNarrowViewport is false at exactly 1550 (threshold)", async () => {
    const mod = await importFreshWithWidth(1550)
    const unsub = mod.viewportWidth.subscribe(() => {})
    expect(get(mod.isNarrowViewport)).toBe(false)
    unsub()
  })

  it("isNarrowViewport is false at 1551 (just above threshold)", async () => {
    const mod = await importFreshWithWidth(1551)
    const unsub = mod.viewportWidth.subscribe(() => {})
    expect(get(mod.isNarrowViewport)).toBe(false)
    unsub()
  })

  it("viewportWidth updates when window dispatches a resize event", async () => {
    const mod = await importFreshWithWidth(1000)
    const seen: number[] = []
    const unsub = mod.viewportWidth.subscribe((w) => seen.push(w))
    expect(seen[0]).toBe(1000)

    setWidthAndDispatch(1500)
    expect(seen[seen.length - 1]).toBe(1500)

    setWidthAndDispatch(600)
    expect(seen[seen.length - 1]).toBe(600)
    unsub()
  })

  it("attaches resize listener on first subscribe and removes it on last unsubscribe", async () => {
    const mod = await importFreshWithWidth(1000)
    const resizeAddsBeforeSubscribe = addListenerSpy.mock.calls.filter(
      (c: unknown[]) => c[0] === "resize",
    ).length
    expect(resizeAddsBeforeSubscribe).toBe(0)

    const unsub1 = mod.viewportWidth.subscribe(() => {})
    const resizeAddsAfterFirst = addListenerSpy.mock.calls.filter(
      (c: unknown[]) => c[0] === "resize",
    ).length
    expect(resizeAddsAfterFirst).toBe(1)

    const unsub2 = mod.viewportWidth.subscribe(() => {})
    const resizeAddsAfterSecond = addListenerSpy.mock.calls.filter(
      (c: unknown[]) => c[0] === "resize",
    ).length
    // readable manages single start/stop lifecycle regardless of subscriber count
    expect(resizeAddsAfterSecond).toBe(1)

    unsub1()
    const resizeRemovesAfterFirstUnsub = removeListenerSpy.mock.calls.filter(
      (c: unknown[]) => c[0] === "resize",
    ).length
    expect(resizeRemovesAfterFirstUnsub).toBe(0)

    unsub2()
    const resizeRemovesAfterAllUnsub = removeListenerSpy.mock.calls.filter(
      (c: unknown[]) => c[0] === "resize",
    ).length
    expect(resizeRemovesAfterAllUnsub).toBe(1)
  })
})

describe("viewport store (SSR / non-browser)", () => {
  afterEach(() => {
    vi.resetModules()
    vi.doUnmock("$app/environment")
  })

  it("uses fallback width 0 and does not touch window when browser is false", async () => {
    vi.resetModules()
    vi.doMock("$app/environment", () => ({ browser: false }))
    const mod = await import("./viewport")
    const unsub = mod.viewportWidth.subscribe(() => {})
    expect(get(mod.viewportWidth)).toBe(0)
    expect(get(mod.isLg)).toBe(false)
    expect(get(mod.isNarrowViewport)).toBe(true)
    unsub()
  })
})
