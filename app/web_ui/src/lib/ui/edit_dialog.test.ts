// @vitest-environment jsdom
import { describe, it, expect, beforeAll, afterEach, vi } from "vitest"
import { render, fireEvent, cleanup, waitFor } from "@testing-library/svelte"
import { tick } from "svelte"
import EditDialog from "./edit_dialog.svelte"

beforeAll(() => {
  if (!HTMLDialogElement.prototype.showModal) {
    HTMLDialogElement.prototype.showModal = function () {
      this.open = true
    }
  }
  if (!HTMLDialogElement.prototype.close) {
    HTMLDialogElement.prototype.close = function () {
      this.open = false
    }
  }
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

async function submit_form() {
  const save_button = document.querySelector(
    'button[type="submit"]',
  ) as HTMLButtonElement
  expect(save_button).not.toBeNull()
  await fireEvent.click(save_button)
}

describe("EditDialog custom_setter", () => {
  it("excludes custom_setter fields from the PATCH body and invokes their setter", async () => {
    const fetch_mock = vi
      .spyOn(global, "fetch")
      .mockResolvedValue(new Response(JSON.stringify({}), { status: 200 }))
    const custom_setter = vi.fn().mockResolvedValue(undefined)

    const { component } = render(EditDialog, {
      props: {
        name: "Thing",
        patch_url: "/api/thing",
        fields: [
          {
            label: "Name",
            api_name: "name",
            value: "new name",
            input_type: "input",
          },
          {
            label: "Display Name",
            api_name: "display_name_a",
            value: "Quality Check",
            input_type: "input",
            custom_setter,
          },
        ],
      },
    })
    component.show()
    await tick()

    await submit_form()

    await waitFor(() => expect(custom_setter).toHaveBeenCalledTimes(1))
    expect(custom_setter).toHaveBeenCalledWith({
      display_name_a: "Quality Check",
    })

    expect(fetch_mock).toHaveBeenCalledTimes(1)
    const [, init] = fetch_mock.mock.calls[0]
    const body = JSON.parse((init?.body as string) ?? "{}")
    expect(body).toEqual({ name: "new name" })
  })

  it("invokes a shared custom_setter once, with every field's value", async () => {
    const fetch_mock = vi
      .spyOn(global, "fetch")
      .mockResolvedValue(new Response(JSON.stringify({}), { status: 200 }))
    const custom_setter = vi.fn().mockResolvedValue(undefined)

    const { component } = render(EditDialog, {
      props: {
        name: "Thing",
        patch_url: "/api/thing",
        fields: [
          {
            label: "Score 0",
            api_name: "display_name_a",
            value: "A",
            input_type: "input",
            custom_setter,
          },
          {
            label: "Score 1",
            api_name: "display_name_b",
            value: "B",
            input_type: "input",
            custom_setter,
          },
        ],
      },
    })
    component.show()
    await tick()

    await submit_form()

    await waitFor(() => expect(custom_setter).toHaveBeenCalledTimes(1))
    expect(custom_setter).toHaveBeenCalledWith({
      display_name_a: "A",
      display_name_b: "B",
    })
    expect(fetch_mock).not.toHaveBeenCalled()
  })

  it("skips the main PATCH and after_save when a custom_setter rejects", async () => {
    const fetch_mock = vi
      .spyOn(global, "fetch")
      .mockResolvedValue(new Response(JSON.stringify({}), { status: 200 }))
    const custom_setter = vi
      .fn()
      .mockRejectedValue(new Error("display name rejected"))
    const after_save = vi.fn()

    const { component, getAllByText, container } = render(EditDialog, {
      props: {
        name: "Thing",
        patch_url: "/api/thing",
        after_save,
        fields: [
          {
            label: "Name",
            api_name: "name",
            value: "new name",
            input_type: "input",
          },
          {
            label: "Display Name",
            api_name: "display_name_a",
            value: "Quality Check",
            input_type: "input",
            custom_setter,
          },
        ],
      },
    })
    component.show()
    await tick()

    await submit_form()

    // The setter runs first and rejects, so the main PATCH is never sent
    await waitFor(() => expect(custom_setter).toHaveBeenCalledTimes(1))
    expect(fetch_mock).not.toHaveBeenCalled()
    // after_save is never called, so the dialog is not dismissed; the error is shown
    expect(after_save).not.toHaveBeenCalled()
    await waitFor(() =>
      expect(getAllByText(/display name rejected/).length).toBeGreaterThan(0),
    )
    // The dialog remains open
    expect(container.querySelector("dialog[open]")).not.toBeNull()
  })

  it("skips the PATCH request entirely when every field has a custom_setter", async () => {
    const fetch_mock = vi
      .spyOn(global, "fetch")
      .mockResolvedValue(new Response(JSON.stringify({}), { status: 200 }))
    const custom_setter = vi.fn().mockResolvedValue(undefined)

    const { component } = render(EditDialog, {
      props: {
        name: "Thing",
        patch_url: "/api/thing",
        fields: [
          {
            label: "Display Name",
            api_name: "display_name_a",
            value: "Quality Check",
            input_type: "input",
            custom_setter,
          },
        ],
      },
    })
    component.show()
    await tick()

    await submit_form()

    await waitFor(() => expect(custom_setter).toHaveBeenCalledTimes(1))
    expect(fetch_mock).not.toHaveBeenCalled()
  })

  it("shows the error and skips after_save when the main PATCH fails after custom setters", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ message: "spec save failed" }), {
        status: 400,
      }),
    )
    const custom_setter = vi.fn().mockResolvedValue(undefined)
    const after_save = vi.fn()

    const { component, getAllByText } = render(EditDialog, {
      props: {
        name: "Thing",
        patch_url: "/api/thing",
        after_save,
        fields: [
          {
            label: "Name",
            api_name: "name",
            value: "new name",
            input_type: "input",
          },
          {
            label: "Display Name",
            api_name: "display_name_a",
            value: "Quality Check",
            input_type: "input",
            custom_setter,
          },
        ],
      },
    })
    component.show()
    await tick()

    await submit_form()

    await waitFor(() =>
      expect(getAllByText(/spec save failed/).length).toBeGreaterThan(0),
    )
    expect(custom_setter).toHaveBeenCalledTimes(1)
    expect(after_save).not.toHaveBeenCalled()
  })
})
