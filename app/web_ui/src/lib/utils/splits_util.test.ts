import { describe, it, expect } from "vitest"
import {
  allocate_splits,
  encode_splits_for_url,
  get_splits_from_url_param,
  splits_equal,
} from "./splits_util"

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

describe("allocate_splits", () => {
  function total(splits: Record<string, number>) {
    return Object.values(splits).reduce((sum, value) => sum + value, 0)
  }

  it("keeps weights that already total 100 as-is", () => {
    expect(
      allocate_splits([
        { tag: "train", weight: 40 },
        { tag: "val", weight: 25 },
        { tag: "test", weight: 25 },
        { tag: "golden", weight: 10 },
      ]),
    ).toEqual({ train: 0.4, val: 0.25, test: 0.25, golden: 0.1 })
  })

  it("rescales the remaining weights when entries are dropped", () => {
    expect(
      allocate_splits([
        { tag: "test", weight: 25 },
        { tag: "golden", weight: 10 },
      ]),
    ).toEqual({ test: 0.71, golden: 0.29 })
  })

  it("gives leftover points to the largest remainders, not the first entries", () => {
    // 40/25/25 of 90 is 44.44/27.77/27.77: floors sum to 98, and both of the two points go
    // to the two larger remainders rather than to whoever comes first.
    expect(
      allocate_splits([
        { tag: "train", weight: 40 },
        { tag: "val", weight: 25 },
        { tag: "test", weight: 25 },
      ]),
    ).toEqual({ train: 0.44, val: 0.28, test: 0.28 })
  })

  it("gives everything to a lone entry regardless of its weight", () => {
    expect(allocate_splits([{ tag: "test", weight: 25 }])).toEqual({ test: 1 })
  })

  it("breaks remainder ties by the caller's order", () => {
    // Three equal weights: 33.33 each, floors sum to 99, and the single leftover point goes
    // to the first of the tied entries.
    expect(
      allocate_splits([
        { tag: "a", weight: 1 },
        { tag: "b", weight: 1 },
        { tag: "c", weight: 1 },
      ]),
    ).toEqual({ a: 0.34, b: 0.33, c: 0.33 })
  })

  it("sums to exactly 1 for every subset of the eval split weights", () => {
    const weights = [
      { tag: "train", weight: 40 },
      { tag: "val", weight: 25 },
      { tag: "test", weight: 25 },
      { tag: "golden", weight: 10 },
    ]
    for (let mask = 1; mask < 1 << weights.length; mask++) {
      const subset = weights.filter((_, index) => mask & (1 << index))
      const splits = allocate_splits(subset)
      expect(Object.keys(splits).length).toBe(subset.length)
      expect(total(splits)).toBeCloseTo(1, 10)
      // Values must survive the round trip through the URL param, which rejects splits
      // that don't sum to 1.
      expect(get_splits_from_url_param(encode_splits_for_url(splits))).toEqual(
        splits,
      )
    }
  })

  it("folds repeated tags into one entry instead of losing a share", () => {
    // Two splits can name the same tag. Collapsing them by key would drop a weight and leave
    // the total under 1, so they're summed: 25 + 10 of 75 is 46.66, and 40 of 75 is 53.33.
    const splits = allocate_splits([
      { tag: "shared", weight: 25 },
      { tag: "train", weight: 40 },
      { tag: "shared", weight: 10 },
    ])
    expect(splits).toEqual({ shared: 0.47, train: 0.53 })
    expect(total(splits)).toBeCloseTo(1, 10)
  })

  it("drops entries with no tag or no weight", () => {
    expect(
      allocate_splits([
        { tag: "", weight: 40 },
        { tag: "zero", weight: 0 },
        { tag: "negative", weight: -10 },
        { tag: "test", weight: 25 },
      ]),
    ).toEqual({ test: 1 })
  })

  it("returns no splits when there is nothing to allocate", () => {
    expect(allocate_splits([])).toEqual({})
    expect(allocate_splits([{ tag: "test", weight: 0 }])).toEqual({})
  })
})
