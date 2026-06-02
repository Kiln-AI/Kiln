// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest"
import { render, fireEvent, waitFor, cleanup } from "@testing-library/svelte"
import { writable } from "svelte/store"
import type { JobRecord } from "$lib/stores/jobs_api"

// Live job list the table renders from. Replaced per-test.
const jobs = writable<JobRecord[]>([])
const synced = writable(true)
const connection = writable<"idle" | "connecting" | "open" | "errored">("open")

vi.mock("$lib/stores/jobs_store", () => ({
  jobs,
  synced,
  connection,
}))

const api = {
  pause_job: vi.fn().mockResolvedValue(undefined),
  resume_job: vi.fn().mockResolvedValue(undefined),
  cancel_job: vi.fn().mockResolvedValue(undefined),
  delete_job: vi.fn().mockResolvedValue(undefined),
  get_job_errors: vi.fn().mockResolvedValue([]),
  get_job_result: vi.fn().mockResolvedValue({}),
}
vi.mock("$lib/stores/jobs_api", () => api)

const JobsTable = (await import("./jobs_table.svelte")).default

function makeJob(overrides: Partial<JobRecord> = {}): JobRecord {
  return {
    id: "j_1",
    type: "noop",
    status: "running",
    supports_pause: false,
    created_at: "2024-01-01T00:00:00Z",
    ...overrides,
  }
}

describe("JobsTable", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    synced.set(true)
    connection.set("open")
    jobs.set([])
  })

  afterEach(() => {
    cleanup()
  })

  it("Clear completed deletes exactly the terminal jobs", async () => {
    jobs.set([
      makeJob({ id: "running", status: "running" }),
      makeJob({ id: "succeeded", status: "succeeded" }),
      makeJob({ id: "pending", status: "pending" }),
      makeJob({ id: "failed", status: "failed" }),
      makeJob({ id: "cancelled", status: "cancelled" }),
    ])
    const { getByText } = render(JobsTable)

    await fireEvent.click(getByText("Clear completed"))

    await waitFor(() => {
      expect(api.delete_job).toHaveBeenCalledTimes(3)
    })
    const deleted = api.delete_job.mock.calls.map((c) => c[0]).sort()
    expect(deleted).toEqual(["cancelled", "failed", "succeeded"])
    // It must not touch the active jobs.
    expect(deleted).not.toContain("running")
    expect(deleted).not.toContain("pending")
  })

  it("Clear completed surfaces an error when a delete fails", async () => {
    jobs.set([makeJob({ id: "failed", status: "failed" })])
    api.delete_job.mockRejectedValueOnce(new Error("boom"))
    const { getByText, getByRole } = render(JobsTable)

    await fireEvent.click(getByText("Clear completed"))

    await waitFor(() => {
      expect(getByRole("alert").textContent).toContain("boom")
    })
  })

  it("renders a Clear button (not a Delete label) for terminal rows", () => {
    jobs.set([makeJob({ id: "succeeded", status: "succeeded" })])
    const { getByText, queryByText } = render(JobsTable)
    expect(getByText("Clear")).not.toBeNull()
    expect(queryByText("Delete")).toBeNull()
  })

  it("gates row actions on status: running with pause shows Pause + Cancel", () => {
    jobs.set([
      makeJob({ id: "running", status: "running", supports_pause: true }),
    ])
    const { getByText, queryByText } = render(JobsTable)
    expect(getByText("Pause")).not.toBeNull()
    expect(getByText("Cancel")).not.toBeNull()
    expect(queryByText("Clear")).toBeNull()
  })

  it("gates row actions on status: paused shows Resume + Cancel", () => {
    jobs.set([makeJob({ id: "paused", status: "paused" })])
    const { getByText } = render(JobsTable)
    expect(getByText("Resume")).not.toBeNull()
    expect(getByText("Cancel")).not.toBeNull()
  })

  it("gates row actions on status: pending shows only Cancel", () => {
    jobs.set([makeJob({ id: "pending", status: "pending" })])
    const { getByText, queryByText } = render(JobsTable)
    expect(getByText("Cancel")).not.toBeNull()
    expect(queryByText("Pause")).toBeNull()
    expect(queryByText("Resume")).toBeNull()
    expect(queryByText("Clear")).toBeNull()
  })

  it("shows the loading spinner before the first sync", () => {
    synced.set(false)
    connection.set("connecting")
    const { container, queryByText } = render(JobsTable)
    expect(container.querySelector(".loading.loading-spinner")).not.toBeNull()
    // Neither the table nor the empty state should render while syncing.
    expect(queryByText("No jobs yet")).toBeNull()
    expect(container.querySelector("table")).toBeNull()
  })

  it("shows the empty state when there are no jobs", () => {
    jobs.set([])
    const { getByText } = render(JobsTable)
    expect(getByText("No jobs yet")).not.toBeNull()
  })

  it("shows the connection-error state when errored before first sync", () => {
    synced.set(false)
    connection.set("errored")
    const { getByText } = render(JobsTable)
    expect(getByText("Can't connect to the job stream")).not.toBeNull()
  })

  it("renders each secondary line on its own row when display.secondary is a list", () => {
    jobs.set([
      makeJob({
        id: "j_eval",
        type: "eval",
        metadata: {
          display: {
            primary: "Eval: My Eval",
            secondary: ["Judge: Judge-1", "Run config: RC-1"],
          },
        },
      }),
    ])
    const { getByText } = render(JobsTable)
    // Each line gets its own element rather than being collapsed into one.
    expect(getByText("Judge: Judge-1")).not.toBeNull()
    expect(getByText("Run config: RC-1")).not.toBeNull()
  })

  it("uses 'View Results' / 'View Errors' labels for the result/errors buttons", () => {
    jobs.set([
      makeJob({
        id: "succ",
        status: "succeeded",
        result: { foo: "bar" } as unknown as Record<string, unknown>,
        progress: {
          total: 10,
          success: 9,
          error: 1,
          updated_at: "2024-01-01",
        },
      }),
    ])
    const { getByText } = render(JobsTable)
    expect(getByText("View Results")).not.toBeNull()
    expect(getByText("View Errors")).not.toBeNull()
  })

  it("renders the Details primary text in red when the job has errored", () => {
    jobs.set([
      makeJob({
        id: "failed",
        status: "failed",
        metadata: { display: { primary: "Eval: Bad Run" } },
      }),
    ])
    const { getByText } = render(JobsTable)
    const primary = getByText("Eval: Bad Run")
    // Either the text node itself or an ancestor cell carries the error color.
    const cell = primary.closest(".text-error") || primary
    expect(cell.className).toContain("text-error")
  })

  it("still renders a string display.secondary as a single line (back-compat)", () => {
    jobs.set([
      makeJob({
        id: "j_legacy",
        type: "eval",
        metadata: {
          display: {
            primary: "Eval: Legacy",
            secondary: "Judge: X · Run config: Y",
          },
        },
      }),
    ])
    const { getByText } = render(JobsTable)
    expect(getByText("Judge: X · Run config: Y")).not.toBeNull()
  })
})
