import { describe, it, expect } from "vitest"
import { splits_equal } from "./splits_util"

describe("splits_equal", () => {
  it("returns true for two empty objects", () => {
    expect(splits_equal({}, {})).toBe(true)
  })

  it("returns true for identical objects", () => {
    const a = { train: 0.8, test: 0.2 }
    const b = { train: 0.8, test: 0.2 }
    expect(splits_equal(a, b)).toBe(true)
  })

  it("returns true for objects with same keys and values in different order", () => {
    const a = { train: 0.8, test: 0.2, val: 0.0 }
    const b = { test: 0.2, val: 0.0, train: 0.8 }
    expect(splits_equal(a, b)).toBe(true)
  })

  it("returns false for objects with different number of keys", () => {
    const a = { train: 0.8, test: 0.2 }
    const b = { train: 0.8 }
    expect(splits_equal(a, b)).toBe(false)
  })

  it("returns false for objects with different keys", () => {
    const a = { train: 0.8, test: 0.2 }
    const b = { train: 0.8, val: 0.2 }
    expect(splits_equal(a, b)).toBe(false)
  })

  it("returns false for objects with same keys but different values", () => {
    const a = { train: 0.8, test: 0.2 }
    const b = { train: 0.7, test: 0.3 }
    expect(splits_equal(a, b)).toBe(false)
  })

  it("returns false when first object is empty and second is not", () => {
    const a = {}
    const b = { train: 1.0 }
    expect(splits_equal(a, b)).toBe(false)
  })

  it("returns false when second object is empty and first is not", () => {
    const a = { train: 1.0 }
    const b = {}
    expect(splits_equal(a, b)).toBe(false)
  })

  it("returns true for objects with multiple keys in different order", () => {
    const a = { train: 0.6, test: 0.2, val: 0.1, holdout: 0.1 }
    const b = { holdout: 0.1, train: 0.6, val: 0.1, test: 0.2 }
    expect(splits_equal(a, b)).toBe(true)
  })

  it("handles floating point precision correctly", () => {
    const a = { train: 0.33333333 }
    const b = { train: 0.33333333 }
    expect(splits_equal(a, b)).toBe(true)
  })

  it("returns false for slightly different floating point values", () => {
    const a = { train: 0.8 }
    const b = { train: 0.80000001 }
    expect(splits_equal(a, b)).toBe(false)
  })

  it("returns true for zero values", () => {
    const a = { train: 0.8, test: 0.2, val: 0.0 }
    const b = { train: 0.8, test: 0.2, val: 0.0 }
    expect(splits_equal(a, b)).toBe(true)
  })
})
