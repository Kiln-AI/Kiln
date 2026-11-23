import { describe, it, expect } from "vitest"
import { sets_equal } from "./collections"

describe("sets_equal", () => {
  it("returns true for sets with same elements", () => {
    expect(sets_equal(new Set([1, 2, 3]), new Set([3, 2, 1]))).toBe(true)
    expect(sets_equal(new Set(), new Set())).toBe(true)
  })

  it("returns true for sets with same elements even if created from arrays with duplicates", () => {
    expect(sets_equal(new Set([1, 2, 2, 3]), new Set([3, 2, 1]))).toBe(true)
  })

  it("returns false for sets with different elements", () => {
    expect(sets_equal(new Set([1, 2, 3]), new Set([1, 2, 4]))).toBe(false)
  })

  it("returns false for sets with different sizes", () => {
    expect(sets_equal(new Set([1, 2]), new Set([1, 2, 3]))).toBe(false)
  })
})
