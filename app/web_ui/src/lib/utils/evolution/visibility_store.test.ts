import { describe, it, expect, beforeEach } from "vitest"
import { get } from "svelte/store"
import {
  hidden_run_config_ids,
  reconcile_visibility,
  reset_visibility,
  toggle_run_config,
  visible_ids,
} from "./visibility_store"

describe("hidden_run_config_ids", () => {
  beforeEach(() => {
    reset_visibility()
  })

  it("starts empty, which is everything visible", () => {
    expect(get(hidden_run_config_ids).size).toBe(0)
    expect(visible_ids(["a", "b"], get(hidden_run_config_ids))).toEqual([
      "a",
      "b",
    ])
  })

  it("toggles one config off and back on", () => {
    toggle_run_config("a")
    expect([...get(hidden_run_config_ids)]).toEqual(["a"])
    toggle_run_config("a")
    expect(get(hidden_run_config_ids).size).toBe(0)
  })

  it("hides configs independently of each other", () => {
    toggle_run_config("a")
    toggle_run_config("c")
    expect(visible_ids(["a", "b", "c"], get(hidden_run_config_ids))).toEqual([
      "b",
    ])
  })

  it("publishes a new Set each time, so subscribers actually fire", () => {
    const seen: Set<string>[] = []
    const unsubscribe = hidden_run_config_ids.subscribe((value) =>
      seen.push(value),
    )
    toggle_run_config("a")
    toggle_run_config("b")
    unsubscribe()
    expect(seen.length).toBe(3)
    // Identity, not contents: a mutated Set would notify nobody
    expect(seen[0]).not.toBe(seen[1])
    expect(seen[1]).not.toBe(seen[2])
  })
})

describe("visible_ids", () => {
  it("keeps pinned order rather than the order things were hidden in", () => {
    expect(visible_ids(["c", "a", "b"], new Set(["a"]))).toEqual(["c", "b"])
  })

  it("returns nothing when everything is hidden", () => {
    expect(visible_ids(["a", "b"], new Set(["a", "b"]))).toEqual([])
  })

  it("ignores hidden ids that are not pinned", () => {
    expect(visible_ids(["a"], new Set(["z"]))).toEqual(["a"])
  })
})

describe("reconcile_visibility", () => {
  beforeEach(() => {
    reset_visibility()
  })

  it("drops ids that are no longer pinned, so unpin-then-repin comes back visible", () => {
    toggle_run_config("a")
    reconcile_visibility(["b", "c"])
    expect(get(hidden_run_config_ids).size).toBe(0)
    // Pinned again: visible, because nothing remembers it was ever off
    expect(visible_ids(["a", "b"], get(hidden_run_config_ids))).toEqual([
      "a",
      "b",
    ])
  })

  it("keeps ids that are still pinned", () => {
    toggle_run_config("a")
    toggle_run_config("b")
    reconcile_visibility(["a", "c"])
    expect([...get(hidden_run_config_ids)]).toEqual(["a"])
  })

  it("does not publish when there is nothing to drop", () => {
    toggle_run_config("a")
    let updates = 0
    const unsubscribe = hidden_run_config_ids.subscribe(() => updates++)
    reconcile_visibility(["a", "b"])
    reconcile_visibility(["a"])
    unsubscribe()
    // Only the subscribe-time call: a store write per redraw would churn every
    // chart that reads it
    expect(updates).toBe(1)
  })

  it("clears everything when nothing is pinned", () => {
    toggle_run_config("a")
    reconcile_visibility([])
    expect(get(hidden_run_config_ids).size).toBe(0)
  })
})
