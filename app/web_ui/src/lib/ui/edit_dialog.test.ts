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
            label: "Score Name",
            api_name: "output_score_name_0",
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
    expect(custom_setter).toHaveBeenCalledWith("Quality Check")

    expect(fetch_mock).toHaveBeenCalledTimes(1)
    const [, init] = fetch_mock.mock.calls[0]
    const body = JSON.parse((init?.body as string) ?? "{}")
    expect(body).toEqual({ name: "new name" })
  })

  it("invokes a shared custom_setter only once across multiple fields", async () => {
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
            api_name: "output_score_name_0",
            value: "A",
            input_type: "input",
            custom_setter,
          },
          {
            label: "Score 1",
            api_name: "output_score_name_1",
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
    expect(fetch_mock).not.toHaveBeenCalled()
  })

  it("does not call after_save when a custom_setter rejects (dialog stays open)", async () => {
    const fetch_mock = vi
      .spyOn(global, "fetch")
      .mockResolvedValue(new Response(JSON.stringify({}), { status: 200 }))
    const custom_setter = vi
      .fn()
      .mockRejectedValue(new Error("migration failed"))
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
            label: "Score Name",
            api_name: "output_score_name_0",
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

    // The main PATCH ran, the setter was attempted and rejected
    await waitFor(() => expect(custom_setter).toHaveBeenCalledTimes(1))
    expect(fetch_mock).toHaveBeenCalledTimes(1)
    // after_save is never called, so the dialog is not dismissed; the error is shown
    expect(after_save).not.toHaveBeenCalled()
    await waitFor(() =>
      expect(getAllByText(/migration failed/).length).toBeGreaterThan(0),
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
            label: "Score Name",
            api_name: "output_score_name_0",
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
})
