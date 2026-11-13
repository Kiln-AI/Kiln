import { describe, it, expect, vi, beforeEach } from "vitest"

const mockPost = vi.fn()
const mockGet = vi.fn()
const mockPatch = vi.fn()

vi.mock("$lib/api_client", () => ({
  client: {
    POST: (...args: unknown[]) => mockPost(...args),
    GET: (...args: unknown[]) => mockGet(...args),
    PATCH: (...args: unknown[]) => mockPatch(...args),
  },
}))

import { KilnError } from "$lib/utils/error_handlers"
import {
  create_openenv_server,
  is_openenv_unreachable,
  load_archived_openenv_server_ids,
  lookup_run_openenv_server,
  openenv_server_error,
  update_openenv_server,
} from "./openenv_server_api"

beforeEach(() => {
  mockPost.mockReset()
  mockGet.mockReset()
  mockPatch.mockReset()
})

const FIELDS = {
  name: "Acme",
  description: null,
  url: "http://127.0.0.1:8000",
}

describe("openenv_server_error", () => {
  it("keeps the backend's message without a prefix", () => {
    const error = openenv_server_error({
      message: "No OpenEnv server answered at http://127.0.0.1:8000.",
    })
    expect(error.getMessage()).toBe(
      "No OpenEnv server answered at http://127.0.0.1:8000.",
    )
  })

  it("passes a KilnError through", () => {
    const error = new KilnError("Already a KilnError")
    expect(openenv_server_error(error)).toBe(error)
  })

  it("falls back to the shared handler for other shapes", () => {
    expect(openenv_server_error(undefined).getMessage()).toBe("Unknown error")
  })
})

describe("create_openenv_server", () => {
  it("posts the fields and returns the saved record", async () => {
    mockPost.mockResolvedValue({
      data: { id: "openenv_1", ...FIELDS },
      error: undefined,
    })
    await expect(create_openenv_server("p1", FIELDS)).resolves.toEqual({
      id: "openenv_1",
      ...FIELDS,
    })
    expect(mockPost).toHaveBeenCalledWith(
      "/api/projects/{project_id}/openenv_servers",
      { params: { path: { project_id: "p1" } }, body: FIELDS },
    )
  })

  it("marks a 502 as the server not answering, without a prefix", async () => {
    mockPost.mockResolvedValue({
      data: undefined,
      error: { message: "Server down" },
      response: { status: 502 },
    })
    const error = await create_openenv_server("p1", FIELDS).catch((e) => e)
    expect(error.getMessage()).toBe("Server down")
    expect(is_openenv_unreachable(error)).toBe(true)
  })

  it("doesn't mark a 400 as the server not answering", async () => {
    mockPost.mockResolvedValue({
      data: undefined,
      error: { message: "Bad name" },
      response: { status: 400 },
    })
    const error = await create_openenv_server("p1", FIELDS).catch((e) => e)
    expect(error.getMessage()).toBe("Bad name")
    expect(is_openenv_unreachable(error)).toBe(false)
  })
})

describe("update_openenv_server", () => {
  it("patches the fields and returns the saved record", async () => {
    mockPatch.mockResolvedValue({
      data: { id: "openenv_1", ...FIELDS },
      error: undefined,
    })
    await expect(
      update_openenv_server("p1", "openenv_1", FIELDS),
    ).resolves.toEqual({ id: "openenv_1", ...FIELDS })
    expect(mockPatch).toHaveBeenCalledWith(
      "/api/projects/{project_id}/openenv_servers/{openenv_server_id}",
      {
        params: { path: { project_id: "p1", openenv_server_id: "openenv_1" } },
        body: FIELDS,
      },
    )
  })

  it.each([
    [502, true],
    [400, false],
  ])(
    "throws the backend's message for a %i, unreachable: %s",
    async (status, unreachable) => {
      mockPatch.mockResolvedValue({
        data: undefined,
        error: { message: "Refused" },
        response: { status },
      })
      const error = await update_openenv_server(
        "p1",
        "openenv_1",
        FIELDS,
      ).catch((e) => e)
      expect(error.getMessage()).toBe("Refused")
      expect(is_openenv_unreachable(error)).toBe(unreachable)
    },
  )
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
