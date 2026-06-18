import { describe, it, expect, vi, beforeEach } from "vitest"
import {
  testV2Eval,
  createEvalConfig,
  checkCodeEvalTrust,
  grantCodeEvalTrust,
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

describe("checkCodeEvalTrust", () => {
  it("calls client.GET with correct path and params", async () => {
    mockGet.mockResolvedValue({
      data: { trusted: false },
      error: undefined,
    })

    await checkCodeEvalTrust("proj-1")

    expect(mockGet).toHaveBeenCalledTimes(1)
    const [path, options] = mockGet.mock.calls[0]
    expect(path).toBe("/api/projects/{project_id}/code_eval_trust")
    expect(options.params.path).toEqual({ project_id: "proj-1" })
  })

  it("returns parsed trust response", async () => {
    mockGet.mockResolvedValue({
      data: { trusted: true },
      error: undefined,
    })

    const result = await checkCodeEvalTrust("proj-1")
    expect(result.trusted).toBe(true)
  })
})

describe("grantCodeEvalTrust", () => {
  it("calls client.POST with correct path and params", async () => {
    mockPost.mockResolvedValue({
      data: { trusted: true },
      error: undefined,
    })

    await grantCodeEvalTrust("proj-1")

    expect(mockPost).toHaveBeenCalledTimes(1)
    const [path, options] = mockPost.mock.calls[0]
    expect(path).toBe("/api/projects/{project_id}/grant_code_eval_trust")
    expect(options.params.path).toEqual({ project_id: "proj-1" })
  })

  it("returns parsed grant response", async () => {
    mockPost.mockResolvedValue({
      data: { trusted: true },
      error: undefined,
    })

    const result = await grantCodeEvalTrust("proj-1")
    expect(result.trusted).toBe(true)
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
    fnName: "checkCodeEvalTrust",
    callFn: () => checkCodeEvalTrust("proj-1"),
    setupMock: (error: Record<string, unknown>) =>
      mockGet.mockResolvedValue({ data: undefined, error }),
    expectedPrefix: "code_eval_trust check failed",
  },
  {
    fnName: "grantCodeEvalTrust",
    callFn: () => grantCodeEvalTrust("proj-1"),
    setupMock: (error: Record<string, unknown>) =>
      mockPost.mockResolvedValue({ data: undefined, error }),
    expectedPrefix: "grant_code_eval_trust failed",
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
