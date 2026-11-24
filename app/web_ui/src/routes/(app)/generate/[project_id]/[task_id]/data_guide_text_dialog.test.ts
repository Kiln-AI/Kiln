// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, cleanup, fireEvent, waitFor } from "@testing-library/svelte"

const mock_put = vi.fn()

vi.mock("$lib/api_client", () => ({
  client: { PUT: (...args: unknown[]) => mock_put(...args) },
}))

// Form fields register their validators from onMount.
vi.mock("svelte", async (importOriginal) =>
  (await import("$lib/test_support/browser_svelte")).browser_svelte(
    importOriginal,
  ),
)

const DataGuideTextDialog = (await import("./data_guide_text_dialog.svelte"))
  .default

beforeEach(() => {
  // The error block's Output measures itself; jsdom has no ResizeObserver.
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  )
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(HTMLDialogElement.prototype as any).showModal = function (
    this: HTMLDialogElement,
  ) {
    this.setAttribute("open", "")
  }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(HTMLDialogElement.prototype as any).close = function (
    this: HTMLDialogElement,
  ) {
    this.removeAttribute("open")
  }
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  vi.unstubAllGlobals()
})

function open_dialog(initial_text = "") {
  const on_saved = vi.fn()
  const { component, container } = render(DataGuideTextDialog, {
    props: { project_id: "p1", task_id: "t1", on_saved },
  })
  component.show(initial_text)
  return { container, on_saved }
}

function submit_button(container: HTMLElement): HTMLButtonElement {
  return container.querySelector('button[type="submit"]') as HTMLButtonElement
}

describe("DataGuideTextDialog", () => {
  it("starts with the text it was opened with", async () => {
    const { container } = open_dialog("Members renew books.")
    await waitFor(() =>
      expect(
        container.querySelector<HTMLTextAreaElement>("#data_guide_text")?.value,
      ).toBe("Members renew books."),
    )
  })

  it("saves the trimmed text as the task's guide and hands it back", async () => {
    const saved = { guide: "Members renew books." }
    mock_put.mockResolvedValue({ data: saved, error: undefined })
    const { container, on_saved } = open_dialog("  Members renew books. \n")
    await fireEvent.click(submit_button(container))
    await waitFor(() => expect(on_saved).toHaveBeenCalledWith(saved))
    expect(mock_put).toHaveBeenCalledWith(
      "/api/projects/{project_id}/tasks/{task_id}/data_gen_guide",
      {
        params: { path: { project_id: "p1", task_id: "t1" } },
        body: { guide: "Members renew books." },
      },
    )
  })

  it("shows the error and keeps the dialog open when the save fails", async () => {
    mock_put.mockResolvedValue({
      data: undefined,
      error: { message: "Disk full." },
    })
    const { container, on_saved } = open_dialog("Members renew books.")
    await fireEvent.click(submit_button(container))
    await waitFor(() => expect(container.textContent).toContain("Disk full."))
    expect(on_saved).not.toHaveBeenCalled()
  })

  it("won't save an empty guide", async () => {
    const { container } = open_dialog("   ")
    await waitFor(() => expect(submit_button(container).disabled).toBe(true))
  })
})
