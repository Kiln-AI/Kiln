import { describe, it, expect, vi, beforeEach } from "vitest"

const mockPost = vi.fn()

vi.mock("$lib/api_client", () => ({
  client: {
    POST: (...args: unknown[]) => mockPost(...args),
  },
}))

import { lookup_run_openenv_server } from "./openenv_server_api"

beforeEach(() => {
  mockPost.mockReset()
})

describe("lookup_run_openenv_server", () => {
  it("posts the tool ids and returns the lookup", async () => {
    const body = {
      openenv_server: { id: "openenv_1", name: "Acme" },
      error: null,
    }
    mockPost.mockResolvedValue({ data: body, error: undefined })

    await expect(
      lookup_run_openenv_server("p1", "t1", [
        "kiln_tool::openenv::openenv_1::list",
      ]),
    ).resolves.toEqual(body)
    expect(mockPost).toHaveBeenCalledWith(
      "/api/projects/{project_id}/tasks/{task_id}/run_openenv_server",
      {
        params: { path: { project_id: "p1", task_id: "t1" } },
        body: { tool_ids: ["kiln_tool::openenv::openenv_1::list"] },
      },
    )
  })

  it("throws the server's error", async () => {
    const error = { message: "Task not found" }
    mockPost.mockResolvedValue({ data: undefined, error })
    await expect(lookup_run_openenv_server("p1", "t1", [])).rejects.toBe(error)
  })
})
