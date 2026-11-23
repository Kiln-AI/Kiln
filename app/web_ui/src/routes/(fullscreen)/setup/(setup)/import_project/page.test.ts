// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from "vitest"
import { render, cleanup, waitFor } from "@testing-library/svelte"

vi.mock("$lib/api_client", () => ({
  client: {
    GET: vi.fn(),
  },
}))

vi.mock("$app/navigation", () => ({
  goto: vi.fn(),
}))

vi.mock("$lib/components/import/import_project.svelte", async () => {
  const Stub = await import("./__tests__/import_project_stub.svelte")
  return { default: Stub.default }
})

import Page from "./+page.svelte"
import { client } from "$lib/api_client"
import { goto } from "$app/navigation"
import { importProjectProps } from "./__tests__/import_project_stub.svelte"

function mock_tasks_response(response: unknown) {
  vi.mocked(client.GET).mockResolvedValue(response as never)
}

beforeEach(() => {
  vi.mocked(client.GET).mockReset()
  vi.mocked(goto).mockReset()
})

afterEach(() => {
  cleanup()
})

describe("Setup import project page: after an import", () => {
  it("opens Select a Task with the imported project in the URL when it has tasks", async () => {
    mock_tasks_response({ data: [{ id: "task_1" }], error: undefined })
    render(Page)

    importProjectProps.on_complete?.("proj 1")

    await waitFor(() => {
      expect(goto).toHaveBeenCalledWith(
        "/setup/select_task?project_id=proj%201",
      )
    })
    expect(client.GET).toHaveBeenCalledWith(
      "/api/projects/{project_id}/tasks",
      { params: { path: { project_id: "proj 1" } } },
    )
  })

  it("opens Create Task when the imported project has no tasks", async () => {
    mock_tasks_response({ data: [], error: undefined })
    render(Page)

    importProjectProps.on_complete?.("proj_1")

    await waitFor(() => {
      expect(goto).toHaveBeenCalledWith("/setup/create_task/proj_1")
    })
  })

  it("opens Select a Task when the task list fails to load", async () => {
    mock_tasks_response({ data: undefined, error: { message: "failed" } })
    render(Page)

    importProjectProps.on_complete?.("proj_1")

    await waitFor(() => {
      expect(goto).toHaveBeenCalledWith("/setup/select_task?project_id=proj_1")
    })
  })
})
