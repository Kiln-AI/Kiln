import { describe, it, expect, vi, beforeEach } from "vitest"
import { client } from "$lib/api_client"
import {
  cancel_job,
  create_job,
  delete_job,
  eval_job_properties,
  get_job,
  get_job_errors,
  get_job_result,
  list_jobs,
  pause_job,
  resume_job,
  type JobRecord,
} from "./jobs_api"

vi.mock("$lib/api_client", () => ({
  client: {
    GET: vi.fn(),
    POST: vi.fn(),
    DELETE: vi.fn(),
  },
  base_url: "http://localhost:8757",
}))

const mockGET = client.GET as unknown as ReturnType<typeof vi.fn>
const mockPOST = client.POST as unknown as ReturnType<typeof vi.fn>
const mockDELETE = client.DELETE as unknown as ReturnType<typeof vi.fn>

describe("jobs_api", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("list_jobs calls GET /api/jobs with the query and returns data", async () => {
    mockGET.mockResolvedValue({ data: [{ id: "j_1" }], error: undefined })
    const result = await list_jobs({ project_id: "p_1", status: "running" })
    expect(mockGET).toHaveBeenCalledWith("/api/jobs", {
      params: { query: { project_id: "p_1", status: "running" } },
    })
    expect(result).toEqual([{ id: "j_1" }])
  })

  it("list_jobs throws when the client returns an error", async () => {
    mockGET.mockResolvedValue({ data: undefined, error: { detail: "boom" } })
    await expect(list_jobs()).rejects.toEqual({ detail: "boom" })
  })

  it("get_job calls GET /api/jobs/{id}", async () => {
    mockGET.mockResolvedValue({ data: { id: "j_2" }, error: undefined })
    const result = await get_job("j_2")
    expect(mockGET).toHaveBeenCalledWith("/api/jobs/{id}", {
      params: { path: { id: "j_2" } },
    })
    expect(result).toEqual({ id: "j_2" })
  })

  it("create_job calls POST /api/jobs/{type} with params and metadata", async () => {
    mockPOST.mockResolvedValue({
      data: { job_id: "j_3", status: "pending" },
      error: undefined,
    })
    const result = await create_job("eval", { eval_id: "e_1" }, { src: "ui" })
    expect(mockPOST).toHaveBeenCalledWith("/api/jobs/{type}", {
      params: { path: { type: "eval" } },
      body: {
        params: { eval_id: "e_1" },
        metadata: { src: "ui" },
        project_id: null,
      },
    })
    expect(result).toEqual({ job_id: "j_3", status: "pending" })
  })

  it("create_job passes an explicit project_id in the body", async () => {
    mockPOST.mockResolvedValue({
      data: { job_id: "j_3b", status: "pending" },
      error: undefined,
    })
    await create_job("noop", { steps: 5 }, null, "p_current")
    expect(mockPOST).toHaveBeenCalledWith("/api/jobs/{type}", {
      params: { path: { type: "noop" } },
      body: { params: { steps: 5 }, metadata: null, project_id: "p_current" },
    })
  })

  it("get_job_result calls GET /api/jobs/{id}/result", async () => {
    mockGET.mockResolvedValue({ data: { total: 5 }, error: undefined })
    const result = await get_job_result("j_4")
    expect(mockGET).toHaveBeenCalledWith("/api/jobs/{id}/result", {
      params: { path: { id: "j_4" } },
    })
    expect(result).toEqual({ total: 5 })
  })

  it("get_job_errors calls GET /api/jobs/{id}/errors with optional run_id", async () => {
    mockGET.mockResolvedValue({
      data: [{ error_message: "oops" }],
      error: undefined,
    })
    const result = await get_job_errors("j_5", "run_xyz")
    expect(mockGET).toHaveBeenCalledWith("/api/jobs/{id}/errors", {
      params: { path: { id: "j_5" }, query: { run_id: "run_xyz" } },
    })
    expect(result).toEqual([{ error_message: "oops" }])
  })

  it("get_job_errors omits run_id query when not provided", async () => {
    mockGET.mockResolvedValue({ data: [], error: undefined })
    await get_job_errors("j_6")
    expect(mockGET).toHaveBeenCalledWith("/api/jobs/{id}/errors", {
      params: { path: { id: "j_6" }, query: {} },
    })
  })

  it("pause_job calls POST /api/jobs/{id}/pause", async () => {
    mockPOST.mockResolvedValue({ data: undefined, error: undefined })
    await pause_job("j_7")
    expect(mockPOST).toHaveBeenCalledWith("/api/jobs/{id}/pause", {
      params: { path: { id: "j_7" } },
    })
  })

  it("resume_job calls POST /api/jobs/{id}/resume", async () => {
    mockPOST.mockResolvedValue({ data: undefined, error: undefined })
    await resume_job("j_8")
    expect(mockPOST).toHaveBeenCalledWith("/api/jobs/{id}/resume", {
      params: { path: { id: "j_8" } },
    })
  })

  it("cancel_job calls POST /api/jobs/{id}/cancel", async () => {
    mockPOST.mockResolvedValue({ data: undefined, error: undefined })
    await cancel_job("j_9")
    expect(mockPOST).toHaveBeenCalledWith("/api/jobs/{id}/cancel", {
      params: { path: { id: "j_9" } },
    })
  })

  it("delete_job calls DELETE /api/jobs/{id}", async () => {
    mockDELETE.mockResolvedValue({ data: undefined, error: undefined })
    await delete_job("j_10")
    expect(mockDELETE).toHaveBeenCalledWith("/api/jobs/{id}", {
      params: { path: { id: "j_10" } },
    })
  })

  it("lifecycle calls throw on client error", async () => {
    mockPOST.mockResolvedValue({ data: undefined, error: { detail: "409" } })
    await expect(cancel_job("j_11")).rejects.toEqual({ detail: "409" })
  })

  describe("eval_job_properties", () => {
    const base: JobRecord = {
      id: "j_1",
      type: "eval",
      status: "running",
      supports_pause: true,
      created_at: "2024-01-01T00:00:00Z",
    } as JobRecord

    it("casts properties for an eval job", () => {
      const props = {
        eval_name: "Toxicity check",
        run_config_name: "GPT-4o run",
        run_config_model_name: "gpt-4o",
        run_config_model_provider: "openai",
        run_config_prompt_name: "Few-Shot",
        run_config_tools_count: 0,
        run_config_skills_count: 0,
        judge_name: "G-Eval judge",
        judge_algorithm: "g_eval",
        judge_model_name: "claude",
        judge_model_provider: "anthropic",
      }
      expect(eval_job_properties({ ...base, properties: props })).toEqual(props)
    })

    it("returns null for a non-eval job", () => {
      expect(
        eval_job_properties({ ...base, type: "noop", properties: {} }),
      ).toBeNull()
    })

    it("returns null when properties are absent", () => {
      expect(eval_job_properties({ ...base, properties: null })).toBeNull()
    })
  })
})
