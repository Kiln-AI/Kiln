import { describe, it, expect, vi, beforeEach } from "vitest"

const mockPost = vi.fn()
const mockGet = vi.fn()

vi.mock("$lib/api_client", () => ({
  client: {
    POST: (...args: unknown[]) => mockPost(...args),
    GET: (...args: unknown[]) => mockGet(...args),
  },
}))

import {
  load_archived_openenv_server_ids,
  lookup_run_openenv_server,
} from "./openenv_server_api"

beforeEach(() => {
  mockPost.mockReset()
  mockGet.mockReset()
})

describe("load_archived_openenv_server_ids", () => {
  it("returns the ids of the archived servers only", async () => {
    mockGet.mockResolvedValue({
      data: [
        { id: "openenv_1", name: "Acme", is_archived: false },
        { id: "openenv_2", name: "Beta", is_archived: true },
        { name: "Unsaved", is_archived: true },
      ],
      error: undefined,
    })
    await expect(load_archived_openenv_server_ids("p1")).resolves.toEqual(
      new Set(["openenv_2"]),
    )
    expect(mockGet).toHaveBeenCalledWith(
      "/api/projects/{project_id}/openenv_servers",
      { params: { path: { project_id: "p1" } } },
    )
  })

  it("throws the server's error", async () => {
    const error = { message: "Project not found" }
    mockGet.mockResolvedValue({ data: undefined, error })
    await expect(load_archived_openenv_server_ids("p1")).rejects.toBe(error)
  })
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
