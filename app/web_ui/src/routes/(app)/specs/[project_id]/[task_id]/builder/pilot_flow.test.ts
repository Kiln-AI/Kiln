import { describe, expect, it } from "vitest"
import {
  first_messages,
  owner_choice_gate,
  write_review_ground,
  type FirstMessagesChoice,
} from "./pilot_flow"

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
