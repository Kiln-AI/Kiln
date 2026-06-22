// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from "vitest"
import { render, cleanup, fireEvent, waitFor } from "@testing-library/svelte"
import { tick } from "svelte"

vi.mock("$lib/api_client", () => ({
  client: {
    GET: vi.fn(),
    POST: vi.fn(),
  },
}))

vi.mock("$lib/stores", () => ({
  load_projects: vi.fn().mockResolvedValue(undefined),
}))

vi.mock("$app/navigation", () => ({
  replaceState: vi.fn(),
  beforeNavigate: vi.fn(),
}))

vi.mock("posthog-js", () => ({
  default: { capture: vi.fn() },
}))

vi.mock("$lib/git_sync/url_utils", () => ({
  sync_url_query_param: vi.fn(),
  read_url_query_param: vi.fn().mockReturnValue(null),
}))

vi.mock("$lib/stores/git_import_wizard_store", () => {
  const { writable } = require("svelte/store")
  return {
    git_import_wizard_store: writable({
      git_url: "",
      pat_token: null,
      oauth_token: null,
      auth_mode: "system_keys",
      clone_path: "",
      selected_branch: "",
      selected_project_path: "",
      selected_project_id: "",
      selected_project_name: "",
    }),
    clear_wizard_store: vi.fn(),
    validate_step_requirements: vi.fn().mockReturnValue(true),
  }
})

import ImportProject from "./import_project.svelte"
import { client } from "$lib/api_client"

const baseProps = {
  create_link: "/create",
  on_complete: vi.fn(),
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  window.location.hash = ""
})

beforeEach(() => {
  vi.mocked(client.POST).mockReset()
  vi.mocked(client.GET).mockReset()
  vi.mocked(baseProps.on_complete).mockReset()
  window.location.hash = ""
})

describe("ImportProject local_file conflict handling", () => {
  async function renderAtLocalStep() {
    const result = render(ImportProject, { props: baseProps })
    await tick()

    // Click "Import from Local Folder" button to navigate to local_file step
    const localBtn = result.getByText("Import from Local Folder")
    await fireEvent.click(localBtn)
    await tick()

    // Now trigger the file selector error to reveal the manual path input
    vi.mocked(client.GET).mockRejectedValue(new Error("No file selector"))
    const selectBtn = result.container.querySelector(
      "button.btn-primary",
    ) as HTMLButtonElement
    if (selectBtn?.textContent?.includes("Select Project File")) {
      await fireEvent.click(selectBtn)
      await tick()
      await new Promise((r) => setTimeout(r, 0))
      await tick()
    }

    return result
  }

  it("shows conflict button on 409 response", async () => {
    vi.mocked(client.POST).mockResolvedValue({
      data: undefined,
      error: { message: "Duplicate project ID" },
      response: new Response(null, { status: 409 }),
    } as never)

    const { container } = await renderAtLocalStep()

    const input = container.querySelector(
      "#import_project_path",
    ) as HTMLInputElement
    expect(input).toBeTruthy()
    await fireEvent.input(input, {
      target: { value: "/path/to/project.kiln" },
    })
    await tick()

    const submitBtn = container.querySelector(
      'button[type="submit"]',
    ) as HTMLButtonElement
    expect(submitBtn).toBeTruthy()
    await fireEvent.click(submitBtn)
    await tick()
    await new Promise((r) => setTimeout(r, 0))
    await tick()

    await waitFor(() => {
      expect(container.textContent).toContain("Remove existing and re-import")
    })

    // Normal submit button should be hidden in conflict state
    const hiddenSubmit = container.querySelector(
      'button[type="submit"]',
    ) as HTMLButtonElement
    expect(hiddenSubmit?.classList.contains("hidden")).toBe(true)
  })

  it("conflict button is type=button so it cannot submit the form", async () => {
    vi.mocked(client.POST).mockResolvedValue({
      data: undefined,
      error: { message: "Duplicate project ID" },
      response: new Response(null, { status: 409 }),
    } as never)

    const { container, getByText } = await renderAtLocalStep()

    const input = container.querySelector(
      "#import_project_path",
    ) as HTMLInputElement
    await fireEvent.input(input, {
      target: { value: "/path/to/project.kiln" },
    })
    await tick()

    const submitBtn = container.querySelector(
      'button[type="submit"]',
    ) as HTMLButtonElement
    await fireEvent.click(submitBtn)
    await tick()
    await new Promise((r) => setTimeout(r, 0))
    await tick()

    await waitFor(() => {
      expect(container.textContent).toContain("Remove existing and re-import")
    })

    // type="button" keeps the conflict button out of implicit form submission.
    // Without it the button defaults to type="submit" and, as the first submit
    // button in tree order, would become the form's default button -- so Enter
    // in the path field could fire the destructive remove-and-re-import action.
    const conflictBtn = getByText(
      "Remove existing and re-import",
    ) as HTMLButtonElement
    expect(conflictBtn.getAttribute("type")).toBe("button")
  })

  it("does not show conflict button on non-409 error", async () => {
    vi.mocked(client.POST).mockResolvedValue({
      data: undefined,
      error: { message: "Server error" },
      response: new Response(null, { status: 500 }),
    } as never)

    const { container } = await renderAtLocalStep()

    const input = container.querySelector(
      "#import_project_path",
    ) as HTMLInputElement
    expect(input).toBeTruthy()
    await fireEvent.input(input, {
      target: { value: "/path/to/project.kiln" },
    })
    await tick()

    const submitBtn = container.querySelector(
      'button[type="submit"]',
    ) as HTMLButtonElement
    await fireEvent.click(submitBtn)
    await tick()
    await new Promise((r) => setTimeout(r, 0))
    await tick()

    await waitFor(() => {
      expect(container.textContent).toContain("Server error")
    })
    expect(container.textContent).not.toContain("Remove existing and re-import")
  })

  it("clicking conflict button retries with remove_conflicting_id=true", async () => {
    // First call: 409 conflict
    vi.mocked(client.POST).mockResolvedValueOnce({
      data: undefined,
      error: { message: "Duplicate project ID" },
      response: new Response(null, { status: 409 }),
    } as never)

    const { container, getByText } = await renderAtLocalStep()

    const input = container.querySelector(
      "#import_project_path",
    ) as HTMLInputElement
    expect(input).toBeTruthy()
    await fireEvent.input(input, {
      target: { value: "/path/to/project.kiln" },
    })
    await tick()

    const submitBtn = container.querySelector(
      'button[type="submit"]',
    ) as HTMLButtonElement
    await fireEvent.click(submitBtn)
    await tick()
    await new Promise((r) => setTimeout(r, 0))
    await tick()

    await waitFor(() => {
      expect(container.textContent).toContain("Remove existing and re-import")
    })

    // Second call: success
    vi.mocked(client.POST).mockResolvedValueOnce({
      data: { id: "proj_1", name: "Imported" },
      error: undefined,
      response: new Response(null, { status: 200 }),
    } as never)

    const conflictBtn = getByText("Remove existing and re-import")
    await fireEvent.click(conflictBtn)
    await tick()
    await new Promise((r) => setTimeout(r, 0))
    await tick()

    // Verify the second call included remove_conflicting_id
    const calls = vi.mocked(client.POST).mock.calls
    expect(calls.length).toBe(2)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const secondCallOpts = calls[1][1] as any
    expect(secondCallOpts?.params?.query?.remove_conflicting_id).toBe(true)
  })

  it("editing path after 409 clears conflict state and restores submit button", async () => {
    vi.mocked(client.POST).mockResolvedValue({
      data: undefined,
      error: { message: "Duplicate project ID" },
      response: new Response(null, { status: 409 }),
    } as never)

    const { container } = await renderAtLocalStep()

    const input = container.querySelector(
      "#import_project_path",
    ) as HTMLInputElement
    expect(input).toBeTruthy()
    await fireEvent.input(input, {
      target: { value: "/path/to/project.kiln" },
    })
    await tick()

    const submitBtn = container.querySelector(
      'button[type="submit"]',
    ) as HTMLButtonElement
    await fireEvent.click(submitBtn)
    await tick()
    await new Promise((r) => setTimeout(r, 0))
    await tick()

    // Confirm conflict state is active
    await waitFor(() => {
      expect(container.textContent).toContain("Remove existing and re-import")
    })
    expect(submitBtn?.classList.contains("hidden")).toBe(true)

    // Now edit the path via typing - should clear conflict and restore normal submit
    await fireEvent.input(input, {
      target: { value: "/different/path/project.kiln" },
    })
    await tick()

    await waitFor(() => {
      expect(container.textContent).not.toContain(
        "Remove existing and re-import",
      )
    })

    // Normal submit button should be visible again
    const restoredSubmit = container.querySelector(
      'button[type="submit"]',
    ) as HTMLButtonElement
    expect(restoredSubmit?.classList.contains("hidden")).toBe(false)
  })

  it("file picker programmatic path change clears conflict via reactive block", async () => {
    // Validates the reactive clearing mechanism via the real file-picker path.
    // select_project_file() sets import_project_path programmatically (no DOM
    // input event), which the old on:input wrapper div would have missed.
    const result = render(ImportProject, { props: baseProps })
    await tick()

    const localBtn = result.getByText("Import from Local Folder")
    await fireEvent.click(localBtn)
    await tick()

    const { container } = result

    // Use the file picker (not manual input) to set the initial path
    vi.mocked(client.GET).mockResolvedValueOnce({
      data: { file_path: "/path/to/project.kiln" },
      error: undefined,
      response: new Response(null, { status: 200 }),
    } as never)

    const selectBtn = container.querySelector(
      "button.btn-primary",
    ) as HTMLButtonElement
    expect(selectBtn?.textContent).toContain("Select Project File")
    await fireEvent.click(selectBtn)
    await tick()
    await new Promise((r) => setTimeout(r, 0))
    await tick()

    // Path was set programmatically by the file picker; input field should show
    const input = container.querySelector(
      "#import_project_path",
    ) as HTMLInputElement
    expect(input).toBeTruthy()
    expect(input.value).toBe("/path/to/project.kiln")

    // Submit -> 409 conflict
    vi.mocked(client.POST).mockResolvedValueOnce({
      data: undefined,
      error: { message: "Duplicate project ID" },
      response: new Response(null, { status: 409 }),
    } as never)

    const submitBtn = container.querySelector(
      'button[type="submit"]',
    ) as HTMLButtonElement
    await fireEvent.click(submitBtn)
    await tick()
    await new Promise((r) => setTimeout(r, 0))
    await tick()

    // Conflict button appears (reactive did NOT self-wipe on the 409)
    await waitFor(() => {
      expect(container.textContent).toContain("Remove existing and re-import")
    })
    expect(submitBtn?.classList.contains("hidden")).toBe(true)

    // Clear the path to make the file picker button reappear.
    // This also clears the conflict (expected: path changed from the conflict path).
    await fireEvent.input(input, { target: { value: "" } })
    await tick()

    await waitFor(() => {
      expect(container.textContent).not.toContain(
        "Remove existing and re-import",
      )
    })

    // File picker button is visible again (select_file_unavailable is still false)
    const selectBtn2 = container.querySelector(
      "button.btn-primary",
    ) as HTMLButtonElement
    expect(selectBtn2?.textContent).toContain("Select Project File")

    // Use the file picker to set a DIFFERENT path programmatically
    vi.mocked(client.GET).mockResolvedValueOnce({
      data: { file_path: "/different/programmatic/path.kiln" },
      error: undefined,
      response: new Response(null, { status: 200 }),
    } as never)

    await fireEvent.click(selectBtn2)
    await tick()
    await new Promise((r) => setTimeout(r, 0))
    await tick()

    // Verify the file picker set the new path programmatically
    const updatedInput = container.querySelector(
      "#import_project_path",
    ) as HTMLInputElement
    expect(updatedInput?.value).toBe("/different/programmatic/path.kiln")

    // Submit again -> 409
    vi.mocked(client.POST).mockResolvedValueOnce({
      data: undefined,
      error: { message: "Duplicate project ID" },
      response: new Response(null, { status: 409 }),
    } as never)

    const submitBtn2 = container.querySelector(
      'button[type="submit"]',
    ) as HTMLButtonElement
    await fireEvent.click(submitBtn2)
    await tick()
    await new Promise((r) => setTimeout(r, 0))
    await tick()

    // Conflict button appears again -- the reactive block correctly handled the
    // programmatic path set from the file picker without self-wiping on the 409
    await waitFor(() => {
      expect(container.textContent).toContain("Remove existing and re-import")
    })

    const hiddenSubmit = container.querySelector(
      'button[type="submit"]',
    ) as HTMLButtonElement
    expect(hiddenSubmit?.classList.contains("hidden")).toBe(true)
  })
})
