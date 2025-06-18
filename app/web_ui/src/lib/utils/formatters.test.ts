import { describe, it, expect } from "vitest"
import { formatSize } from "./formatters"

describe("formatters", () => {
  describe("formatSize", () => {
    const testCases = [
      { a: 0, expected: "0 B" },
      { a: 1024, expected: "1.00 KB" },
      { a: 1024 * 1024, expected: "1.00 MB" },
      { a: 1024 * 1024 * 1024, expected: "1.00 GB" },
      { a: 1024 * 1024 * 1024 * 1024, expected: "1.00 TB" },
      { a: 3, expected: "3 B" },
      { a: 3.5 * 1024, expected: "3.50 KB" },
      { a: 3.5 * 1024 * 1024, expected: "3.50 MB" },
      { a: 3.5 * 1024 * 1024 * 1024, expected: "3.50 GB" },
      { a: 3.5 * 1024 * 1024 * 1024 * 1024, expected: "3.50 TB" },
      { a: 15, expected: "15 B" },
      { a: 15.5 * 1024, expected: "15.50 KB" },
      { a: 15.5 * 1024 * 1024, expected: "15.50 MB" },
      { a: 15.5 * 1024 * 1024 * 1024, expected: "15.50 GB" },
      { a: 15.5 * 1024 * 1024 * 1024 * 1024, expected: "15.50 TB" },
    ]

    testCases.forEach(({ a, expected }) => {
      it(`should return ${expected} when formatting ${a}`, () => {
        expect(formatSize(a)).toBe(expected)
      })
    })

    it("should return unknown when the size is undefined", () => {
      expect(formatSize(undefined)).toBe("unknown")
    })

    it("should return unknown when the size is null", () => {
      expect(formatSize(null)).toBe("unknown")
    })

    it("should return unknown when the size is negative", () => {
      expect(formatSize(-1)).toBe("unknown")
    })

    it("should return unknown when the size is NaN", () => {
      expect(formatSize(NaN)).toBe("unknown")
    })
  })
})
