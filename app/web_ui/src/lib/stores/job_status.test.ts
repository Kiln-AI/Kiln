import { describe, it, expect } from "vitest"
import {
  available_actions,
  completed_jobs,
  is_active,
  is_terminal,
  job_status_badge_class,
  job_status_display,
  jobs_indicator,
  progress_label,
  progress_percent,
} from "./job_status"
import type { BackgroundJobStatus, JobRecord } from "./jobs_api"

function makeJob(overrides: Partial<JobRecord> = {}): JobRecord {
  return {
    id: "j_1",
    type: "noop",
    status: "running",
    supports_pause: false,
    ...overrides,
  }
}

describe("is_active / is_terminal", () => {
  it("treats pending, running, paused as active", () => {
    expect(is_active("pending")).toBe(true)
    expect(is_active("running")).toBe(true)
    expect(is_active("paused")).toBe(true)
  })

  it("treats terminal statuses as not active", () => {
    expect(is_active("succeeded")).toBe(false)
    expect(is_active("failed")).toBe(false)
    expect(is_active("cancelled")).toBe(false)
  })

  it("identifies terminal statuses", () => {
    expect(is_terminal("succeeded")).toBe(true)
    expect(is_terminal("failed")).toBe(true)
    expect(is_terminal("cancelled")).toBe(true)
    expect(is_terminal("running")).toBe(false)
  })
})

describe("available_actions", () => {
  it("running without pause support: cancel only", () => {
    expect(available_actions(makeJob({ status: "running" }))).toEqual([
      "cancel",
    ])
  })

  it("running with pause support: pause then cancel", () => {
    expect(
      available_actions(makeJob({ status: "running", supports_pause: true })),
    ).toEqual(["pause", "cancel"])
  })

  it("paused: resume and cancel", () => {
    expect(
      available_actions(makeJob({ status: "paused", supports_pause: true })),
    ).toEqual(["resume", "cancel"])
  })

  it("pending: cancel only", () => {
    expect(available_actions(makeJob({ status: "pending" }))).toEqual([
      "cancel",
    ])
  })

  it("terminal states: delete only", () => {
    for (const status of [
      "succeeded",
      "failed",
      "cancelled",
    ] as BackgroundJobStatus[]) {
      expect(available_actions(makeJob({ status }))).toEqual(["delete"])
    }
  })
})

describe("job_status_display / job_status_badge_class", () => {
  const cases: [BackgroundJobStatus, string, string][] = [
    ["pending", "Pending", "badge-ghost"],
    ["running", "Running", "badge-info"],
    ["paused", "Paused", "badge-warning"],
    ["succeeded", "Succeeded", "badge-success"],
    ["failed", "Failed", "badge-error"],
    ["cancelled", "Cancelled", "badge-ghost"],
  ]
  it.each(cases)("maps %s", (status, label, badge) => {
    expect(job_status_display(status)).toBe(label)
    expect(job_status_badge_class(status)).toBe(badge)
  })
})

describe("progress_label", () => {
  it("shows count only when total is null", () => {
    expect(progress_label({ success: 3, error: 0 })).toBe("3")
  })

  it("shows success / total", () => {
    expect(progress_label({ success: 3, error: 0, total: 10 })).toBe("3 / 10")
  })

  it("appends errored count when present", () => {
    expect(progress_label({ success: 3, error: 2, total: 10 })).toBe(
      "3 / 10 (2 errored)",
    )
  })

  it("handles undefined progress", () => {
    expect(progress_label(undefined)).toBe("0")
  })
})

describe("progress_percent", () => {
  it("returns 0 when total is null or zero", () => {
    expect(progress_percent({ success: 1, error: 0 })).toBe(0)
    expect(progress_percent({ success: 1, error: 0, total: 0 })).toBe(0)
  })

  it("computes processed / total as a percent", () => {
    expect(progress_percent({ success: 2, error: 1, total: 10 })).toBe(30)
  })

  it("returns 100 when complete", () => {
    expect(progress_percent({ success: 8, error: 2, total: 10 })).toBe(100)
  })
})

describe("completed_jobs", () => {
  it("returns exactly the terminal jobs", () => {
    const jobs = [
      makeJob({ id: "a", status: "running" }),
      makeJob({ id: "b", status: "succeeded" }),
      makeJob({ id: "c", status: "pending" }),
      makeJob({ id: "d", status: "failed" }),
      makeJob({ id: "e", status: "paused" }),
      makeJob({ id: "f", status: "cancelled" }),
    ]
    expect(completed_jobs(jobs).map((j) => j.id)).toEqual(["b", "d", "f"])
  })

  it("returns an empty array when nothing is terminal", () => {
    expect(completed_jobs([makeJob({ status: "running" })])).toEqual([])
  })
})

describe("jobs_indicator", () => {
  it("shows a spinner with the active count when at least one job is running", () => {
    // 1 running, 3 active total (running + paused + pending), 5 jobs total.
    expect(jobs_indicator(1, 3, 5)).toEqual({ kind: "spinner", count: 3 })
  })

  it("stays static when only paused/pending jobs exist (no running)", () => {
    // 0 running, 2 active (paused), 2 total — must NOT spin.
    expect(jobs_indicator(0, 2, 2)).toEqual({ kind: "static", count: 2 })
  })

  it("shows a static total count when none active but jobs remain", () => {
    expect(jobs_indicator(0, 0, 3)).toEqual({ kind: "static", count: 3 })
  })

  it("is hidden when there are no jobs at all", () => {
    expect(jobs_indicator(0, 0, 0)).toEqual({ kind: "hidden" })
  })
})
