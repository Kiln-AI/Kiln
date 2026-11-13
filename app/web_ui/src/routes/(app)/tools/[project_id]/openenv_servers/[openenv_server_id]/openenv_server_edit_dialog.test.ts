// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, cleanup, fireEvent, waitFor } from "@testing-library/svelte"
import type { OpenEnvServer } from "$lib/types"

const mock_patch = vi.fn()

vi.mock("$lib/api_client", () => ({
  client: { PATCH: (...args: unknown[]) => mock_patch(...args) },
}))

// Form fields register their validators from onMount.
vi.mock("svelte", async (importOriginal) =>
  (await import("$lib/test_support/browser_svelte")).browser_svelte(
    importOriginal,
  ),
)

const OpenEnvServerEditDialog = (
  await import("./openenv_server_edit_dialog.svelte")
).default

const ACME: OpenEnvServer = {
  id: "e1",
  name: "Acme",
  description: null,
  url: "http://127.0.0.1:8000",
  is_archived: false,
}

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

function open_dialog() {
  const after_save = vi.fn()
  const { component, container } = render(OpenEnvServerEditDialog, {
    props: {
      project_id: "p1",
      openenv_server_id: "e1",
      openenv_server: ACME,
      after_save,
    },
  })
  component.show()
  return { container, after_save }
}

async function set_url(container: HTMLElement, value: string) {
  await fireEvent.input(container.querySelector("#openenv_server_edit_url")!, {
    target: { value },
  })
}

async function submit(container: HTMLElement) {
  await fireEvent.click(
    container.querySelector('button[type="submit"]') as HTMLButtonElement,
  )
}

describe("OpenEnvServerEditDialog", () => {
  it("prefills the record and hands the saved record back", async () => {
    const saved = { ...ACME, name: "Acme 2" }
    mock_patch.mockResolvedValue({ data: saved, error: undefined })
    const { container, after_save } = open_dialog()
    await waitFor(() =>
      expect(
        container.querySelector<HTMLInputElement>("#openenv_server_edit_url")
          ?.value,
      ).toBe("http://127.0.0.1:8000"),
    )
    expect(
      container
        .querySelector("#openenv_server_edit_url")
        ?.getAttribute("placeholder"),
    ).toBe("http://127.0.0.1:8000")
    await fireEvent.input(
      container.querySelector("#openenv_server_edit_name")!,
      { target: { value: "Acme 2" } },
    )
    await submit(container)
    await waitFor(() => expect(after_save).toHaveBeenCalledWith(saved))
    expect(mock_patch.mock.calls[0][1].body).toEqual({
      name: "Acme 2",
      description: null,
      url: "http://127.0.0.1:8000",
    })
  })

  it("won't submit a URL without http:// or https://", async () => {
    const { container } = open_dialog()
    await waitFor(() =>
      expect(
        container.querySelector("#openenv_server_edit_url"),
      ).not.toBeNull(),
    )
    await set_url(container, "127.0.0.1:8000")
    await submit(container)
    await waitFor(() =>
      expect(container.textContent).toContain(
        "Enter a full URL starting with http:// or https://, like http://127.0.0.1:8000.",
      ),
    )
    expect(mock_patch).not.toHaveBeenCalled()
  })

  it("shows the can't-reach steps when a new URL doesn't answer", async () => {
    mock_patch.mockResolvedValue({
      data: undefined,
      error: { message: "No OpenEnv server answered." },
      response: { status: 502 },
    })
    const { container, after_save } = open_dialog()
    await waitFor(() =>
      expect(
        container.querySelector("#openenv_server_edit_url"),
      ).not.toBeNull(),
    )
    await set_url(container, "http://127.0.0.1:8001")
    await submit(container)
    await waitFor(() =>
      expect(container.textContent).toContain("Can't Reach OpenEnv Server"),
    )
    expect(container.textContent).toContain("No OpenEnv server answered.")
    expect(container.textContent).not.toContain("Unexpected error")
    expect(container.textContent).toContain(
      "If the server is remote, check your network connection.",
    )
    expect(after_save).not.toHaveBeenCalled()
  })

  it("shows a refused save with the same URL as a plain form error", async () => {
    mock_patch.mockResolvedValue({
      data: undefined,
      error: { message: "Name has invalid characters." },
      response: { status: 400 },
    })
    const { container, after_save } = open_dialog()
    await waitFor(() =>
      expect(
        container.querySelector("#openenv_server_edit_name"),
      ).not.toBeNull(),
    )
    await fireEvent.input(
      container.querySelector("#openenv_server_edit_name")!,
      { target: { value: "Acme/2" } },
    )
    await submit(container)
    await waitFor(() =>
      expect(container.textContent).toContain("Name has invalid characters."),
    )
    expect(container.textContent).not.toContain("Can't Reach OpenEnv Server")
    expect(container.textContent).not.toContain("Troubleshooting Steps")
    expect(container.textContent).not.toContain("Unexpected error")
    expect(after_save).not.toHaveBeenCalled()
  })
})
