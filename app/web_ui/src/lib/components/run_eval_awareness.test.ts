import { describe, it, expect } from "vitest"
import type { JobRecord } from "$lib/stores/jobs_api"
import { match_ongoing_jobs, aggregate_progress } from "./run_eval_awareness"

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

describe("match_ongoing_jobs", () => {
  it("includes pending and running matches, excludes paused and terminals", () => {
    const all: JobRecord[] = [
      make_job({ id: "j_running", status: "running" }),
      make_job({ id: "j_pending", status: "pending" }),
      make_job({ id: "j_paused", status: "paused" }),
      make_job({ id: "j_succeeded", status: "succeeded" }),
      make_job({ id: "j_failed", status: "failed" }),
      make_job({ id: "j_cancelled", status: "cancelled" }),
    ]
    const result = match_ongoing_jobs(all, E, C, [R1], false)
    expect(result.map((j) => j.id).sort()).toEqual(["j_pending", "j_running"])
  })

  it("filters out untagged, non-eval, and mismatched-field tags", () => {
    const all: JobRecord[] = [
      // No tag at all — e.g. an older or untagged job.
      make_job({ id: "j_untagged", metadata: {} }),
      // Tagged for a different feature (kind != "eval").
      make_job({
        id: "j_rag",
        metadata: { tag: { kind: "rag", rag_config_id: "rcfg1" } },
      }),
      // Eval tag but wrong eval_id / eval_config_id / run_config_id.
      make_job({
        id: "j_wrong_eval",
        metadata: eval_tag_meta({ eval_id: "other" }),
      }),
      make_job({
        id: "j_wrong_config",
        metadata: eval_tag_meta({ eval_config_id: "other" }),
      }),
      make_job({
        id: "j_wrong_run",
        metadata: eval_tag_meta({ run_config_id: "other" }),
      }),
      // The match.
      make_job({ id: "j_match" }),
    ]
    const result = match_ongoing_jobs(all, E, C, [R1], false)
    expect(result.map((j) => j.id)).toEqual(["j_match"])
  })

  it("run_all skips the run_config filter (any matching eval/config counts)", () => {
    const all: JobRecord[] = [
      make_job({ id: "j_r1", metadata: eval_tag_meta({ run_config_id: R1 }) }),
      make_job({ id: "j_r2", metadata: eval_tag_meta({ run_config_id: R2 }) }),
      make_job({
        id: "j_other_config",
        metadata: eval_tag_meta({ eval_config_id: "other" }),
      }),
    ]
    const result = match_ongoing_jobs(all, E, C, [], true)
    expect(result.map((j) => j.id).sort()).toEqual(["j_r1", "j_r2"])
  })
})

describe("aggregate_progress", () => {
  it("sums success/total/error across jobs", () => {
    const jobs: JobRecord[] = [
      make_job({
        progress: { total: 50, success: 12, error: 1, updated_at: "x" },
      }),
      make_job({
        progress: { total: 30, success: 7, error: 2, updated_at: "x" },
      }),
    ]
    expect(aggregate_progress(jobs)).toEqual({
      progress: 19,
      total: 80,
      errors: 3,
    })
  })

  it("treats nullish/missing progress fields as zero", () => {
    const jobs: JobRecord[] = [
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      make_job({ progress: null as any }),
      make_job({
        progress: { total: 5, success: 2, error: 0, updated_at: "x" },
      }),
    ]
    expect(aggregate_progress(jobs)).toEqual({
      progress: 2,
      total: 5,
      errors: 0,
    })
  })

  it("returns zeros for empty input", () => {
    expect(aggregate_progress([])).toEqual({
      progress: 0,
      total: 0,
      errors: 0,
    })
  })
})
