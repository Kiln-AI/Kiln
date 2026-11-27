import { describe, it, expect, vi, beforeEach } from "vitest"
import { grant_code_trust, load_trust_code } from "./trust_code"

const { mockGet, mockCheckTrust, mockAddTrust } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockCheckTrust: vi.fn(),
  mockAddTrust: vi.fn(),
}))

vi.mock("$lib/api_client", () => ({ client: { GET: mockGet } }))
vi.mock("$lib/api/v2_eval_api", () => ({
  checkAddCodeTrust: mockCheckTrust,
  addCodeTrust: mockAddTrust,
}))

beforeEach(() => {
  mockGet.mockReset()
  mockCheckTrust.mockReset()
  mockAddTrust.mockReset()
  mockGet.mockResolvedValue({ data: { name: "Support Bot" }, error: undefined })
})

describe("load_trust_code", () => {
  it("asks the question when the project is not trusted", async () => {
    mockCheckTrust.mockResolvedValue({ trusted: false })
    expect(await load_trust_code("p1")).toEqual({
      kind: "question",
      project_name: "Support Bot",
    })
    expect(mockGet).toHaveBeenCalledWith("/api/projects/{project_id}", {
      params: { path: { project_id: "p1" } },
    })
    expect(mockCheckTrust).toHaveBeenCalledWith("p1")
  })

  it("is trusted when trust was already granted", async () => {
    mockCheckTrust.mockResolvedValue({ trusted: true })
    expect(await load_trust_code("p1")).toEqual({
      kind: "trusted",
      project_name: "Support Bot",
    })
  })

  it("is an error when the project does not load", async () => {
    mockGet.mockResolvedValue({
      data: undefined,
      error: { message: "Project not found" },
    })
    mockCheckTrust.mockResolvedValue({ trusted: false })
    const state = await load_trust_code("p1")
    expect(state.kind).toBe("error")
    if (state.kind === "error") {
      expect(state.error.getMessage()).toContain("Project not found")
    }
  })

  it("is an error when the trust check fails", async () => {
    mockCheckTrust.mockRejectedValue(new Error("add_code_trust check failed"))
    const state = await load_trust_code("p1")
    expect(state.kind).toBe("error")
  })
})

describe("grant_code_trust", () => {
  it("returns null when trust is granted", async () => {
    mockAddTrust.mockResolvedValue({ trusted: true })
    expect(await grant_code_trust("p1")).toBeNull()
    expect(mockAddTrust).toHaveBeenCalledWith("p1")
  })

  it("returns the error when the grant fails", async () => {
    mockAddTrust.mockRejectedValue(new Error("add_code_trust failed: boom"))
    const error = await grant_code_trust("p1")
    expect(error?.getMessage()).toContain("boom")
  })
})
