// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest"
import { render, cleanup } from "@testing-library/svelte"
import CalloutCardDefault from "./__tests__/callout_card_default.svelte"
import CalloutCardWithIcon from "./__tests__/callout_card_with_icon.svelte"

afterEach(cleanup)

describe("CalloutCard component", () => {
  it("renders slot content inside the card", () => {
    const { container } = render(CalloutCardDefault)
    const slot = container.querySelector('[data-testid="slot-content"]')
    expect(slot).not.toBeNull()
    expect(slot!.textContent).toBe("Hello from slot")
  })

  it("applies the primary-tinted callout styling", () => {
    const { container } = render(CalloutCardDefault)
    const card = container.querySelector(".card")
    expect(card).not.toBeNull()
    expect(card!.classList.contains("card-bordered")).toBe(true)
    expect(card!.className).toContain("border-primary/30")
    expect(card!.className).toContain("bg-primary/5")
    expect(card!.className).toContain("shadow-sm")
  })

  it("does not render icon bubble when no icon slot is provided", () => {
    const { container } = render(CalloutCardDefault)
    const bubble = container.querySelector(".rounded-full")
    expect(bubble).toBeNull()
  })

  it("renders icon bubble when icon slot is provided", () => {
    const { container } = render(CalloutCardWithIcon)
    const bubble = container.querySelector(".rounded-full")
    expect(bubble).not.toBeNull()
    expect(bubble!.className).toContain("bg-primary/10")
    expect(bubble!.className).toContain("text-primary")
    const svg = container.querySelector('[data-testid="icon-svg"]')
    expect(svg).not.toBeNull()
  })

  it("renders slot content alongside the icon", () => {
    const { container } = render(CalloutCardWithIcon)
    const slot = container.querySelector('[data-testid="slot-content"]')
    expect(slot).not.toBeNull()
    expect(slot!.textContent).toBe("Content with icon")
  })

  it("passes testid prop to the card element", () => {
    const { container } = render(CalloutCardDefault, {
      props: { testid: "my-callout" },
    })
    const card = container.querySelector('[data-testid="my-callout"]')
    expect(card).not.toBeNull()
    expect(card!.classList.contains("card")).toBe(true)
  })

  it("does not set data-testid when testid prop is null", () => {
    const { container } = render(CalloutCardDefault)
    const card = container.querySelector(".card")
    expect(card).not.toBeNull()
    expect(card!.getAttribute("data-testid")).toBeNull()
  })
})
