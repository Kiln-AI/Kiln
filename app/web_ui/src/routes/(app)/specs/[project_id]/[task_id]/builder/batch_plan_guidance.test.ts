import { describe, expect, it } from "vitest"
import {
  compose_plan_guidance,
  multiturn_plan_guidance,
  single_turn_plan_guidance,
} from "./batch_plan_guidance"

describe("compose_plan_guidance", () => {
  it("returns the base byte-identical when the steer is blank", () => {
    const base = multiturn_plan_guidance("be helpful")
    expect(compose_plan_guidance(base, "")).toBe(base)
  })

  it("returns the base byte-identical when the steer is only whitespace", () => {
    const base = single_turn_plan_guidance("be helpful")
    expect(compose_plan_guidance(base, "  \n\t ")).toBe(base)
  })

  it("keeps the base as a strict prefix when a steer is appended", () => {
    const base = multiturn_plan_guidance("be helpful")
    const composed = compose_plan_guidance(base, "Fewer refund scenarios.")
    expect(composed.startsWith(base)).toBe(true)
    expect(composed.length).toBeGreaterThan(base.length)
  })

  it("includes the steer text in the composed guidance", () => {
    const composed = compose_plan_guidance("BASE", "Fewer refund scenarios.")
    expect(composed).toContain("Fewer refund scenarios.")
  })

  it("trims surrounding whitespace off the steer", () => {
    expect(compose_plan_guidance("BASE", "  steer text  ")).toBe(
      compose_plan_guidance("BASE", "steer text"),
    )
  })

  it("leaves the arm marker readable at the start of the composed guidance", () => {
    // The mock (and anything else reading the request) identifies the arm from
    // the head of the guidance, so a steer must never displace it.
    const single = compose_plan_guidance(
      single_turn_plan_guidance("be helpful"),
      "More edge cases.",
    )
    expect(single).toContain("one single-turn task input")
    const multi = compose_plan_guidance(
      multiturn_plan_guidance("be helpful"),
      "More edge cases.",
    )
    expect(multi).not.toContain("one single-turn task input")
  })
})
