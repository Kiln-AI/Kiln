import { describe, it, expect } from "vitest"
import {
  CHAT_BAR_MIN_WIDTH,
  CHAT_BAR_DEFAULT_WIDTH_LG,
  CHAT_BAR_DEFAULT_WIDTH_2XL,
  CHAT_BAR_BREAKPOINT_2XL,
  getChatBarMaxWidth,
  clampChatBarWidth,
  getChatBarDefaultWidth,
} from "./chat_bar_sizing"

describe("chat_bar_sizing", () => {
  describe("getChatBarMaxWidth", () => {
    it("returns 30% of viewport width, floored", () => {
      expect(getChatBarMaxWidth(1000)).toBe(300)
      expect(getChatBarMaxWidth(1999)).toBe(599)
      expect(getChatBarMaxWidth(2560)).toBe(768)
    })
  })

  describe("clampChatBarWidth", () => {
    it("clamps above max down to 30% of viewport", () => {
      // On a 2560px monitor, 30% = 768. If stored at 768, then viewport
      // shrinks to 1400px (30% = 420), the width should clamp to 420.
      expect(clampChatBarWidth(768, 1400)).toBe(420)
    })

    it("clamps below minimum up to MIN_WIDTH", () => {
      expect(clampChatBarWidth(100, 2000)).toBe(CHAT_BAR_MIN_WIDTH)
    })

    it("passes through values within range", () => {
      expect(clampChatBarWidth(400, 2000)).toBe(400)
    })

    it("rounds fractional values", () => {
      expect(clampChatBarWidth(400.7, 2000)).toBe(401)
    })

    it("respects min even when viewport is tiny", () => {
      // Tiny viewport would make max < min; min wins.
      expect(clampChatBarWidth(500, 600)).toBe(CHAT_BAR_MIN_WIDTH)
    })
  })

  describe("getChatBarDefaultWidth", () => {
    it("returns lg default below 2XL breakpoint", () => {
      expect(getChatBarDefaultWidth(CHAT_BAR_BREAKPOINT_2XL - 1)).toBe(
        CHAT_BAR_DEFAULT_WIDTH_LG,
      )
    })

    it("returns 2xl default at or above 2XL breakpoint", () => {
      expect(getChatBarDefaultWidth(CHAT_BAR_BREAKPOINT_2XL)).toBe(
        CHAT_BAR_DEFAULT_WIDTH_2XL,
      )
      expect(getChatBarDefaultWidth(2560)).toBe(CHAT_BAR_DEFAULT_WIDTH_2XL)
    })
  })
})
