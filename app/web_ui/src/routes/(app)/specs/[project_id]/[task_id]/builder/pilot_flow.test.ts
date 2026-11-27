import { describe, expect, it } from "vitest"
import {
  batch_after_pilot,
  first_messages,
  owner_choice_gate,
  PILOT_CASES,
  pilot_next_step,
  pilot_positions,
  pilot_save_blocked_text,
  split_pilot,
  widen_pilot_batch,
  write_review_ground,
  type FirstMessagesChoice,
} from "./pilot_flow"
import { plan_drive } from "./plan_flow"

// Records the steps of one build in call order, like the network panel would.
function recorder(choice: FirstMessagesChoice = "continue") {
  const calls: string[] = []
  const written = [{ seed_prompt: "a" }, { seed_prompt: "b" }]
  let grounded_with: unknown = null
  return {
    calls,
    written,
    grounded_with: () => grounded_with,
    steps: (
      pilot_first: boolean,
      write_result: typeof written | null = written,
    ) => ({
      pilot_first,
      write: async () => {
        calls.push("write")
        return write_result
      },
      review: async () => {
        calls.push("review")
        return choice
      },
      ground: async (cases: typeof written) => {
        calls.push("ground")
        grounded_with = cases
        return { grounded: cases.length }
      },
    }),
  }
}

describe("write_review_ground", () => {
  it("with Pilot First off, writes then grounds, as before the box existed", async () => {
    const r = recorder()
    expect(await write_review_ground(r.steps(false))).toEqual({ grounded: 2 })
    expect(r.calls).toEqual(["write", "ground"])
    // The written cases reach grounding untouched (the same array).
    expect(r.grounded_with()).toBe(r.written)
  })

  it("with Pilot First off, never asks the owner, whatever the answer would be", async () => {
    const r = recorder("refine")
    await write_review_ground(r.steps(false))
    expect(r.calls).toEqual(["write", "ground"])
  })

  it("with Pilot First on, the owner reads the messages before any grounding call", async () => {
    const r = recorder("continue")
    expect(await write_review_ground(r.steps(true))).toEqual({ grounded: 2 })
    expect(r.calls).toEqual(["write", "review", "ground"])
    expect(r.grounded_with()).toBe(r.written)
  })

  it("on Refine, stops before grounding and returns null", async () => {
    const r = recorder("refine")
    expect(await write_review_ground(r.steps(true))).toBeNull()
    expect(r.calls).toEqual(["write", "review"])
  })

  it("stops after a failed write, on or off", async () => {
    for (const on of [false, true]) {
      const r = recorder()
      expect(await write_review_ground(r.steps(on, null))).toBeNull()
      expect(r.calls).toEqual(["write"])
    }
  })
})

describe("owner_choice_gate", () => {
  it("resolves with the owner's choice", async () => {
    const gate = owner_choice_gate<FirstMessagesChoice>()
    const waiting = gate.wait(new AbortController().signal)
    expect(gate.pending()).toBe(true)
    gate.choose("refine")
    expect(await waiting).toBe("refine")
    expect(gate.pending()).toBe(false)
  })

  it("rejects with an AbortError when the build is cancelled mid-wait", async () => {
    const gate = owner_choice_gate<FirstMessagesChoice>()
    const controller = new AbortController()
    const waiting = gate.wait(controller.signal)
    controller.abort()
    await expect(waiting).rejects.toMatchObject({ name: "AbortError" })
    expect(gate.pending()).toBe(false)
    // A late click after the abort does nothing.
    gate.choose("continue")
  })

  it("rejects at once on a signal already aborted", async () => {
    const gate = owner_choice_gate<FirstMessagesChoice>()
    const controller = new AbortController()
    controller.abort()
    await expect(gate.wait(controller.signal)).rejects.toMatchObject({
      name: "AbortError",
    })
  })

  it("ignores a choice with nothing waiting", () => {
    const gate = owner_choice_gate<FirstMessagesChoice>()
    expect(() => gate.choose("continue")).not.toThrow()
    expect(gate.pending()).toBe(false)
  })
})

describe("first_messages", () => {
  it("labels each message by its plan row, in order", () => {
    expect(
      first_messages([
        { seed_prompt: "one", scenario_index: 0 },
        { seed_prompt: "three", scenario_index: 2 },
        { seed_prompt: "no row" },
      ]),
    ).toEqual([
      { key: "0:0", label: "Plan row 1", text: "one" },
      { key: "1:2", label: "Plan row 3", text: "three" },
      { key: "2:2", label: "Plan row 3", text: "no row" },
    ])
  })
})

describe("the pilot of 12", () => {
  it("spreads 12 positions over the plan, the same every time", () => {
    expect(PILOT_CASES).toBe(12)
    expect(pilot_positions(66)).toEqual([
      0, 5, 11, 16, 22, 27, 33, 38, 44, 49, 55, 60,
    ])
    expect(pilot_positions(66)).toEqual(pilot_positions(66))
    expect(pilot_positions(13)).toEqual([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11])
    // A plan no bigger than a pilot runs as one batch.
    expect(pilot_positions(12)).toEqual([])
    expect(pilot_positions(3)).toEqual([])
  })

  it("splits the written cases into a pilot and a rest, stamped with their plan rows", () => {
    const cases = Array.from({ length: 30 }, (_, i) => ({
      seed_prompt: `m${i}`,
      // One case lost its index upstream; its position is its row.
      scenario_index: i === 7 ? null : i,
    }))
    const split = split_pilot(cases)
    expect(split).not.toBeNull()
    expect(split!.pilot.map((c) => c.scenario_index)).toEqual([
      0, 2, 5, 7, 10, 12, 15, 17, 20, 22, 25, 27,
    ])
    expect(split!.pilot.length + split!.rest.length).toBe(30)
    const rows = [...split!.pilot, ...split!.rest]
      .map((c) => c.scenario_index)
      .sort((a, b) => (a ?? 0) - (b ?? 0))
    expect(rows).toEqual(Array.from({ length: 30 }, (_, i) => i))
    // The input is not changed.
    expect(cases[7].scenario_index).toBeNull()
    expect(split_pilot(cases.slice(0, 12))).toBeNull()
  })

  it("tops the pilot batch off with the rest, keeping the pilot's results", () => {
    const pilot = [{ id: "p0" }, { id: "p1" }]
    const rest = [{ id: "r0" }, { id: "r1" }, { id: "r2" }]
    const full = batch_after_pilot(pilot, rest)
    expect(full.map((c) => c.id)).toEqual(["p0", "p1", "r0", "r1", "r2"])
    const pilot_results = ["result p0", "result p1"]
    const widened = widen_pilot_batch({
      batch_items: pilot,
      built_slots: pilot_results,
      pilot_cases: pilot,
      full_items: full,
    })
    expect(widened).toEqual({
      batch_items: full,
      built_slots: ["result p0", "result p1", null, null, null],
    })
    // The existing drive plan then drives only the rest, into the same batch.
    const plan = plan_drive({
      items: full,
      batch_items: widened!.batch_items,
      built_slots: widened!.built_slots,
      batch_tag: "pilot_batch",
      undeleted_batch_tags: ["pilot_batch"],
    })
    expect(plan.top_off).toBe(true)
    expect(plan.items.map((c) => c.id)).toEqual(["r0", "r1", "r2"])
    expect(plan.slot_of_stream_index).toEqual([2, 3, 4])
    expect(plan.batch_tag).toBe("pilot_batch")
    expect(plan.replace_batch_tags).toEqual([])
  })

  it("does not widen a batch that is not the pilot", () => {
    const pilot = [{ id: "p0" }]
    const full = [{ id: "p0" }, { id: "r0" }]
    expect(
      widen_pilot_batch({
        batch_items: [{ id: "other" }],
        built_slots: ["x"],
        pilot_cases: pilot,
        full_items: full,
      }),
    ).toBeNull()
    expect(
      widen_pilot_batch({
        batch_items: null,
        built_slots: [],
        pilot_cases: pilot,
        full_items: full,
      }),
    ).toBeNull()
    expect(
      widen_pilot_batch({
        batch_items: pilot,
        built_slots: ["x"],
        pilot_cases: pilot,
        full_items: [{ id: "r0" }, { id: "p0" }],
      }),
    ).toBeNull()
  })
})

describe("pilot_next_step: the pilot is never paid for twice", () => {
  const pilot = [{ id: "p0" }, { id: "p1" }, { id: "p2" }]
  const rest = [{ id: "r0" }, { id: "r1" }]
  const state = { key: "k", pilot_cases: pilot }

  it("is none without a pilot under this key, so the build runs as before", () => {
    const args = { key: "k", batch_items: pilot, built_slots: ["a", "b", "c"] }
    expect(pilot_next_step({ ...args, pilot_state: null })).toBe("none")
    expect(
      pilot_next_step({ ...args, pilot_state: { ...state, key: "other" } }),
    ).toBe("none")
  })

  it("runs the rest on any way in, when every pilot slot is built", () => {
    // Path: the rest's grounding failed, the owner pressed Retry (or went
    // Back and pressed Generate). The pilot state is still there.
    const built = ["result p0", "result p1", "result p2"]
    expect(
      pilot_next_step({
        pilot_state: state,
        key: "k",
        batch_items: pilot,
        built_slots: built,
      }),
    ).toBe("rest")
    // The rest drive then tops the pilot off: only the rest is driven.
    const full = batch_after_pilot(pilot, rest)
    const widened = widen_pilot_batch({
      batch_items: pilot,
      built_slots: built,
      pilot_cases: pilot,
      full_items: full,
    })!
    const plan = plan_drive({
      items: full,
      batch_items: widened.batch_items,
      built_slots: widened.built_slots,
      batch_tag: "pilot_batch",
      undeleted_batch_tags: ["pilot_batch"],
    })
    expect(plan.top_off).toBe(true)
    expect(plan.items.map((c) => c.id)).toEqual(["r0", "r1"])
    expect(plan.items.some((c) => c.id.startsWith("p"))).toBe(false)
  })

  it("retries only the missing pilot slots when the pilot drive stopped short", () => {
    const built = ["result p0", null, "result p2"]
    expect(
      pilot_next_step({
        pilot_state: state,
        key: "k",
        batch_items: pilot,
        built_slots: built,
      }),
    ).toBe("retry")
    // A retry drives the same pilot cases: the existing top-off drives the
    // missing slot only, so the built ones are not paid again.
    const plan = plan_drive({
      items: pilot,
      batch_items: pilot,
      built_slots: built,
      batch_tag: "pilot_batch",
      undeleted_batch_tags: ["pilot_batch"],
    })
    expect(plan.top_off).toBe(true)
    expect(plan.items.map((c) => c.id)).toEqual(["p1"])
  })

  it("retries when another batch is on screen under the same key", () => {
    expect(
      pilot_next_step({
        pilot_state: state,
        key: "k",
        batch_items: null,
        built_slots: [],
      }),
    ).toBe("retry")
  })

  it("says why the pilot cannot be saved", () => {
    expect(pilot_save_blocked_text(54)).toBe(
      "Only the pilot ran. Continue to run the other 54 first.",
    )
  })
})
