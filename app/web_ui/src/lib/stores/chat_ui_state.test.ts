import { describe, it, expect, vi, afterEach } from "vitest"
import { get } from "svelte/store"

describe("chat_ui_state store", () => {
  afterEach(() => {
    vi.resetModules()
    vi.doUnmock("$lib/chat/chat_ui_storage")
    vi.doUnmock("$app/environment")
  })

  async function importFresh({
    browser = true,
    initial = true,
  }: {
    browser?: boolean
    initial?: boolean
  }) {
    vi.resetModules()
    const getMock = vi.fn(() => initial)
    const setMock = vi.fn()
    vi.doMock("$app/environment", () => ({ browser }))
    vi.doMock("$lib/chat/chat_ui_storage", () => ({
      getChatBarExpanded: getMock,
      setChatBarExpanded: setMock,
    }))
    const mod = await import("./chat_ui_state")
    return { mod, getMock, setMock }
  }

  it("initializes the store from getChatBarExpanded when browser is true", async () => {
    const { mod, getMock } = await importFresh({
      browser: true,
      initial: false,
    })
    expect(getMock).toHaveBeenCalledTimes(1)
    expect(get(mod.chatBarExpanded)).toBe(false)
  })

  it("initializes the store to true (default) when browser is false", async () => {
    const { mod, getMock } = await importFresh({ browser: false })
    expect(getMock).not.toHaveBeenCalled()
    expect(get(mod.chatBarExpanded)).toBe(true)
  })

  it("setChatBarExpanded(true) updates the store and persists true", async () => {
    const { mod, setMock } = await importFresh({
      browser: true,
      initial: false,
    })
    mod.setChatBarExpanded(true)
    expect(get(mod.chatBarExpanded)).toBe(true)
    expect(setMock).toHaveBeenCalledWith(true)
  })

  it("setChatBarExpanded(false) updates the store and persists false", async () => {
    const { mod, setMock } = await importFresh({ browser: true, initial: true })
    mod.setChatBarExpanded(false)
    expect(get(mod.chatBarExpanded)).toBe(false)
    expect(setMock).toHaveBeenCalledWith(false)
  })

  it("setChatBarExpanded does not persist when browser is false", async () => {
    const { mod, setMock } = await importFresh({ browser: false })
    mod.setChatBarExpanded(false)
    expect(get(mod.chatBarExpanded)).toBe(false)
    expect(setMock).not.toHaveBeenCalled()
  })

  it("notifies multiple subscribers of updates", async () => {
    const { mod } = await importFresh({ browser: true, initial: true })
    const a: boolean[] = []
    const b: boolean[] = []
    const unsubA = mod.chatBarExpanded.subscribe((v) => a.push(v))
    const unsubB = mod.chatBarExpanded.subscribe((v) => b.push(v))
    mod.setChatBarExpanded(false)
    expect(a[a.length - 1]).toBe(false)
    expect(b[b.length - 1]).toBe(false)
    mod.setChatBarExpanded(true)
    expect(a[a.length - 1]).toBe(true)
    expect(b[b.length - 1]).toBe(true)
    unsubA()
    unsubB()
  })
})
