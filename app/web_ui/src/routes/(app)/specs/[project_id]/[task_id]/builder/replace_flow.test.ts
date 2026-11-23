import { describe, expect, it, vi } from "vitest"
import type { GroundingDrop } from "./batch_plan_guidance"
import type { SyntheticUserCaseWire } from "./builder_draft"
import {
  SIMULATED_USER_MISSING_DETAIL,
  interrupted_replacement,
  unchecked_detail,
  kept_scenarios,
  merge_cases,
  merge_drops,
  place_replacement_cases,
  plan_and_generate_replacements,
  plan_replacements,
} from "./replace_flow"

const PLAN = [
  "Refund a shipped order",
  "Close an account",
  "Change a plan",
  "Merge two accounts",
]

function drop(row: number, detail = "Nothing like it exists."): GroundingDrop {
  return { scenario_index: row, scenario: PLAN[row], drop_detail: detail }
}

function generated(
  seed: string,
  scenario_index?: number | null,
): SyntheticUserCaseWire {
  return {
    seed_prompt: seed,
    synthetic_user_info: `<persona>${seed}</persona>`,
    scenario_index,
  }
}

describe("kept_scenarios", () => {
  it("keeps the rows that didn't drop, in plan order", () => {
    expect(kept_scenarios(PLAN, [drop(3), drop(1)])).toEqual([
      "Refund a shipped order",
      "Change a plan",
    ])
  })
})

describe("plan_replacements", () => {
  it("swaps each dropped row for a new scenario, leaving kept rows in place", () => {
    const result = plan_replacements(
      PLAN,
      [drop(3), drop(1)],
      ["New A", "New B"],
    )
    expect(result.prompts).toEqual([
      "Refund a shipped order",
      "New A",
      "Change a plan",
      "New B",
    ])
    expect(result.replacements).toEqual([
      { row: 1, scenario: "New A" },
      { row: 3, scenario: "New B" },
    ])
    expect(result.unreplaced).toEqual([])
  })

  it("keeps a drop the planner returned no scenario for", () => {
    const result = plan_replacements(PLAN, [drop(1), drop(3)], ["New A"])
    expect(result.prompts).toEqual([
      "Refund a shipped order",
      "New A",
      "Change a plan",
      "Merge two accounts",
    ])
    expect(result.replacements).toEqual([{ row: 1, scenario: "New A" }])
    expect(result.unreplaced).toEqual([drop(3)])
  })

  it("leaves the original plan untouched", () => {
    const plan = [...PLAN]
    plan_replacements(plan, [drop(0)], ["New A"])
    expect(plan).toEqual(PLAN)
  })
})

describe("place_replacement_cases", () => {
  const replacements = [
    { row: 1, scenario: "New A" },
    { row: 3, scenario: "New B" },
  ]

  it("moves each case from its request position to its plan row", () => {
    const result = place_replacement_cases(
      [generated("b", 1), generated("a", 0)],
      replacements,
    )
    expect(result.cases.map((c) => [c.seed_prompt, c.scenario_index])).toEqual([
      ["a", 1],
      ["b", 3],
    ])
    expect(result.missing).toEqual([])
  })

  it("reads a case without a scenario_index at its position", () => {
    const result = place_replacement_cases(
      [generated("a"), generated("b", null)],
      replacements,
    )
    expect(result.cases.map((c) => c.scenario_index)).toEqual([1, 3])
  })

  it("drops a replacement the generator skipped", () => {
    const result = place_replacement_cases([generated("b", 1)], replacements)
    expect(result.cases.map((c) => c.scenario_index)).toEqual([3])
    expect(result.missing).toEqual([
      {
        scenario_index: 1,
        scenario: "New A",
        drop_detail: SIMULATED_USER_MISSING_DETAIL,
      },
    ])
  })

  it("places only one case on a row two cases both name", () => {
    const result = place_replacement_cases(
      [generated("a", 0), generated("again", 0), generated("b", 1)],
      replacements,
    )
    expect(result.cases.map((c) => c.seed_prompt)).toEqual(["a", "b"])
    expect(result.missing).toEqual([])
  })

  it("ignores a case naming a request position that wasn't sent", () => {
    const result = place_replacement_cases([generated("x", 7)], replacements)
    expect(result.cases).toEqual([])
    expect(result.missing).toHaveLength(2)
  })
})

describe("merge_cases", () => {
  it("swaps the cases on replaced rows and orders by row", () => {
    const kept = [generated("0", 0), generated("1", 1), generated("2", 2)]
    const merged = merge_cases(kept, new Set([1, 3]), [
      generated("new3", 3),
      generated("new1", 1),
    ])
    expect(merged.map((c) => c.seed_prompt)).toEqual(["0", "new1", "2", "new3"])
  })

  it("reads a kept case without a scenario_index at its position", () => {
    const merged = merge_cases(
      [generated("0"), generated("1"), generated("2")],
      new Set([1]),
      [generated("new1", 1)],
    )
    expect(merged.map((c) => [c.seed_prompt, c.scenario_index])).toEqual([
      ["0", 0],
      ["new1", 1],
      ["2", 2],
    ])
  })
})

describe("merge_drops", () => {
  it("joins drop lists in plan order", () => {
    expect(merge_drops([drop(3)], [], [drop(0), drop(2)])).toEqual([
      drop(0),
      drop(2),
      drop(3),
    ])
  })
})

describe("interrupted_replacement", () => {
  const kept = [generated("0", 0), generated("2", 2)]
  const drops = [drop(1), drop(3)]
  const committed = {
    prompts: [PLAN[0], "New A", PLAN[2], "New B"],
    unreplaced: [],
    missing: [
      {
        scenario_index: 3,
        scenario: "New B",
        drop_detail: SIMULATED_USER_MISSING_DETAIL,
      },
    ],
    sent_for_grounding: [generated("new1", 1)],
  }

  it("brings the screen back as it was when it stops before the commit", () => {
    expect(
      interrupted_replacement({
        kept,
        drops,
        committed: null,
        error: "Planner down.",
      }),
    ).toEqual({ grounded: kept, drops, replace_error: "Planner down." })
  })

  it("shows no error when the user stopped it before the commit", () => {
    expect(
      interrupted_replacement({ kept, drops, committed: null, error: null }),
    ).toEqual({ grounded: kept, drops, replace_error: null })
  })

  it("keeps the kept cases grounded and drops the unchecked ones after the commit", () => {
    const result = interrupted_replacement({
      kept,
      drops,
      committed,
      error: "Server unreachable.",
    })
    expect(result.grounded).toBe(kept)
    expect(result.replace_error).toBe("Server unreachable.")
    expect(result.drops).toEqual([
      {
        scenario_index: 1,
        scenario: "New A",
        drop_detail: unchecked_detail("Server unreachable."),
      },
      committed.missing[0],
    ])
    expect(result.drops[0].drop_detail).toContain("Server unreachable.")
  })

  it("says the check was stopped when the user stopped it after the commit", () => {
    const result = interrupted_replacement({
      kept,
      drops,
      committed,
      error: null,
    })
    expect(result.replace_error).toBeNull()
    expect(result.drops[0].drop_detail).toBe(
      "Kiln stopped before checking this case against your OpenEnv server.",
    )
  })
})

describe("plan_and_generate_replacements", () => {
  const drops = [drop(1), drop(3)]

  function fakes() {
    return {
      guidance: vi.fn(async (_signal: AbortSignal) => "guidance"),
      request_plan: vi.fn(
        async (
          _guidance: string,
          count: number,
          _signal: AbortSignal,
        ): Promise<{ prompts: string[] } | null> => ({
          prompts: Array.from({ length: count }, (_, i) => `New ${i}`),
        }),
      ),
      generate: vi.fn(
        async (
          scenarios: string[],
          _signal: AbortSignal,
        ): Promise<SyntheticUserCaseWire[] | null> =>
          scenarios.map((s, i) => generated(s, i)),
      ),
      on_generating: vi.fn(),
    }
  }

  function run(load: ReturnType<typeof fakes>, signal: AbortSignal) {
    return plan_and_generate_replacements({
      prompts: PLAN,
      drops,
      signal,
      ...load,
    })
  }

  async function error_name(work: Promise<unknown>): Promise<string> {
    try {
      await work
    } catch (e) {
      return (e as DOMException).name
    }
    return "resolved"
  }

  it("plans one scenario per drop and places the new cases on their rows", async () => {
    const load = fakes()
    const signal = new AbortController().signal
    const result = await run(load, signal)
    expect(load.request_plan).toHaveBeenCalledWith("guidance", 2, signal)
    expect(load.generate).toHaveBeenCalledWith(["New 0", "New 1"], signal)
    expect(load.on_generating).toHaveBeenCalledOnce()
    expect(result?.merged.prompts).toEqual([PLAN[0], "New 0", PLAN[2], "New 1"])
    expect(result?.placed.cases.map((c) => c.scenario_index)).toEqual([1, 3])
  })

  it("gives every request the same signal", async () => {
    const load = fakes()
    const signal = new AbortController().signal
    await run(load, signal)
    expect(load.guidance.mock.calls[0][0]).toBe(signal)
    expect(load.request_plan.mock.calls[0][2]).toBe(signal)
    expect(load.generate.mock.calls[0][1]).toBe(signal)
  })

  it("returns null without generating when the plan fails", async () => {
    const load = fakes()
    load.request_plan.mockResolvedValue(null)
    expect(await run(load, new AbortController().signal)).toBeNull()
    expect(load.generate).not.toHaveBeenCalled()
  })

  it("returns null when generating fails", async () => {
    const load = fakes()
    load.generate.mockResolvedValue(null)
    expect(await run(load, new AbortController().signal)).toBeNull()
  })

  it("requests no plan when aborted during the lookups before it", async () => {
    const load = fakes()
    const controller = new AbortController()
    load.guidance.mockImplementation(async () => {
      controller.abort()
      return "guidance"
    })
    expect(await error_name(run(load, controller.signal))).toBe("AbortError")
    expect(load.request_plan).not.toHaveBeenCalled()
  })

  it("generates nothing when aborted while the plan was out", async () => {
    const load = fakes()
    const controller = new AbortController()
    load.request_plan.mockImplementation(async (_g, count) => {
      controller.abort()
      return { prompts: Array.from({ length: count }, (_, i) => `New ${i}`) }
    })
    expect(await error_name(run(load, controller.signal))).toBe("AbortError")
    expect(load.generate).not.toHaveBeenCalled()
  })

  it("throws when aborted while the simulated users were written", async () => {
    const load = fakes()
    const controller = new AbortController()
    load.generate.mockImplementation(async (scenarios) => {
      controller.abort()
      return scenarios.map((s, i) => generated(s, i))
    })
    expect(await error_name(run(load, controller.signal))).toBe("AbortError")
  })
})
