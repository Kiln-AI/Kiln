import { describe, it, expect, vi, beforeEach } from "vitest"
import {
  testV2Eval,
  testV2EvalLlmJudge,
  fetchTaskRuns,
  createEvalConfig,
  checkAddCodeTrust,
  addCodeTrust,
  type TestV2EvalRequest,
  type CreateEvalConfigRequest,
} from "./v2_eval_api"

const mockPost = vi.fn()
const mockGet = vi.fn()

vi.mock("$lib/api_client", () => ({
  client: {
    POST: (...args: unknown[]) => mockPost(...args),
    GET: (...args: unknown[]) => mockGet(...args),
  },
}))

beforeEach(() => {
  mockPost.mockReset()
  mockGet.mockReset()
})

describe("testV2Eval", () => {
  const request: TestV2EvalRequest = {
    properties: {
      type: "exact_match",
      case_sensitive: true,
      value_expression: null,
      expected_value: "hello",
      reference_key: null,
    },
    eval_input: {
      final_message: "hello",
    },
  }

  it("calls client.POST with correct path, params and body", async () => {
    const responseData = { scores: { accuracy: 1.0 } }
    mockPost.mockResolvedValue({ data: responseData, error: undefined })

    await testV2Eval("proj-1", "task-2", "eval-3", request)

    expect(mockPost).toHaveBeenCalledTimes(1)
    const [path, options] = mockPost.mock.calls[0]
    expect(path).toBe(
      "/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/test_v2_eval",
    )
    expect(options.params.path).toEqual({
      project_id: "proj-1",
      task_id: "task-2",
      eval_id: "eval-3",
    })
    expect(options.body).toEqual(request)
  })

  it("returns parsed response on success", async () => {
    const responseData = {
      scores: { accuracy: 1.0, relevance: 0.8 },
      skipped_reason: null,
    }
    mockPost.mockResolvedValue({ data: responseData, error: undefined })

    const result = await testV2Eval("p", "t", "e", request)
    expect(result.scores).toEqual({ accuracy: 1.0, relevance: 0.8 })
  })
})

describe("createEvalConfig", () => {
  const request: CreateEvalConfigRequest = {
    type: "v2",
    properties: { type: "exact_match", case_sensitive: true },
    model_name: null,
    provider: null,
  }

  it("calls client.POST with correct path, params and body", async () => {
    const responseData = { id: "cfg-1", config_type: "v2", properties: {} }
    mockPost.mockResolvedValue({ data: responseData, error: undefined })

    await createEvalConfig("proj-1", "task-2", "eval-3", request)

    expect(mockPost).toHaveBeenCalledTimes(1)
    const [path, options] = mockPost.mock.calls[0]
    expect(path).toBe(
      "/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/create_eval_config",
    )
    expect(options.params.path).toEqual({
      project_id: "proj-1",
      task_id: "task-2",
      eval_id: "eval-3",
    })
    expect(options.body).toEqual(request)
  })

  it("returns parsed EvalConfig on success", async () => {
    const responseData = {
      id: "cfg-1",
      config_type: "v2",
      name: "test config",
      properties: { type: "exact_match" },
      model_name: null,
      model_provider: null,
    }
    mockPost.mockResolvedValue({ data: responseData, error: undefined })

    const result = await createEvalConfig("p", "t", "e", request)
    expect(result.id).toBe("cfg-1")
    expect(result.config_type).toBe("v2")
  })

  it("sends optional model_name and provider when provided", async () => {
    const requestWithModel: CreateEvalConfigRequest = {
      type: "llm_as_judge",
      properties: { eval_steps: [], task_description: "test" },
      model_name: "gpt-4o",
      provider: "openai",
    }
    mockPost.mockResolvedValue({
      data: { id: "cfg-2", config_type: "llm_as_judge" },
      error: undefined,
    })

    await createEvalConfig("p", "t", "e", requestWithModel)

    const [, options] = mockPost.mock.calls[0]
    expect(options.body.model_name).toBe("gpt-4o")
    expect(options.body.provider).toBe("openai")
  })
})

describe("checkAddCodeTrust", () => {
  it("calls client.GET with correct path and params", async () => {
    mockGet.mockResolvedValue({
      data: { trusted: false },
      error: undefined,
    })

    await checkAddCodeTrust("proj-1")

    expect(mockGet).toHaveBeenCalledTimes(1)
    const [path, options] = mockGet.mock.calls[0]
    expect(path).toBe("/api/projects/{project_id}/add_code_trust")
    expect(options.params.path).toEqual({ project_id: "proj-1" })
  })

  it("returns parsed trust response", async () => {
    mockGet.mockResolvedValue({
      data: { trusted: true },
      error: undefined,
    })

    const result = await checkAddCodeTrust("proj-1")
    expect(result.trusted).toBe(true)
  })
})

describe("addCodeTrust", () => {
  it("calls client.POST with correct path and params", async () => {
    mockPost.mockResolvedValue({
      data: { trusted: true },
      error: undefined,
    })

    await addCodeTrust("proj-1")

    expect(mockPost).toHaveBeenCalledTimes(1)
    const [path, options] = mockPost.mock.calls[0]
    expect(path).toBe("/api/projects/{project_id}/add_code_trust")
    expect(options.params.path).toEqual({ project_id: "proj-1" })
  })

  it("returns parsed grant response", async () => {
    mockPost.mockResolvedValue({
      data: { trusted: true },
      error: undefined,
    })

    const result = await addCodeTrust("proj-1")
    expect(result.trusted).toBe(true)
  })
})

describe("testV2EvalLlmJudge", () => {
  it("sends llm_judge_builder_input and eval_input to testV2Eval", async () => {
    const responseData = { scores: { accuracy: 1.0 }, skipped_reason: null }
    mockPost.mockResolvedValue({ data: responseData, error: undefined })

    const builderInput = {
      model_name: "gpt-4o",
      provider: "openai" as const,
      g_eval: false,
    }
    const evalInput = { final_message: "test output" }

    const result = await testV2EvalLlmJudge(
      "proj-1",
      "task-2",
      "eval-3",
      builderInput,
      evalInput,
    )

    expect(mockPost).toHaveBeenCalledTimes(1)
    const [path, options] = mockPost.mock.calls[0]
    expect(path).toBe(
      "/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/test_v2_eval",
    )
    expect(options.body).toEqual({
      eval_input: evalInput,
      llm_judge_builder_input: builderInput,
    })
    expect(result.scores).toEqual({ accuracy: 1.0 })
  })

  it("forwards abort signal", async () => {
    mockPost.mockResolvedValue({
      data: { scores: {}, skipped_reason: null },
      error: undefined,
    })

    const controller = new AbortController()
    await testV2EvalLlmJudge(
      "p",
      "t",
      "e",
      { model_name: "m", provider: "openai" as const, g_eval: false },
      { final_message: "x" },
      controller.signal,
    )

    const [, options] = mockPost.mock.calls[0]
    expect(options.signal).toBe(controller.signal)
  })
})

describe("fetchTaskRuns", () => {
  it("calls client.GET with correct path, params, and limit=50", async () => {
    mockGet.mockResolvedValue({ data: [], error: undefined })

    await fetchTaskRuns("proj-1", "task-2")

    expect(mockGet).toHaveBeenCalledTimes(1)
    const [path, options] = mockGet.mock.calls[0]
    expect(path).toBe("/api/projects/{project_id}/tasks/{task_id}/runs")
    expect(options.params.path).toEqual({
      project_id: "proj-1",
      task_id: "task-2",
    })
    expect(options.params.query).toEqual({ limit: 50 })
  })

  it("returns data as-is from backend (no client-side sort)", async () => {
    const runs = [
      { id: "a", created_at: "2024-06-15T00:00:00Z" },
      { id: "b", created_at: "2024-01-01T00:00:00Z" },
    ]
    mockGet.mockResolvedValue({ data: runs, error: undefined })

    const result = await fetchTaskRuns("p", "t")
    expect(result.map((r) => r.id)).toEqual(["a", "b"])
  })

  it("returns empty array when data is null", async () => {
    mockGet.mockResolvedValue({ data: null, error: undefined })

    const result = await fetchTaskRuns("p", "t")
    expect(result).toEqual([])
  })

  it("throws on error response", async () => {
    mockGet.mockResolvedValue({
      data: undefined,
      error: { message: "Not found" },
    })
    await expect(fetchTaskRuns("p", "t")).rejects.toThrow(
      "Failed to fetch task runs: Not found",
    )
  })
})

describe.each([
  {
    fnName: "testV2Eval",
    callFn: () =>
      testV2Eval("p", "t", "e", {
        properties: {
          type: "exact_match",
          case_sensitive: true,
          value_expression: null,
          expected_value: "hello",
          reference_key: null,
        },
        eval_input: { final_message: "hello" },
      } as TestV2EvalRequest),
    setupMock: (error: Record<string, unknown>) =>
      mockPost.mockResolvedValue({ data: undefined, error }),
    expectedPrefix: "test_v2_eval failed",
  },
  {
    fnName: "createEvalConfig",
    callFn: () =>
      createEvalConfig("p", "t", "e", {
        type: "v2",
        properties: { type: "exact_match", case_sensitive: true },
        model_name: null,
        provider: null,
      } as CreateEvalConfigRequest),
    setupMock: (error: Record<string, unknown>) =>
      mockPost.mockResolvedValue({ data: undefined, error }),
    expectedPrefix: "create_eval_config failed",
  },
  {
    fnName: "checkAddCodeTrust",
    callFn: () => checkAddCodeTrust("proj-1"),
    setupMock: (error: Record<string, unknown>) =>
      mockGet.mockResolvedValue({ data: undefined, error }),
    expectedPrefix: "add_code_trust check failed",
  },
  {
    fnName: "addCodeTrust",
    callFn: () => addCodeTrust("proj-1"),
    setupMock: (error: Record<string, unknown>) =>
      mockPost.mockResolvedValue({ data: undefined, error }),
    expectedPrefix: "add_code_trust failed",
  },
])("$fnName error handling", ({ callFn, setupMock, expectedPrefix }) => {
  it("throws on error response with message field", async () => {
    setupMock({ message: "Server Error" })
    await expect(callFn()).rejects.toThrow(`${expectedPrefix}: Server Error`)
  })

  it("falls back to detail field when message is absent", async () => {
    setupMock({ detail: "Detail fallback" })
    await expect(callFn()).rejects.toThrow(`${expectedPrefix}: Detail fallback`)
  })
})
