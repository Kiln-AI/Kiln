import { describe, it, expect } from "vitest"
import { select_default_test_run } from "./test_run_selection"
import type { TaskRunOutput } from "$lib/types"

function run(id: string, trace?: TaskRunOutput["trace"]): TaskRunOutput {
  return {
    v: 1,
    id,
    input: `input ${id}`,
    output: { output: `output ${id}`, source: { type: "human" } },
    tags: [],
    created_at: new Date().toISOString(),
    trace,
  } as unknown as TaskRunOutput
}

const trace = [{ role: "user", content: "hi" }] as TaskRunOutput["trace"]

describe("select_default_test_run", () => {
  it("prefers a run with a trace over earlier traceless runs", () => {
    const traced = run("r3", trace)
    expect(select_default_test_run([run("r1"), run("r2"), traced])).toBe(traced)
  })

  it("picks the first run with a trace, keeping the newest-first order", () => {
    const newer = run("r1", trace)
    const older = run("r2", trace)
    expect(select_default_test_run([newer, older])).toBe(newer)
  })

  it("falls back to the first run when none have a trace", () => {
    const first = run("r1")
    expect(select_default_test_run([first, run("r2")])).toBe(first)
  })

  it("treats an empty trace as no trace", () => {
    const empty_trace = run("r1", [])
    const traced = run("r2", trace)
    expect(select_default_test_run([empty_trace, traced])).toBe(traced)
    expect(select_default_test_run([empty_trace])).toBe(empty_trace)
  })

  it("treats a null trace as no trace", () => {
    const null_trace = run("r1", null)
    const traced = run("r2", trace)
    expect(select_default_test_run([null_trace, traced])).toBe(traced)
  })

  it("returns null for an empty list", () => {
    expect(select_default_test_run([])).toBeNull()
  })
})
