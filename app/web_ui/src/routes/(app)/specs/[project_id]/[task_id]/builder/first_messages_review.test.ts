// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest"
import { cleanup, fireEvent, render } from "@testing-library/svelte"
import FirstMessagesReview from "./first_messages_review.svelte"

afterEach(() => cleanup())

describe("FirstMessagesReview", () => {
  it("lists every first message and hands Continue and Refine to the page", async () => {
    const on_continue = vi.fn()
    const on_refine = vi.fn()
    const cases = Array.from({ length: 30 }, (_, i) => ({
      seed_prompt: `Message ${i}\nsecond line`,
      scenario_index: i,
    }))
    const { container } = render(FirstMessagesReview, {
      props: { cases, on_continue, on_refine },
    })
    const items = container.querySelectorAll("[data-first-messages] li")
    expect(items.length).toBe(30)
    expect(items[0].textContent).toContain("Plan row 1")
    expect(items[29].textContent).toContain("Message 29")
    expect(container.textContent).toContain("Nothing has been set up")
    // The list scrolls rather than pushing the buttons off screen.
    expect(
      container.querySelector(".overflow-y-auto [data-first-messages]"),
    ).not.toBeNull()

    await fireEvent.click(
      container.querySelector("[data-first-messages-refine]") as Element,
    )
    expect(on_refine).toHaveBeenCalledTimes(1)
    expect(on_continue).not.toHaveBeenCalled()
    await fireEvent.click(
      container.querySelector("[data-first-messages-continue]") as Element,
    )
    expect(on_continue).toHaveBeenCalledTimes(1)
  })
})
