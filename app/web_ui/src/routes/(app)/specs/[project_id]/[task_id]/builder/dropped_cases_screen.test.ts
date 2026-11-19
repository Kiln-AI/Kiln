// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest"
import { cleanup, fireEvent, render } from "@testing-library/svelte"
import DroppedCasesScreen from "./dropped_cases_screen.svelte"

afterEach(() => cleanup())

const DROPS = [
  { scenario: "Refund a shipped order", drop_detail: "No order has shipped." },
  { scenario: "Close an account", drop_detail: "Accounts can't be closed." },
]

function render_screen(total: number, drops = DROPS) {
  const handlers = {
    on_cancel: vi.fn(),
    on_retry: vi.fn(),
    on_continue: vi.fn(),
  }
  const result = render(DroppedCasesScreen, {
    props: { drops, total, ...handlers },
  })
  // The screen's own buttons, not the See all dialog's Close.
  const buttons = [
    ...result.container.querySelectorAll<HTMLButtonElement>("button.btn"),
  ].filter((b) => !b.closest("dialog"))
  return { ...result, handlers, buttons }
}

function squash(text: string | null | undefined): string {
  return (text ?? "").replace(/\s+/g, " ").trim()
}

describe("DroppedCasesScreen", () => {
  it("says how many cases didn't fit, under the title", () => {
    const { getByText } = render_screen(20)
    expect(getByText("Some Cases Don't Fit Your Environment")).toBeTruthy()
    expect(
      getByText(
        "Kiln checked each case against your OpenEnv server. 2 of 20 couldn't be made to fit.",
      ),
    ).toBeTruthy()
  })

  it("lists each dropped case with its reason", () => {
    const { container } = render_screen(20)
    const rows = [...container.querySelectorAll("[data-dropped-case]")]
    expect(rows).toHaveLength(2)
    expect(squash(rows[0].textContent)).toContain("Refund a shipped order")
    expect(squash(rows[0].textContent)).toContain("No order has shipped.")
    expect(squash(rows[1].textContent)).toContain("Accounts can't be closed.")
  })

  it("offers Cancel, Retry and Continue With the cases that fit, primary last", async () => {
    const { buttons, handlers } = render_screen(20)
    expect(buttons.map((b) => squash(b.textContent))).toEqual([
      "Cancel",
      "Retry",
      "Continue With 18",
    ])
    expect(buttons.map((b) => b.classList.contains("btn-primary"))).toEqual([
      false,
      false,
      true,
    ])
    await fireEvent.click(buttons[0])
    await fireEvent.click(buttons[1])
    await fireEvent.click(buttons[2])
    expect(handlers.on_cancel).toHaveBeenCalledOnce()
    expect(handlers.on_retry).toHaveBeenCalledOnce()
    expect(handlers.on_continue).toHaveBeenCalledOnce()
  })

  it("drops Continue and leads with Retry when nothing fits", () => {
    const { buttons, getByText } = render_screen(2)
    expect(
      getByText(
        "Kiln checked each case against your OpenEnv server. None of the 2 cases could be made to fit.",
      ),
    ).toBeTruthy()
    expect(buttons.map((b) => squash(b.textContent))).toEqual([
      "Cancel",
      "Retry",
    ])
    expect(buttons[1].classList.contains("btn-primary")).toBe(true)
  })
})
