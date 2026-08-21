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
  judge_feedback_batch_job_properties: (job: JobRecord) =>
    job.type === "judge_feedback_batch" && job.properties
      ? job.properties
      : null,
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

    await fireEvent.click(getByText("Clear Completed"))

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

    await fireEvent.click(getByText("Clear Completed"))

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
    expect(queryByText("This project has no tracked jobs")).toBeNull()
    expect(container.querySelector("table")).toBeNull()
  })

  it("shows the empty state when there are no jobs", () => {
    jobs.set([])
    const { getByText } = render(JobsTable)
    expect(getByText("This project has no tracked jobs")).not.toBeNull()
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
          run_config_tools_count: 2,
          run_config_skills_count: 1,
          judge_name: "Magical Yeti",
          judge_algorithm: "g_eval",
          judge_model_name: "claude",
          judge_model_provider: "anthropic",
        },
      }),
    ])
    const { getByText } = render(JobsTable)
    // Eval name is the header; run-config summary lines follow.
    expect(getByText(/Eval: Toxicity check/)).not.toBeNull()
    expect(getByText(/Run config: GLM run/)).not.toBeNull()
    // Model line flows through the model-name helper (unknown id -> "Model ID:").
    expect(getByText(/Model:/)).not.toBeNull()
    expect(getByText(/Prompt: Few-Shot/)).not.toBeNull()
    // Non-zero counts render the "N available" branch.
    expect(getByText(/Tools: 2 available/)).not.toBeNull()
    expect(getByText(/Skills: 1 available/)).not.toBeNull()
    // The judge line shows the judge (eval-config) name plus its algorithm.
    expect(getByText(/Judge: Magical Yeti \(G-Eval\)/)).not.toBeNull()
    expect(getByText(/Judge model:/)).not.toBeNull()
  })

  it("renders no eval properties for non-eval jobs", () => {
    jobs.set([makeJob({ id: "j_noop", type: "noop" })])
    const { queryByText } = render(JobsTable)
    expect(queryByText(/Run config:/)).toBeNull()
  })

  it("renders judge feedback batch job properties inline", () => {
    jobs.set([
      makeJob({
        id: "j_judge",
        type: "judge_feedback_batch",
        properties: {
          batch_name: "Nightly gate",
          eval_name: "Toxicity check",
          judge_name: "Magical Yeti",
          judge_algorithm: "g_eval",
          judge_model_name: "claude",
          judge_model_provider: "anthropic",
          generate_outputs: true,
          run_config_name: "Candidate run",
          run_config_model_name: "gpt-4o",
          run_config_model_provider: "openai",
          target_tags: ["val_set"],
          max_samples: 25,
          stop_after_failures: null,
        },
      }),
    ])
    const { getByText } = render(JobsTable)
    expect(getByText(/Nightly gate/)).not.toBeNull()
    expect(getByText(/Eval: Toxicity check/)).not.toBeNull()
    expect(getByText(/Judge: Magical Yeti \(G-Eval\)/)).not.toBeNull()
    // generate_outputs=true -> "Generate & judge" mode + candidate run config.
    expect(getByText(/Mode: Generate & judge/)).not.toBeNull()
    expect(getByText(/Run config: Candidate run/)).not.toBeNull()
    expect(getByText(/Tags: val_set/)).not.toBeNull()
    expect(getByText(/Max samples: 25/)).not.toBeNull()
  })
})
