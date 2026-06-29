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
  // Real-shaped passthrough: the table calls this for every row.
  eval_job_properties: (job: JobRecord) =>
    job.type === "eval" && job.properties ? job.properties : null,
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

  it("offers a Clear action (not a Delete label) for terminal rows", async () => {
    jobs.set([makeJob({ id: "succeeded", status: "succeeded" })])
    const { getByLabelText, getByText, queryByText } = render(JobsTable)
    await fireEvent.click(getByLabelText("More options"))
    expect(getByText("Clear")).not.toBeNull()
    expect(queryByText("Delete")).toBeNull()
  })

  it("gates row actions on status: running with pause shows Pause + Cancel", async () => {
    jobs.set([
      makeJob({ id: "running", status: "running", supports_pause: true }),
    ])
    const { getByLabelText, getByText, queryByText } = render(JobsTable)
    await fireEvent.click(getByLabelText("More options"))
    expect(getByText("Pause")).not.toBeNull()
    expect(getByText("Cancel")).not.toBeNull()
    expect(queryByText("Clear")).toBeNull()
  })

  it("gates row actions on status: paused shows Resume + Cancel", async () => {
    jobs.set([makeJob({ id: "paused", status: "paused" })])
    const { getByLabelText, getByText } = render(JobsTable)
    await fireEvent.click(getByLabelText("More options"))
    expect(getByText("Resume")).not.toBeNull()
    expect(getByText("Cancel")).not.toBeNull()
  })

  it("gates row actions on status: pending shows only Cancel", async () => {
    jobs.set([makeJob({ id: "pending", status: "pending" })])
    const { getByLabelText, getByText, queryByText } = render(JobsTable)
    await fireEvent.click(getByLabelText("More options"))
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

  it("renders eval job properties inline in the Details cell", () => {
    jobs.set([
      makeJob({
        id: "j_eval",
        type: "eval",
        properties: {
          eval_name: "Toxicity check",
          run_config_name: "GLM run",
          run_config_model_name: "gpt-4o",
          run_config_model_provider: "openai",
          run_config_prompt_name: "Few-Shot",
          run_config_tools_count: 0,
          run_config_skills_count: 0,
          judge_name: "G-Eval judge",
          judge_algorithm: "g_eval",
          judge_model_name: "claude",
          judge_model_provider: "anthropic",
        },
      }),
    ])
    const { getByText } = render(JobsTable)
    // Eval name is the header; run-config summary lines follow, with g_eval
    // mapped to its UI name.
    expect(getByText(/Eval: Toxicity check/)).not.toBeNull()
    expect(getByText(/Run config: GLM run/)).not.toBeNull()
    expect(getByText(/Prompt: Few-Shot/)).not.toBeNull()
    expect(getByText(/Tools: None/)).not.toBeNull()
    expect(getByText(/Skills: None/)).not.toBeNull()
    expect(getByText(/Judge: G-Eval/)).not.toBeNull()
  })

  it("renders no eval properties for non-eval jobs", () => {
    jobs.set([makeJob({ id: "j_noop", type: "noop" })])
    const { queryByText } = render(JobsTable)
    expect(queryByText(/Run config:/)).toBeNull()
  })
})
