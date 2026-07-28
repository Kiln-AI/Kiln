import { describe, expect, it } from "vitest"
import {
  dominant_failure_message,
  drive_stop_banner,
  driven_data_confirm,
  is_claims_resolved,
  new_plan_confirm,
  resolved_selected_count,
  type DriveStop,
} from "./plan_flow"
import type { ClaimsBuildState } from "./claim_evidence"

describe("dominant_failure_message", () => {
  it("returns null for no messages", () => {
    expect(dominant_failure_message([])).toBeNull()
  })

  it("ignores blank messages", () => {
    expect(dominant_failure_message(["", "", ""])).toBeNull()
  })

  it("returns the most frequent message", () => {
    expect(
      dominant_failure_message([
        "RateLimitError",
        "NotFoundError: model x",
        "RateLimitError",
      ]),
    ).toBe("RateLimitError")
  })

  it("resolves ties to the first seen", () => {
    expect(dominant_failure_message(["a", "b"])).toBe("a")
  })
})

describe("drive_stop_banner", () => {
  const partial: DriveStop = {
    survivors: 38,
    failed: 2,
    dominant_error: "RateLimitError from OpenRouter",
  }

  it("partial failure: counts, dominant error, both recovery actions", () => {
    const msg = drive_stop_banner(partial, "Polite Hawk")
    expect(msg).toBe(
      "38 of 40 conversations completed — 2 failed after retries (most common: RateLimitError from OpenRouter). Continue with the 38 that completed, or drive the batch again.",
    )
  })

  it("partial failure without a dominant error omits the clause", () => {
    const msg = drive_stop_banner(
      { ...partial, dominant_error: null },
      "Polite Hawk",
    )
    expect(msg).toContain("2 failed after retries.")
    expect(msg).not.toContain("most common")
  })

  it("all-failed: error color content — dominant error, run config name, and the /run deeplink", () => {
    const msg = drive_stop_banner(
      {
        survivors: 0,
        failed: 40,
        dominant_error: "NotFoundError: model gpt_5_5 is unavailable",
      },
      "Polite Hawk",
    )
    expect(msg).toBe(
      "All conversations failed — NotFoundError: model gpt_5_5 is unavailable (run config: Polite Hawk). You can [test your run config](/run), then drive again.",
    )
  })

  it("all-failed without a run config name omits the clause", () => {
    const msg = drive_stop_banner(
      { survivors: 0, failed: 5, dominant_error: "boom" },
      null,
    )
    expect(msg).not.toContain("run config:")
    expect(msg).toContain("[test your run config](/run)")
  })

  it("abort with survivors: diagnosis with name+model, continue-or-test recovery", () => {
    const msg = drive_stop_banner(
      {
        survivors: 12,
        failed: 28,
        dominant_error: null,
        aborted_error: "AuthenticationError: invalid api key",
      },
      "Polite Hawk",
      "gpt_5_5",
    )
    expect(msg).toBe(
      "Drive aborted — AuthenticationError: invalid api key (run config: Polite Hawk, gpt_5_5). 12 conversations completed before the abort — continue with those, or [test your run config](/run) and drive again.",
    )
  })

  it("abort with no survivors: test-then-drive recovery only", () => {
    const msg = drive_stop_banner(
      {
        survivors: 0,
        failed: 40,
        dominant_error: null,
        aborted_error: "NotFoundError: model gpt_5_5 is deprecated",
      },
      "Polite Hawk",
      "gpt_5_5",
    )
    expect(msg).toBe(
      "Drive aborted — NotFoundError: model gpt_5_5 is deprecated (run config: Polite Hawk, gpt_5_5). You can [test your run config](/run), then drive again.",
    )
  })

  it("abort outranks the all-failed wording even at zero survivors", () => {
    const msg = drive_stop_banner(
      { survivors: 0, failed: 3, dominant_error: "x", aborted_error: "boom" },
      null,
    )
    expect(msg).toMatch(/^Drive aborted — boom\./)
  })
})

describe("driven_data_confirm", () => {
  it("has-data wording includes the review-progress clause", () => {
    expect(driven_data_confirm("A new plan", 38, true)).toBe(
      "You have 38 driven conversations and your review progress. A new plan will discard them. This cannot be undone.",
    )
  })

  it("stop-screen wording omits the review-progress clause", () => {
    expect(driven_data_confirm("Editing the plan", 38, false)).toBe(
      "You have 38 driven conversations. Editing the plan will discard them. This cannot be undone.",
    )
  })

  it("singular survivor", () => {
    expect(driven_data_confirm("A new plan", 1, false)).toContain(
      "1 driven conversation.",
    )
  })
})

describe("new_plan_confirm", () => {
  it("pristine plan uses SDG's exact formula", () => {
    expect(
      new_plan_confirm({
        has_driven_results: false,
        survivors: 0,
        include_review_progress: false,
        plan_edited: false,
      }),
    ).toBe(
      "Are you sure you want to discard the current batch plan? This cannot be undone.",
    )
  })

  it("edited plan uses SDG's removed-items variant", () => {
    expect(
      new_plan_confirm({
        has_driven_results: false,
        survivors: 0,
        include_review_progress: false,
        plan_edited: true,
      }),
    ).toBe(
      "Are you sure you want to discard the current batch plan, including the dataset items you removed? This cannot be undone.",
    )
  })

  it("driven results outrank the edited tier", () => {
    expect(
      new_plan_confirm({
        has_driven_results: true,
        survivors: 40,
        include_review_progress: true,
        plan_edited: true,
      }),
    ).toBe(
      "You have 40 driven conversations and your review progress. A new plan will discard them. This cannot be undone.",
    )
  })
})

describe("claims gate resolution", () => {
  it("built and error are resolved; unbuilt and building are not", () => {
    expect(is_claims_resolved("built")).toBe(true)
    expect(is_claims_resolved("error")).toBe(true)
    expect(is_claims_resolved("unbuilt")).toBe(false)
    expect(is_claims_resolved("building")).toBe(false)
  })

  const traces = (states: ClaimsBuildState[]) =>
    states.map((claims_state) => ({ claims_state }))

  it("counts only the selected traces", () => {
    const t = traces(["built", "unbuilt", "error", "building", "built"])
    expect(resolved_selected_count(t, [0, 2, 3])).toBe(2)
    expect(resolved_selected_count(t, [1, 3])).toBe(0)
    expect(resolved_selected_count(t, [0, 2, 4])).toBe(3)
  })

  it("out-of-range indices never count as resolved", () => {
    expect(resolved_selected_count(traces(["built"]), [0, 7])).toBe(1)
  })

  it("empty selection resolves to zero", () => {
    expect(resolved_selected_count(traces(["built"]), [])).toBe(0)
  })
})
