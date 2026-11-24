import { describe, expect, it } from "vitest"
import {
  compose_plan_guidance,
  dropped_cases_section,
  grounding_data_guide,
  join_data_guides,
  multiturn_plan_guidance,
  reset_arguments_section,
  single_turn_plan_guidance,
  data_guide_section,
} from "./batch_plan_guidance"

describe("compose_plan_guidance", () => {
  it("returns the base byte-identical when the steer is blank", () => {
    const base = multiturn_plan_guidance("be helpful")
    expect(compose_plan_guidance(base, [], "")).toBe(base)
  })

  it("returns the base byte-identical when the steer is only whitespace", () => {
    const base = single_turn_plan_guidance("be helpful")
    expect(compose_plan_guidance(base, [], "  \n\t ")).toBe(base)
  })

  it("keeps the base as a strict prefix when a steer is appended", () => {
    const base = multiturn_plan_guidance("be helpful")
    const composed = compose_plan_guidance(base, [], "Fewer refund scenarios.")
    expect(composed.startsWith(base)).toBe(true)
    expect(composed.length).toBeGreaterThan(base.length)
  })

  it("includes the steer text in the composed guidance", () => {
    const composed = compose_plan_guidance(
      "BASE",
      [],
      "Fewer refund scenarios.",
    )
    expect(composed).toContain("Fewer refund scenarios.")
  })

  it("trims surrounding whitespace off the steer", () => {
    expect(compose_plan_guidance("BASE", [], "  steer text  ")).toBe(
      compose_plan_guidance("BASE", [], "steer text"),
    )
  })

  it("leaves the arm marker readable at the start of the composed guidance", () => {
    // The mock (and anything else reading the request) identifies the arm from
    // the head of the guidance, so a steer must never displace it.
    const single = compose_plan_guidance(
      single_turn_plan_guidance("be helpful"),
      [],
      "More edge cases.",
    )
    expect(single).toContain("one single-turn task input")
    const multi = compose_plan_guidance(
      multiturn_plan_guidance("be helpful"),
      [],
      "More edge cases.",
    )
    expect(multi).not.toContain("one single-turn task input")
  })
})

// Both arms carry a world-state paragraph: the planner cannot see the live
// system the agent acts on, so no input or scenario may assume a record
// already exists. Each arm's tests pin the paragraph's wording in that arm's
// voice, its place as the second paragraph (read before the specification),
// and the arm marker at the very start, because the arm is identified from
// the head of the guidance.
const WORLD_STATE_OPENER =
  "The agent may act on a live system through tools (a database, an API, a set of records)."
const SPECIFICATION_INTRO =
  "The batch exists to stress-test the agent against this specification:"

describe("spec tag the batch planner reads", () => {
  // The planner's EVAL composition rules key off an <eval_definition> block.
  it("wraps the spec in eval_definition on both arms", () => {
    for (const guidance of [
      multiturn_plan_guidance("SPEC"),
      multiturn_plan_guidance("SPEC", { openenv: true }),
      single_turn_plan_guidance("SPEC"),
    ]) {
      expect(guidance).toContain("<eval_definition>\nSPEC\n</eval_definition>")
      expect(guidance).not.toContain("<specification>")
    }
  })
})

describe("multiturn_plan_guidance world-state rule", () => {
  const guidance = multiturn_plan_guidance("be helpful")

  it("carries the world-state paragraph in the multi-turn voice", () => {
    expect(guidance).toContain(WORLD_STATE_OPENER)
    expect(guidance).toContain(
      "Neither you nor the user can see what that system contains.",
    )
    expect(guidance).toContain(
      "Never write a scenario that depends on a specific record already existing: the user creates what the scenario later acts on, or asks the agent what exists and works from the answer.",
    )
    expect(guidance).toContain(
      "Name a specific record only when the point of the scenario is how the agent handles a record that is not found.",
    )
    // Multi-turn plans scenarios, so the single-turn wording must not leak in.
    expect(guidance).not.toContain("Never write an input that depends on")
  })

  it("places it as the second paragraph, directly before the specification block", () => {
    const paragraphs = guidance.split("\n\n")
    expect(paragraphs[1].startsWith(WORLD_STATE_OPENER)).toBe(true)
    expect(paragraphs[2].startsWith(SPECIFICATION_INTRO)).toBe(true)
  })

  it("keeps the arm marker at the exact start of the string", () => {
    expect(
      guidance.startsWith(
        "Each input is a scenario for one multi-turn synthetic-user conversation with the agent:",
      ),
    ).toBe(true)
  })
})

describe("single_turn_plan_guidance world-state rule", () => {
  const guidance = single_turn_plan_guidance("be helpful")

  it("carries the world-state paragraph in the single-turn voice", () => {
    expect(guidance).toContain(WORLD_STATE_OPENER)
    expect(guidance).toContain("You cannot see what that system contains.")
    expect(guidance).toContain(
      "Never write an input that depends on a specific record already existing: the input creates what it later acts on, or asks the agent what exists.",
    )
    expect(guidance).toContain(
      "Name a specific record only when the point of the input is how the agent handles a record that is not found.",
    )
    // Single-turn has no synthetic user, so the multi-turn wording must not leak in.
    expect(guidance).not.toContain("Neither you nor the user")
  })

  it("places it as the second paragraph, directly before the specification block", () => {
    const paragraphs = guidance.split("\n\n")
    expect(paragraphs[1].startsWith(WORLD_STATE_OPENER)).toBe(true)
    expect(paragraphs[2].startsWith(SPECIFICATION_INTRO)).toBe(true)
  })

  it("keeps the arm marker at the exact start of the string", () => {
    expect(
      guidance.startsWith("Each input is one single-turn task input:"),
    ).toBe(true)
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

describe("compose_plan_guidance sections", () => {
  it("orders base, then each section, then the steer", () => {
    const composed = compose_plan_guidance(
      "BASE",
      ["SECTION ONE", "SECTION TWO"],
      "the steer",
    )
    expect(composed).toBe(
      "BASE\n\nSECTION ONE\n\nSECTION TWO\n\nThe user has asked for this batch specifically:\nthe steer",
    )
  })

  it("skips null and blank sections", () => {
    expect(compose_plan_guidance("BASE", [null, "  ", "KEPT"], "")).toBe(
      "BASE\n\nKEPT",
    )
  })

  it("keeps the base a strict prefix with sections and a steer", () => {
    const base = multiturn_plan_guidance("be helpful", { openenv: true })
    const composed = compose_plan_guidance(base, ["SECTION"], "steer")
    expect(composed.startsWith(base)).toBe(true)
  })
})

describe("multiturn_plan_guidance on an OpenEnv build", () => {
  const openenv = multiturn_plan_guidance("be helpful", { openenv: true })

  it("swaps the world-state paragraph for the OpenEnv wording", () => {
    expect(openenv).not.toContain(
      "Neither you nor the user can see what that system contains.",
    )
    expect(openenv).toContain("The agent acts on an OpenEnv server")
    expect(openenv).toContain("never specific records, names or IDs")
  })

  it("keeps everything else the same as the default", () => {
    const plain = multiturn_plan_guidance("be helpful")
    const strip = (text: string) =>
      text
        .split("\n\n")
        .filter((_, i) => i !== 1)
        .join("\n\n")
    expect(strip(openenv)).toBe(strip(plain))
  })

  it("defaults to the plain wording", () => {
    expect(multiturn_plan_guidance("x", { openenv: false })).toBe(
      multiturn_plan_guidance("x"),
    )
  })
})

describe("reset_arguments_section", () => {
  it("passes the server's brief through, trimmed", () => {
    expect(reset_arguments_section("  ## The system\n- fixture  ")).toBe(
      "## The system\n- fixture",
    )
  })

  it("is null without a brief", () => {
    expect(reset_arguments_section(null)).toBeNull()
    expect(reset_arguments_section("   ")).toBeNull()
  })
})

describe("data_guide_section", () => {
  it("frames the guide for the planner", () => {
    const section = data_guide_section(" Support agents ask. ")
    expect(section).toContain("## Data Guide")
    expect(section).toContain(
      "<data_guide>\nSupport agents ask.\n</data_guide>",
    )
  })

  it("is null when the guide is blank", () => {
    expect(data_guide_section(null)).toBeNull()
    expect(data_guide_section(" ")).toBeNull()
  })
})

describe("dropped_cases_section", () => {
  it("lists each dropped scenario with its reason", () => {
    const section = dropped_cases_section([
      {
        scenario_index: 0,
        scenario: "Refund a shipped order",
        drop_detail: "No orders ship.",
      },
      {
        scenario_index: 3,
        scenario: "Close an account",
        drop_detail: "Accounts can't close.",
      },
    ])
    expect(section).toContain("Don't plan them again in the same form.")
    expect(section).toContain(
      "- Scenario: Refund a shipped order\n  Why it didn't fit: No orders ship.",
    )
    expect(section).toContain(
      "- Scenario: Close an account\n  Why it didn't fit: Accounts can't close.",
    )
  })

  it("lists drops where the check itself failed apart, as fine to plan again", () => {
    const section = dropped_cases_section([
      {
        scenario_index: 0,
        scenario: "Refund a shipped order",
        drop_detail: "No orders ship.",
        drop_reason: "no_fit",
      },
      {
        scenario_index: 1,
        scenario: "Close an account",
        drop_detail: "The agent ran out of tool calls.",
        drop_reason: "limit",
      },
      {
        scenario_index: 2,
        scenario: "Rename a team",
        drop_detail: "The model sent an empty reply.",
        drop_reason: "invalid_output",
      },
    ])
    expect(section).toContain(
      "<dropped_scenarios>\n- Scenario: Refund a shipped order\n  Why it didn't fit: No orders ship.\n</dropped_scenarios>",
    )
    expect(section).toContain("## Scenarios that couldn't be checked")
    expect(section).toContain("You may plan them again as they are.")
    expect(section).toContain(
      "<unchecked_scenarios>\n- Close an account\n- Rename a team\n</unchecked_scenarios>",
    )
    expect(section).not.toContain("ran out of tool calls")
  })

  it("leaves out the didn't-fit heading when only checks failed", () => {
    const section = dropped_cases_section([
      {
        scenario_index: 1,
        scenario: "Close an account",
        drop_detail: "The agent ran out of tool calls.",
        drop_reason: "limit",
      },
    ])
    expect(section).not.toContain("didn't fit the environment")
    expect(section).toContain("- Close an account")
  })

  it("is null when nothing dropped", () => {
    expect(dropped_cases_section([])).toBeNull()
  })
})

describe("single_turn_plan_guidance", () => {
  it("warns the planner off assuming records without an OpenEnv server", () => {
    const guidance = single_turn_plan_guidance("be helpful")
    expect(guidance).toContain("You cannot see what that system contains.")
    expect(guidance).not.toContain("OpenEnv")
  })

  it("lets inputs rely on a starting state on an OpenEnv build", () => {
    const guidance = single_turn_plan_guidance("be helpful", { openenv: true })
    expect(
      guidance.startsWith("Each input is one single-turn task input"),
    ).toBe(true)
    expect(guidance).toContain("starting states each input can run in")
    expect(guidance).toContain("Kiln fits each input to real data")
    expect(guidance).toContain(
      "<eval_definition>\nbe helpful\n</eval_definition>",
    )
  })
})
