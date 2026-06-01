import { describe, it, expect } from "vitest"
import type { JobRecord } from "$lib/stores/jobs_api"
import { filter_by_tag, ongoing, compute_run_state } from "./job_selectors"

const E = "e1"
const C = "c1"
const R1 = "rc1"
const R2 = "rc2"

function eval_tag_meta(
  over: Partial<{
    eval_id: string
    eval_config_id: string
    run_config_id: string
  }> = {},
): Record<string, unknown> {
  return {
    tag: {
      kind: "eval",
      eval_id: over.eval_id ?? E,
      eval_config_id: over.eval_config_id ?? C,
      run_config_id: over.run_config_id ?? R1,
    },
  }
}

function make_job(over: Partial<JobRecord>): JobRecord {
  return {
    id: "j_x",
    type: "eval",
    status: "running",
    progress: { total: 10, success: 0, error: 0, updated_at: "now" },
    params: {},
    result: null,
    error: null,
    metadata: eval_tag_meta(),
    project_id: "p1",
    supports_pause: true,
    created_at: "now",
    updated_at: "now",
    started_at: "now",
    ended_at: null,
    run_id: "r1",
    ...over,
  } as JobRecord
}

describe("filter_by_tag", () => {
  it("narrows to the given kind, ignoring untagged / wrong-kind records", () => {
    const all: JobRecord[] = [
      make_job({ id: "j_eval" }),
      make_job({ id: "j_untagged", metadata: {} }),
      make_job({
        id: "j_rag",
        metadata: { tag: { kind: "rag", rag_config_id: "rcfg" } },
      }),
    ]
    expect(filter_by_tag(all, "eval").map((j) => j.id)).toEqual(["j_eval"])
    expect(filter_by_tag(all, "rag").map((j) => j.id)).toEqual(["j_rag"])
  })

  it("applies the refine predicate against the narrowed tag and job", () => {
    const all: JobRecord[] = [
      make_job({ id: "j_match" }),
      make_job({
        id: "j_other_eval",
        metadata: eval_tag_meta({ eval_id: "other" }),
      }),
      make_job({
        id: "j_other_run",
        metadata: eval_tag_meta({ run_config_id: "other" }),
      }),
    ]
    const result = filter_by_tag(
      all,
      "eval",
      (t) => t.eval_id === E && t.run_config_id === R1,
    )
    expect(result.map((j) => j.id)).toEqual(["j_match"])
  })
})

describe("ongoing", () => {
  it("includes only pending and running — excludes paused and terminals", () => {
    const all: JobRecord[] = [
      make_job({ id: "j_running", status: "running" }),
      make_job({ id: "j_pending", status: "pending" }),
      make_job({ id: "j_paused", status: "paused" }),
      make_job({ id: "j_succeeded", status: "succeeded" }),
      make_job({ id: "j_failed", status: "failed" }),
      make_job({ id: "j_cancelled", status: "cancelled" }),
    ]
    expect(
      ongoing(all)
        .map((j) => j.id)
        .sort(),
    ).toEqual(["j_pending", "j_running"])
  })
})

describe("compute_run_state", () => {
  it("store_running trumps everything, including a stuck local 'running'", () => {
    expect(compute_run_state(true, false, "running")).toBe("running")
    expect(compute_run_state(true, false, "not_started")).toBe("running")
    expect(compute_run_state(true, false, "complete")).toBe("running")
  })

  it("initiating bridges the click-to-store-update window", () => {
    expect(compute_run_state(false, true, "running")).toBe("running")
    expect(compute_run_state(false, true, "not_started")).toBe("running")
  })

  it("paused store → local 'running' is overridden (the bug fix)", () => {
    // The user-facing scenario: a stuck local "running" while the store has
    // only paused matching jobs (no ongoing). Button should show "Run Eval".
    expect(compute_run_state(false, false, "running")).toBe("not_started")
  })

  it("local terminal states show when no store-ongoing and not initiating", () => {
    expect(compute_run_state(false, false, "complete")).toBe("complete")
    expect(compute_run_state(false, false, "complete_with_errors")).toBe(
      "complete_with_errors",
    )
  })

  it("default is 'not_started'", () => {
    expect(compute_run_state(false, false, "not_started")).toBe("not_started")
  })
})
