// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest"
import { cleanup, fireEvent, render } from "@testing-library/svelte"
import PilotStop from "./pilot_stop.svelte"

afterEach(() => cleanup())

describe("PilotStop", () => {
  it("says what ran and hands Continue and Refine Plan to the page", async () => {
    const on_continue = vi.fn()
    const on_refine_plan = vi.fn()
    const { container } = render(PilotStop, {
      props: { ran: 12, rest: 54, on_continue, on_refine_plan },
    })
    const text = (container.textContent ?? "").replace(/\s+/g, " ")
    expect(text).toContain("Pilot: 12 conversations ran, spread over the plan.")
    expect(text).toContain("runs the other 54 and keeps these results")
    expect(text).not.toMatch(/\$/)
    await fireEvent.click(
      container.querySelector("[data-pilot-refine]") as Element,
    )
    expect(on_refine_plan).toHaveBeenCalledTimes(1)
    await fireEvent.click(
      container.querySelector("[data-pilot-continue]") as Element,
    )
    expect(on_continue).toHaveBeenCalledTimes(1)
  })
})
