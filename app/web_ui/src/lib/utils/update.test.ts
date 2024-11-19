import { describe, it, expect, vi, beforeEach } from "vitest"
import { check_for_update, semantic_version_compare } from "./update"

// Mock the app_version
vi.mock("./update", async (importOriginal) => {
  const mod = await importOriginal()
  return {
    ...(mod as object),
    app_version: "1.2.3",
  }
})

describe("update utilities", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe("check_for_update", () => {
    it("should detect when an update is available", async () => {
      // Mock fetch response for a newer version
      global.fetch = vi.fn().mockResolvedValue({
        json: () =>
          Promise.resolve({
            html_url: "https://github.com/Kiln-AI/Kiln/releases/tag/999.6.0",
            tag_name: "999.6.0",
          }),
      })

      const result = await check_for_update()
      expect(result).toEqual({
        has_update: true,
        latest_version: "999.6.0",
        link: "https://github.com/Kiln-AI/Kiln/releases/tag/999.6.0",
      })
    })

    it("should handle when no update is available", async () => {
      // Mock fetch response for same version
      global.fetch = vi.fn().mockResolvedValue({
        json: () =>
          Promise.resolve({
            html_url: "https://github.com/Kiln-AI/Kiln/releases/tag/0.0.1",
            tag_name: "0.0.1",
          }),
      })

      const result = await check_for_update()
      expect(result).toEqual({
        has_update: false,
        latest_version: "0.0.1",
        link: "https://github.com/Kiln-AI/Kiln/releases/tag/0.0.1",
      })
    })

    it("should handle fetch errors", async () => {
      global.fetch = vi.fn().mockRejectedValue(new Error("Network error"))

      const result = await check_for_update()
      expect(result).toHaveProperty("message")
      expect(result).toHaveProperty("name", "KilnError")
    })

    it("should handle invalid response data", async () => {
      global.fetch = vi.fn().mockResolvedValue({
        json: () =>
          Promise.resolve({
            // Missing required fields
          }),
      })

      const result = await check_for_update()
      expect(result).toHaveProperty("message", "Failed to fetch update data")
      expect(result).toHaveProperty("name", "KilnError")
    })
  })

  describe("semantic_version_compare", () => {
    const testCases = [
      { a: "1.2.4", b: "1.2.3", expected: true }, // Higher patch
      { a: "1.3.0", b: "1.2.3", expected: true }, // Higher minor
      { a: "2.0.0", b: "1.2.3", expected: true }, // Higher major
      { a: "1.2.3", b: "1.2.3", expected: false }, // Equal versions
      { a: "1.2.2", b: "1.2.3", expected: false }, // Lower patch
      { a: "1.1.9", b: "1.2.3", expected: false }, // Lower minor
      { a: "0.9.9", b: "1.2.3", expected: false }, // Lower major
      { a: "1.2.3.4", b: "1.2.3", expected: true }, // Extra version number
      { a: "1.2", b: "1.2.3", expected: false }, // Missing version number
      { a: "1.2.3-beta", b: "1.2.3", expected: false }, // With suffix
      { a: "1.2.4-beta", b: "1.2.3", expected: false }, // With suffix, (this is desired, 'latest' tag used for filter, not suffix)
      { a: "1.2.3", b: "1.2.4-beta", expected: false }, // With suffix, (this is desired, 'latest' tag used for filter, not suffix)
      { a: "v1.2.3", b: "1.2.4", expected: false }, // With leading 'v'
      { a: "1.2.4", b: "v1.2.3", expected: true }, // With leading 'v'
    ]

    testCases.forEach(({ a, b, expected }) => {
      it(`should return ${expected} when comparing ${a} to ${b}`, () => {
        expect(semantic_version_compare(a, b)).toBe(expected)
      })
    })
  })
})
