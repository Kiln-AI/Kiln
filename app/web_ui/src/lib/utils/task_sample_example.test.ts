import { describe, it, expect, vi, beforeEach } from "vitest"
import type { RunSummary, TaskRun } from "$lib/types"

const { mock_get } = vi.hoisted(() => ({ mock_get: vi.fn() }))
vi.mock("$lib/api_client", () => ({ client: { GET: mock_get } }))

import {
  TASK_SAMPLE_CANDIDATE_LIMIT,
  fetch_task_sample_candidates,
  is_five_star_rating,
} from "./task_sample_example"

const RUNS_PATH = "/api/projects/{project_id}/tasks/{task_id}/runs"
const SUMMARIES_PATH =
  "/api/projects/{project_id}/tasks/{task_id}/runs_summaries"

function make_run(
  id: string,
  created_at: string,
  five_star_value: number | null = null,
): TaskRun {
  return {
    id,
    created_at,
    input: `input ${id}`,
    output: {
      output: `output ${id}`,
      rating:
        five_star_value === null
          ? null
          : { type: "five_star", value: five_star_value },
    },
  } as TaskRun
}

function make_summary(
  id: string,
  created_at: string,
  input_source: string,
): RunSummary {
  return { id, created_at, input_source } as RunSummary
}

function day(n: number): string {
  return new Date(Date.UTC(2026, 0, 1) + n * 86_400_000).toISOString()
}

function respond_with(runs: TaskRun[], summaries: RunSummary[] = []): void {
  mock_get.mockImplementation(async (path: string) => ({
    data: path === SUMMARIES_PATH ? summaries : runs,
    error: undefined,
  }))
}

function requested_run_ids(): string[] | undefined {
  const runs_call = mock_get.mock.calls.find(([path]) => path === RUNS_PATH)
  return runs_call?.[1].params.query.run_ids
}

const not_synthetic = (run: RunSummary) => run.input_source !== "synthetic"

describe("fetch_task_sample_candidates", () => {
  beforeEach(() => {
    mock_get.mockReset()
  })

  it("requests only the task's newest runs", async () => {
    respond_with([])

    await fetch_task_sample_candidates("p1", "t1")

    expect(TASK_SAMPLE_CANDIDATE_LIMIT).toBe(100)
    expect(mock_get).toHaveBeenCalledTimes(1)
    expect(mock_get).toHaveBeenCalledWith(RUNS_PATH, {
      params: {
        path: { project_id: "p1", task_id: "t1" },
        query: { limit: 100 },
      },
    })
  })

  it("auto-selects the most recent five-star run", async () => {
    respond_with([
      make_run("old_five_star", day(1), 5),
      make_run("newest", day(4), 3),
      make_run("new_five_star", day(3), 5),
    ])

    const result = await fetch_task_sample_candidates("p1", "t1")

    expect(result.auto_select_type).toBe("highly_rated")
    expect(result.selected_example).toEqual({
      input: "input new_five_star",
      output: "output new_five_star",
    })
    expect(result.available_runs.map((run) => run.id)).toEqual([
      "newest",
      "new_five_star",
      "old_five_star",
    ])
  })

  it("auto-selects the most recent run when none is five-star", async () => {
    respond_with([make_run("older", day(1), 4), make_run("newest", day(2))])

    const result = await fetch_task_sample_candidates("p1", "t1")

    expect(result.auto_select_type).toBe("most_recent")
    expect(result.selected_example?.input).toBe("input newest")
  })

  it("asks for manual entry when there are no runs", async () => {
    respond_with([])

    expect(await fetch_task_sample_candidates("p1", "t1")).toEqual({
      auto_select_type: null,
      selected_example: null,
      available_runs: [],
    })
  })

  it("finds older matching runs when every recent run is filtered out", async () => {
    const synthetic = Array.from({ length: 150 }, (_, i) =>
      make_summary(`synthetic_${i}`, day(10 + i), "synthetic"),
    )
    respond_with(
      [make_run("human_new", day(2)), make_run("human_old", day(1))],
      [
        ...synthetic,
        make_summary("human_old", day(1), "human"),
        make_summary("human_new", day(2), "human"),
      ],
    )

    const result = await fetch_task_sample_candidates("p1", "t1", not_synthetic)

    expect(requested_run_ids()).toEqual(["human_new", "human_old"])
    expect(result.auto_select_type).toBe("most_recent")
    expect(result.available_runs.map((run) => run.id)).toEqual([
      "human_new",
      "human_old",
    ])
  })

  it("requests the newest matching runs, up to the limit", async () => {
    const summaries = Array.from({ length: 120 }, (_, i) =>
      make_summary(`human_${i}`, day(i), "human"),
    )
    respond_with([], summaries)

    await fetch_task_sample_candidates("p1", "t1", not_synthetic)

    const expected = Array.from({ length: 100 }, (_, i) => `human_${119 - i}`)
    expect(requested_run_ids()).toEqual(expected)
  })

  it("asks for manual entry without fetching runs when the filter keeps none", async () => {
    respond_with(
      [make_run("only", day(1), 5)],
      [make_summary("only", day(1), "synthetic")],
    )

    const result = await fetch_task_sample_candidates("p1", "t1", not_synthetic)

    expect(result.auto_select_type).toBeNull()
    expect(result.available_runs).toEqual([])
    expect(mock_get).toHaveBeenCalledTimes(1)
    expect(mock_get).toHaveBeenCalledWith(SUMMARIES_PATH, {
      params: { path: { project_id: "p1", task_id: "t1" } },
    })
  })

  it.each([RUNS_PATH, SUMMARIES_PATH])(
    "throws the error message of a failed %s request",
    async (failing_path) => {
      mock_get.mockImplementation(async (path: string) =>
        path === failing_path
          ? { data: undefined, error: { message: "Task not found" } }
          : { data: [make_summary("run", day(1), "human")], error: undefined },
      )

      await expect(
        fetch_task_sample_candidates("p1", "t1", not_synthetic),
      ).rejects.toThrow("Task not found")
    },
  )
})

describe("is_five_star_rating", () => {
  it.each([
    [{ type: "five_star", value: 5 }, true],
    [{ type: "five_star", value: 4 }, false],
    [{ type: "pass_fail", value: 1 }, false],
    [null, false],
    [undefined, false],
  ] as const)("%o is five-star: %s", (rating, expected) => {
    expect(is_five_star_rating(rating)).toBe(expected)
  })
})
