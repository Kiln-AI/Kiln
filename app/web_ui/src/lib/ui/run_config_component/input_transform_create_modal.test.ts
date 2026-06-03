// @vitest-environment jsdom
import { describe, it, expect, vi, beforeAll, beforeEach } from "vitest"
import { render, fireEvent, waitFor } from "@testing-library/svelte"
import { tick } from "svelte"
import InputTransformCreateModal from "./input_transform_create_modal.svelte"

beforeAll(() => {
  if (typeof globalThis.ResizeObserver === "undefined") {
    // eslint-disable-next-line @typescript-eslint/no-extraneous-class
    class ResizeObserverStub {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
    ;(
      globalThis as unknown as { ResizeObserver: typeof ResizeObserverStub }
    ).ResizeObserver = ResizeObserverStub
  }
  HTMLDialogElement.prototype.showModal = vi.fn()
  HTMLDialogElement.prototype.close = vi.fn()
})

const mockPost = vi.fn()

vi.mock("$lib/api_client", () => ({
  client: {
    POST: (...args: unknown[]) => mockPost(...args),
  },
}))

describe("InputTransformCreateModal", () => {
  let on_created: ReturnType<typeof vi.fn>

  beforeEach(() => {
    on_created = vi.fn()
    mockPost.mockReset()
  })

  it("renders title and subtitle", () => {
    const { container } = render(InputTransformCreateModal, {
      props: { on_created },
    })

    expect(container.textContent).toContain("Input Transform")
    expect(container.textContent).toContain(
      "Transform the provided input using a jinja template",
    )
  })

  it("shows error for empty/whitespace template without calling API", async () => {
    const { container, component } = render(InputTransformCreateModal, {
      props: { on_created },
    })
    component.show("")
    await tick()

    const submitButton = container.querySelector(
      'button[type="submit"]',
    ) as HTMLButtonElement
    await fireEvent.click(submitButton)
    await tick()

    expect(container.textContent).toContain("Template can't be empty")
    expect(mockPost).not.toHaveBeenCalled()
    expect(on_created).not.toHaveBeenCalled()
  })

  it("does not leave button stuck in submitting state after empty submit", async () => {
    const { container, component } = render(InputTransformCreateModal, {
      props: { on_created },
    })
    component.show("")
    await tick()

    const submitButton = container.querySelector(
      'button[type="submit"]',
    ) as HTMLButtonElement
    await fireEvent.click(submitButton)
    await tick()

    expect(container.textContent).toContain("Template can't be empty")
    expect(submitButton.disabled).toBe(false)
    expect(submitButton.textContent).toContain("Create")
  })

  it("shows error for whitespace-only template without calling API", async () => {
    const { container, component } = render(InputTransformCreateModal, {
      props: { on_created },
    })
    component.show("   \n\t  ")
    await tick()

    const submitButton = container.querySelector(
      'button[type="submit"]',
    ) as HTMLButtonElement
    await fireEvent.click(submitButton)
    await tick()

    expect(container.textContent).toContain("Template can't be empty")
    expect(mockPost).not.toHaveBeenCalled()
    expect(on_created).not.toHaveBeenCalled()
  })

  it("calls on_created with jinja transform when valid", async () => {
    mockPost.mockResolvedValueOnce({
      data: { valid: true, error: null },
      error: null,
    })

    const { container, component } = render(InputTransformCreateModal, {
      props: { on_created },
    })
    component.show("Hello {{ input }}")
    await tick()

    const submitButton = container.querySelector(
      'button[type="submit"]',
    ) as HTMLButtonElement
    await fireEvent.click(submitButton)

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith(
        "/api/validate_input_transform_template",
        { body: { template: "Hello {{ input }}" } },
      )
      expect(on_created).toHaveBeenCalledWith({
        type: "jinja",
        template: "Hello {{ input }}",
      })
    })
  })

  it("shows validation error and does not call on_created when invalid", async () => {
    mockPost.mockResolvedValueOnce({
      data: { valid: false, error: "Unexpected end of template" },
      error: null,
    })

    const { container, component } = render(InputTransformCreateModal, {
      props: { on_created },
    })
    component.show("{{ unclosed")
    await tick()

    const submitButton = container.querySelector(
      'button[type="submit"]',
    ) as HTMLButtonElement
    await fireEvent.click(submitButton)

    await waitFor(() => {
      expect(container.textContent).toContain("Unexpected end of template")
    })
    expect(on_created).not.toHaveBeenCalled()
  })

  it("shows error on network failure and does not call on_created", async () => {
    mockPost.mockRejectedValueOnce(new Error("Network error"))

    const { container, component } = render(InputTransformCreateModal, {
      props: { on_created },
    })
    component.show("Hello {{ input }}")
    await tick()

    const submitButton = container.querySelector(
      'button[type="submit"]',
    ) as HTMLButtonElement
    await fireEvent.click(submitButton)

    await waitFor(() => {
      expect(container.textContent).toContain("Network error")
    })
    expect(on_created).not.toHaveBeenCalled()
  })

  it("shows error when API returns an error object (non-200)", async () => {
    mockPost.mockResolvedValueOnce({
      data: null,
      error: { detail: "Server error" },
    })

    const { container, component } = render(InputTransformCreateModal, {
      props: { on_created },
    })
    component.show("Hello {{ input }}")
    await tick()

    const submitButton = container.querySelector(
      'button[type="submit"]',
    ) as HTMLButtonElement
    await fireEvent.click(submitButton)

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalled()
    })
    expect(on_created).not.toHaveBeenCalled()
  })

  it("clears validation error when user edits the textarea", async () => {
    const { container, component } = render(InputTransformCreateModal, {
      props: { on_created },
    })
    component.show("")
    await tick()

    const submitButton = container.querySelector(
      'button[type="submit"]',
    ) as HTMLButtonElement
    await fireEvent.click(submitButton)
    await tick()

    expect(container.textContent).toContain("Template can't be empty")

    const textarea = container.querySelector("textarea") as HTMLTextAreaElement
    await fireEvent.input(textarea)
    await tick()

    expect(container.textContent).not.toContain("Template can't be empty")
  })

  it("prefills textarea with initial template", async () => {
    const { container, component } = render(InputTransformCreateModal, {
      props: { on_created },
    })
    component.show("prefilled template")
    await tick()

    const textarea = container.querySelector("textarea") as HTMLTextAreaElement
    expect(textarea.value).toBe("prefilled template")
  })

  it("has a monospace textarea", async () => {
    const { container, component } = render(InputTransformCreateModal, {
      props: { on_created },
    })
    component.show("")
    await tick()

    const textarea = container.querySelector("textarea") as HTMLTextAreaElement
    expect(textarea.classList.contains("font-mono")).toBe(true)
  })
})
