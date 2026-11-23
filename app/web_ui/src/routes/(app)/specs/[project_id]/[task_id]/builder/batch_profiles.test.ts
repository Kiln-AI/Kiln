import { describe, expect, it } from "vitest"
import {
  planned_count,
  restore_batch_size,
  shares_for,
  CUSTOM_MAX,
  CUSTOM_MIN,
  DEFAULT_BATCH_SIZE,
  type BatchSize,
} from "./batch_profiles"

const size = (
  profile: BatchSize["profile"],
  custom_count = DEFAULT_BATCH_SIZE.custom_count,
): BatchSize => ({ profile, custom_count })

describe("planned_count", () => {
  it("asks for the profile's cases plus the golden six", () => {
    expect(planned_count(size("standard"))).toBe(66)
    expect(planned_count(size("deep"))).toBe(126)
    expect(planned_count(size("smoke_test"))).toBe(26)
    // The custom count rides along on every profile, and is read on none of
    // them but Custom.
    expect(planned_count(size("standard", 120))).toBe(66)
  })

  it("asks for the user's own count on Custom", () => {
    expect(planned_count(size("custom", 80))).toBe(86)
  })

  it("holds Custom inside its bounds", () => {
    // A stored count from a wider range can never plan a batch the picker
    // would refuse.
    expect(planned_count(size("custom", 5))).toBe(CUSTOM_MIN + 6)
    expect(planned_count(size("custom", 500))).toBe(CUSTOM_MAX + 6)
  })
})

describe("shares_for", () => {
  it("deals the three splits evenly on every sized profile", () => {
    for (const profile of ["standard", "deep", "custom"] as const) {
      expect(shares_for(size(profile))).toEqual([
        { split: "test", weight: 1 },
        { split: "train", weight: 1 },
        { split: "val", weight: 1 },
      ])
    }
  })

  it("gives Smoke Test a test split and nothing else", () => {
    expect(shares_for(size("smoke_test"))).toEqual([
      { split: "test", weight: 1 },
    ])
  })
})

describe("restore_batch_size", () => {
  it("restores a stored choice", () => {
    expect(restore_batch_size(size("deep", 90))).toEqual(size("deep", 90))
  })

  it("restores the default when no choice is on record", () => {
    expect(restore_batch_size(null)).toEqual(DEFAULT_BATCH_SIZE)
    expect(restore_batch_size(undefined)).toEqual(DEFAULT_BATCH_SIZE)
  })

  it("restores the default for a profile this build does not have", () => {
    expect(
      restore_batch_size({
        profile: "exhaustive",
        custom_count: 60,
      } as unknown as BatchSize),
    ).toEqual(DEFAULT_BATCH_SIZE)
  })

  it("clamps a custom count from outside its bounds", () => {
    expect(restore_batch_size(size("custom", 10)).custom_count).toBe(CUSTOM_MIN)
    expect(restore_batch_size(size("custom", 999)).custom_count).toBe(
      CUSTOM_MAX,
    )
  })
})
