// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest"
import { render, cleanup, fireEvent } from "@testing-library/svelte"
import DropsRefineScreen from "./drops_refine_screen.svelte"

afterEach(() => cleanup())

function setup(dropped: number, planned: number) {
  const on_refine_plan = vi.fn()
  const { container } = render(DropsRefineScreen, {
    props: { dropped, planned, noun: "conversation", on_refine_plan },
  })
  return { container, on_refine_plan }
}

describe("DropsRefineScreen", () => {
  it("says none of the plan fit when every item dropped", () => {
    const { container } = setup(8, 8)
    expect(container.textContent).toContain("None of the Plan Fit")
    expect(container.textContent).toContain(
      "None of the 8 planned conversations fit your OpenEnv server.",
    )
  })

  it("says most of the plan didn't fit when some items are left", () => {
    const { container } = setup(5, 8)
    expect(container.textContent).toContain("Most of the Plan Didn't Fit")
    expect(container.textContent).not.toContain("Align the Judge")
  })

  it("offers Refine Plan as its only action", async () => {
    const { container, on_refine_plan } = setup(8, 8)
    const buttons = Array.from(container.querySelectorAll("button"))
    expect(buttons.map((b) => b.textContent?.trim())).toEqual(["Refine Plan"])
    await fireEvent.click(buttons[0])
    expect(on_refine_plan).toHaveBeenCalledOnce()
  })
})
