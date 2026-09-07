import { describe, expect, it } from "vitest"
import {
  compose_plan_guidance,
  grounding_data_guide,
  join_data_guides,
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

describe("join_data_guides", () => {
  const guide = "# Reference Inputs\n\nShort support questions.\n"
  const grounding = grounding_data_guide({
    input: "  Where is my order?  ",
  }) as string

  it("puts the guide first and the grounding second under two headers", () => {
    const joined = join_data_guides(guide, grounding) as string
    expect(joined.startsWith("Data Guide:\n")).toBe(true)
    expect(joined.indexOf(guide)).toBeLessThan(joined.indexOf(grounding))
    expect(joined).toContain("\n\nGrounding Example:\n")
    expect(joined).toContain(guide)
    expect(joined).toContain(grounding)
  })

  it("sends a lone guide byte-identical and untrimmed", () => {
    expect(join_data_guides(guide, null)).toBe(guide)
    expect(join_data_guides(guide, "")).toBe(guide)
    expect(join_data_guides(guide, "   \n")).toBe(guide)
  })

  it("sends a lone grounding sample byte-identical — what a task with no guide sent before", () => {
    expect(join_data_guides(null, grounding)).toBe(grounding)
    expect(join_data_guides("", grounding)).toBe(grounding)
    expect(join_data_guides(" \t ", grounding)).toBe(grounding)
  })

  it("treats blank on both sides as no guide at all", () => {
    expect(join_data_guides(null, null)).toBeNull()
    expect(join_data_guides("", "")).toBeNull()
    expect(join_data_guides("  ", null)).toBeNull()
  })

  it("keeps the dataset sample's own wrapper intact inside the join", () => {
    const joined = join_data_guides(guide, grounding) as string
    expect(joined).toContain("<example_input>")
    expect(joined).toContain("</example_input>")
  })
})
