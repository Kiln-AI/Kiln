// @vitest-environment jsdom
import { describe, it, expect, vi, beforeAll } from "vitest"
import { render, fireEvent, waitFor } from "@testing-library/svelte"
import { tick } from "svelte"
import InputTransformSelector from "./input_transform_selector.svelte"
import type { InputTransform } from "$lib/types"

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

vi.mock("$lib/api_client", () => ({
  client: {
    POST: vi.fn(),
  },
}))

const JINJA_TRANSFORM: InputTransform = {
  type: "jinja",
  template: "Hello {{ input }}",
}

describe("InputTransformSelector", () => {
  it("renders the label and info tooltip text", () => {
    const { container } = render(InputTransformSelector, {
      props: { input_transform: null },
    })
    expect(container.textContent).toContain("Input Transform")
    expect(container.textContent).toContain(
      "Transform the provided input before sending the input to the model",
    )
  })

  it('shows "None" as selected label when no transform set', () => {
    const { container } = render(InputTransformSelector, {
      props: { input_transform: null },
    })
    expect(container.textContent).toContain("None")
  })

  it('shows "Custom Template" as selected label when transform is set', () => {
    const { container } = render(InputTransformSelector, {
      props: { input_transform: JINJA_TRANSFORM },
    })
    expect(container.textContent).toContain("Custom Template")
  })

  it("contains the create modal dialog element", () => {
    const { container } = render(InputTransformSelector, {
      props: { input_transform: null },
    })
    const dialog = container.querySelector("dialog")
    expect(dialog).not.toBeNull()
  })

  it("has the modal with correct title", () => {
    const { container } = render(InputTransformSelector, {
      props: { input_transform: null },
    })
    const dialog = container.querySelector("dialog")
    expect(dialog?.textContent).toContain("Input Transform")
  })

  it("clearing transform to null reconciles selector to None", async () => {
    const { container, component } = render(InputTransformSelector, {
      props: { input_transform: JINJA_TRANSFORM },
    })
    expect(container.textContent).toContain("Custom Template")

    // Simulate what happens when the user picks "None" in the FancySelect:
    // the bound select_value changes, triggering handle_select which nulls
    // input_transform. We drive this through the prop to exercise the
    // reactive reconciliation ($: select_value = input_transform ? ...)
    component.input_transform = null
    await tick()

    expect(component.input_transform).toBeNull()
    expect(container.textContent).toContain("None")
    expect(container.textContent).not.toContain("Custom Template")
  })

  it("edit action prefills the modal textarea with the existing template", async () => {
    const { container, component } = render(InputTransformSelector, {
      props: { input_transform: JINJA_TRANSFORM },
    })

    // The textarea starts empty because the modal hasn't been opened yet
    const textarea = container.querySelector("textarea") as HTMLTextAreaElement
    expect(textarea).toBeTruthy()
    expect(textarea.value).toBe("")

    // Verify the selector label shows "Custom Template" (transform is set)
    expect(container.textContent).toContain("Custom Template")

    // The selector's build_options wires an action_handler that calls
    // create_modal.show(transform.template). To test this wiring at the
    // selector level, we find the action_handler from the built options
    // in the component's Svelte context and invoke it directly -- this
    // is the exact function the "Edit Template" button triggers.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const ctx = (component as any).$$.ctx
    const options = ctx.find(
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (item: any) =>
        Array.isArray(item) &&
        item.length > 0 &&
        item[0]?.action_handler != null,
    )
    expect(options).toBeTruthy()
    expect(options[0].action_label).toBe("Edit Template")

    // Invoke the action_handler -- this is the exact closure the
    // "Edit Template" button executes in the FancySelect dropdown.
    // It calls create_modal.show(transform.template) internally.
    options[0].action_handler()
    await tick()

    // After the action_handler runs, the modal's show() should have
    // set template_draft to the existing template, prefilling the textarea.
    expect(textarea.value).toBe("Hello {{ input }}")
  })

  it("modal on_created callback updates input_transform and selector shows Custom Template", async () => {
    const { container, component } = render(InputTransformSelector, {
      props: { input_transform: null },
    })
    expect(container.textContent).toContain("None")
    expect(container.textContent).not.toContain("Custom Template")

    // The modal's form is rendered in the DOM. Fill the textarea and submit
    // to trigger the on_created callback wired from the selector.
    const textarea = container.querySelector("textarea") as HTMLTextAreaElement
    expect(textarea).toBeTruthy()
    textarea.value = "New {{ input }}"
    await fireEvent.input(textarea)
    await tick()

    const { client } = await import("$lib/api_client")
    vi.mocked(client.POST).mockResolvedValueOnce({
      data: { valid: true, error: null },
      error: null,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any)

    const submitButton = container.querySelector(
      'button[type="submit"]',
    ) as HTMLButtonElement
    await fireEvent.click(submitButton)

    await waitFor(() => {
      expect(vi.mocked(client.POST)).toHaveBeenCalledWith(
        "/api/validate_input_transform_template",
        { body: { template: "New {{ input }}" } },
      )
    })
    await tick()

    expect(component.input_transform).toEqual({
      type: "jinja",
      template: "New {{ input }}",
    })
    expect(container.textContent).toContain("Custom Template")
  })
})
