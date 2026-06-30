// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, cleanup, waitFor } from "@testing-library/svelte"

vi.mock("$lib/stores", () => {
  const { writable } = require("svelte/store")
  return {
    projects: writable({
      projects: [{ id: "proj_1", name: "My Project" }],
    }),
    current_project: writable({ id: "proj_1", name: "My Project" }),
    current_task: writable(null),
    ui_state: writable({
      current_project_id: "proj_1",
      current_task_id: null,
    }),
  }
})

vi.mock("$lib/api_client", () => ({
  client: {
    GET: vi.fn(),
  },
}))

vi.mock("$app/navigation", () => ({
  goto: vi.fn(),
}))

import SelectTasksMenu from "./select_tasks_menu.svelte"
import { client } from "$lib/api_client"

afterEach(() => {
  cleanup()
})

beforeEach(() => {
  vi.mocked(client.GET).mockReset()
})

describe("SelectTasksMenu error state", () => {
  it("shows the error message and re-import link on task load failure", async () => {
    vi.mocked(client.GET).mockRejectedValue(
      new Error("Git authentication failed"),
    )

    const { container } = render(SelectTasksMenu)

    await waitFor(() => {
      expect(container.textContent).toContain("Git authentication failed")
    })

    const link = container.querySelector(
      'a[href="/settings/import_project"]',
    ) as HTMLAnchorElement
    expect(link).not.toBeNull()
    expect(link.textContent?.trim()).toBe("Re-import project?")
  })

  it("uses the default import_project_url for the in-app context", async () => {
    vi.mocked(client.GET).mockRejectedValue(new Error("some error"))

    const { container } = render(SelectTasksMenu)

    await waitFor(() => {
      expect(container.textContent).toContain("some error")
    })

    const link = container.querySelector(
      'a[href="/settings/import_project"]',
    ) as HTMLAnchorElement
    expect(link).not.toBeNull()
  })

  it("uses the custom import_project_url prop for the setup context", async () => {
    vi.mocked(client.GET).mockRejectedValue(new Error("some error"))

    const { container } = render(SelectTasksMenu, {
      props: { import_project_url: "/setup/import_project" },
    })

    await waitFor(() => {
      expect(container.textContent).toContain("some error")
    })

    const link = container.querySelector(
      'a[href="/setup/import_project"]',
    ) as HTMLAnchorElement
    expect(link).not.toBeNull()
    expect(link.textContent?.trim()).toBe("Re-import project?")
  })

  it("does not show re-import link when tasks load successfully", async () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    vi.mocked(client.GET).mockResolvedValue({
      data: [{ id: "task_1", name: "My Task" }],
      error: undefined,
      response: new Response(),
    } as any)

    const { container } = render(SelectTasksMenu)

    await waitFor(() => {
      expect(container.textContent).toContain("My Task")
    })

    const link = container.querySelector('a[href="/settings/import_project"]')
    expect(link).toBeNull()
  })
})
