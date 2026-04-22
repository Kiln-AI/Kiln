import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import {
  getChatBarExpanded,
  setChatBarExpanded,
  getChatBarWidth,
  setChatBarWidth,
} from "./chat_ui_storage"

describe("chat_ui_storage", () => {
  let sessionStore: Record<string, string>
  let localStore: Record<string, string>

  beforeEach(() => {
    sessionStore = {}
    localStore = {}

    vi.stubGlobal("sessionStorage", {
      getItem: vi.fn((key: string) => sessionStore[key] ?? null),
      setItem: vi.fn((key: string, value: string) => {
        sessionStore[key] = value
      }),
    })

    vi.stubGlobal("localStorage", {
      getItem: vi.fn((key: string) => localStore[key] ?? null),
      setItem: vi.fn((key: string, value: string) => {
        localStore[key] = value
      }),
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  describe("getChatBarExpanded", () => {
    it("returns true by default when no storage is set", () => {
      expect(getChatBarExpanded()).toBe(true)
    })

    it("reads from sessionStorage first", () => {
      sessionStore["chat_bar_expanded"] = "false"
      localStore["chat_bar_expanded"] = "true"
      expect(getChatBarExpanded()).toBe(false)
    })

    it("falls back to localStorage when sessionStorage is empty", () => {
      localStore["chat_bar_expanded"] = "false"
      expect(getChatBarExpanded()).toBe(false)
    })

    it("returns true for localStorage true value", () => {
      localStore["chat_bar_expanded"] = "true"
      expect(getChatBarExpanded()).toBe(true)
    })

    it("returns true for sessionStorage true value", () => {
      sessionStore["chat_bar_expanded"] = "true"
      expect(getChatBarExpanded()).toBe(true)
    })

    it("treats non-'true' values as false", () => {
      sessionStore["chat_bar_expanded"] = "invalid"
      expect(getChatBarExpanded()).toBe(false)
    })

    it("returns true when storage throws", () => {
      vi.stubGlobal("sessionStorage", {
        getItem: () => {
          throw new Error("denied")
        },
      })
      expect(getChatBarExpanded()).toBe(true)
    })
  })

  describe("setChatBarExpanded", () => {
    it("writes true to both storages", () => {
      setChatBarExpanded(true)
      expect(sessionStorage.setItem).toHaveBeenCalledWith(
        "chat_bar_expanded",
        "true",
      )
      expect(localStorage.setItem).toHaveBeenCalledWith(
        "chat_bar_expanded",
        "true",
      )
    })

    it("writes false to both storages", () => {
      setChatBarExpanded(false)
      expect(sessionStorage.setItem).toHaveBeenCalledWith(
        "chat_bar_expanded",
        "false",
      )
      expect(localStorage.setItem).toHaveBeenCalledWith(
        "chat_bar_expanded",
        "false",
      )
    })

    it("does not throw when storage is unavailable", () => {
      vi.stubGlobal("sessionStorage", {
        setItem: () => {
          throw new Error("denied")
        },
      })
      expect(() => setChatBarExpanded(true)).not.toThrow()
    })

    it("does not throw when localStorage fails after sessionStorage succeeds", () => {
      vi.stubGlobal("localStorage", {
        getItem: vi.fn((key: string) => localStore[key] ?? null),
        setItem: () => {
          throw new Error("denied")
        },
      })
      expect(() => setChatBarExpanded(true)).not.toThrow()
      expect(sessionStorage.setItem).toHaveBeenCalledWith(
        "chat_bar_expanded",
        "true",
      )
    })
  })

  describe("getChatBarWidth", () => {
    it("returns null when no storage is set", () => {
      expect(getChatBarWidth()).toBeNull()
    })

    it("reads from localStorage", () => {
      localStore["chat_bar_width"] = "400"
      expect(getChatBarWidth()).toBe(400)
    })

    it("returns null for non-numeric values", () => {
      localStore["chat_bar_width"] = "abc"
      expect(getChatBarWidth()).toBeNull()
    })

    it("returns null for zero", () => {
      localStore["chat_bar_width"] = "0"
      expect(getChatBarWidth()).toBeNull()
    })

    it("returns null for negative values", () => {
      localStore["chat_bar_width"] = "-100"
      expect(getChatBarWidth()).toBeNull()
    })

    it("returns null when storage throws", () => {
      vi.stubGlobal("localStorage", {
        getItem: () => {
          throw new Error("denied")
        },
        setItem: vi.fn(),
      })
      expect(getChatBarWidth()).toBeNull()
    })

    it("handles float values", () => {
      localStore["chat_bar_width"] = "350.5"
      expect(getChatBarWidth()).toBe(350.5)
    })
  })

  describe("setChatBarWidth", () => {
    it("writes to localStorage", () => {
      setChatBarWidth(400)
      expect(localStorage.setItem).toHaveBeenCalledWith("chat_bar_width", "400")
    })

    it("does not write to sessionStorage", () => {
      setChatBarWidth(400)
      expect(sessionStorage.setItem).not.toHaveBeenCalled()
    })

    it("does not throw when storage is unavailable", () => {
      vi.stubGlobal("localStorage", {
        getItem: vi.fn(),
        setItem: () => {
          throw new Error("denied")
        },
      })
      expect(() => setChatBarWidth(400)).not.toThrow()
    })
  })
})
