// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest"
import { cleanup, fireEvent, render } from "@testing-library/svelte"
import DroppedCasesScreen from "./dropped_cases_screen.svelte"

afterEach(() => cleanup())

const DROPS = [
  {
    scenario_index: 0,
    scenario: "Refund a shipped order",
    drop_detail: "No order has shipped.",
  },
  {
    scenario_index: 1,
    scenario: "Close an account",
    drop_detail: "Accounts can't be closed.",
  },
]

function render_screen(
  total: number,
  drops = DROPS,
  error: string | null = null,
) {
  const handlers = {
    on_cancel: vi.fn(),
    on_retry: vi.fn(),
    on_replace: vi.fn(),
    on_continue: vi.fn(),
  }
  const result = render(DroppedCasesScreen, {
    props: { drops, total, error, ...handlers },
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
  it("says how many cases were dropped, under the title", () => {
    const { getByText } = render_screen(20)
    expect(getByText("Some Cases Were Dropped")).toBeTruthy()
    expect(
      getByText(
        "Kiln checked each case against your OpenEnv server. 2 of 20 were dropped. Each row says why.",
      ),
    ).toBeTruthy()
  })

  it("counts a single dropped case in the singular", () => {
    const { getByText } = render_screen(20, DROPS.slice(0, 1))
    expect(getByText("Some Cases Were Dropped")).toBeTruthy()
    expect(
      getByText(
        "Kiln checked each case against your OpenEnv server. 1 of 20 was dropped. Each row says why.",
      ),
    ).toBeTruthy()
  })

  it("says the only case was dropped when there was one", () => {
    const { getByText } = render_screen(1, DROPS.slice(0, 1))
    expect(getByText("All Cases Were Dropped")).toBeTruthy()
    expect(
      getByText(
        "Kiln checked each case against your OpenEnv server. The case was dropped. Each row says why.",
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

  it("offers Cancel, Retry, Replace Dropped Cases and Continue With the cases that fit, primary last", async () => {
    const { buttons, handlers } = render_screen(20)
    expect(buttons.map((b) => squash(b.textContent))).toEqual([
      "Cancel",
      "Retry",
      "Replace Dropped Cases",
      "Continue With 18",
    ])
    expect(buttons.map((b) => b.classList.contains("btn-primary"))).toEqual([
      false,
      false,
      false,
      true,
    ])
    for (const button of buttons) await fireEvent.click(button)
    expect(handlers.on_cancel).toHaveBeenCalledOnce()
    expect(handlers.on_retry).toHaveBeenCalledOnce()
    expect(handlers.on_replace).toHaveBeenCalledOnce()
    expect(handlers.on_continue).toHaveBeenCalledOnce()
  })

  it("drops Continue and Replace and leads with Retry when every case dropped", () => {
    const { buttons, getByText } = render_screen(2)
    expect(getByText("All Cases Were Dropped")).toBeTruthy()
    expect(
      getByText(
        "Kiln checked each case against your OpenEnv server. All 2 cases were dropped. Each row says why.",
      ),
    ).toBeTruthy()
    expect(buttons.map((b) => squash(b.textContent))).toEqual([
      "Cancel",
      "Retry",
    ])
    expect(buttons[1].classList.contains("btn-primary")).toBe(true)
  })

  it("shows why the last Replace stopped, only when it failed", () => {
    expect(render_screen(20).container.querySelector(".text-error")).toBeNull()
    cleanup()
    const { getByText } = render_screen(20, DROPS, "Server unreachable.")
    expect(getByText("Server unreachable.")).toBeTruthy()
  })
})
