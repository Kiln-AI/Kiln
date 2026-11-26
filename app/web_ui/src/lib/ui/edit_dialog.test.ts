// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from "vitest"
import { render, cleanup } from "@testing-library/svelte"
import EditDialog from "./edit_dialog.svelte"

afterEach(() => cleanup())

describe("edit_dialog", () => {
  it("passes on its dialog's close event", () => {
    const { container, component } = render(EditDialog, {
      props: {
        name: "OpenEnv",
        patch_url: "/api/projects/p1/openenv_servers/e1",
        fields: [
          {
            label: "Name",
            api_name: "name",
            value: "Acme",
            input_type: "input",
          },
        ],
      },
    })
    const on_close = vi.fn()
    component.$on("close", on_close)
    container.querySelector("dialog")!.dispatchEvent(new Event("close"))
    expect(on_close).toHaveBeenCalledOnce()
  })
})
