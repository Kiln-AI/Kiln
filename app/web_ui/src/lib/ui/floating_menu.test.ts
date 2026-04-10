// @vitest-environment jsdom
import { describe, it, expect, vi } from "vitest"
import { render, fireEvent } from "@testing-library/svelte"
import FloatingMenu from "./floating_menu.svelte"
import type { FloatingMenuItem } from "./floating_menu_types"

function renderMenu(items: FloatingMenuItem[], props = {}) {
  return render(FloatingMenu, {
    props: { items, ...props },
    // Provide a trigger slot via the default slot content approach isn't
    // straightforward in Svelte 4 testing-library. We'll test with items
    // and check the wrapper renders.
  })
}

describe("FloatingMenu component rendering", () => {
  it("renders nothing when all items are hidden", () => {
    const items: FloatingMenuItem[] = [
      { label: "A", onclick: () => {}, hidden: true },
      { label: "B", onclick: () => {}, hidden: true },
    ]
    const { container } = renderMenu(items)
    expect(container.querySelector(".relative")).toBeNull()
  })

  it("renders nothing when items array is empty", () => {
    const { container } = renderMenu([])
    expect(container.querySelector(".relative")).toBeNull()
  })

  it("renders the wrapper when there are visible items", () => {
    const items: FloatingMenuItem[] = [
      { label: "Edit", onclick: () => {} },
      { label: "Delete", onclick: () => {} },
    ]
    const { container } = renderMenu(items)
    expect(container.querySelector(".relative.inline-block")).not.toBeNull()
  })

  it("does not render menu items until trigger is clicked", () => {
    const items: FloatingMenuItem[] = [{ label: "Edit", onclick: () => {} }]
    const { container } = renderMenu(items)
    expect(container.querySelector("ul")).toBeNull()
  })

  it("renders menu items after trigger click", async () => {
    const items: FloatingMenuItem[] = [
      { label: "Edit", onclick: () => {} },
      { label: "Delete", onclick: () => {} },
    ]
    const { container } = renderMenu(items)
    const trigger = container.querySelector(
      ".relative.inline-block > div",
    ) as HTMLElement
    await fireEvent.click(trigger)
    const listItems = container.querySelectorAll("li")
    expect(listItems).toHaveLength(2)
  })

  it("excludes hidden items from the rendered menu", async () => {
    const items: FloatingMenuItem[] = [
      { label: "Edit", onclick: () => {} },
      { label: "Secret", onclick: () => {}, hidden: true },
      { label: "Delete", onclick: () => {} },
    ]
    const { container } = renderMenu(items)
    const trigger = container.querySelector(
      ".relative.inline-block > div",
    ) as HTMLElement
    await fireEvent.click(trigger)
    const listItems = container.querySelectorAll("li")
    expect(listItems).toHaveLength(2)
    expect(container.textContent).toContain("Edit")
    expect(container.textContent).not.toContain("Secret")
    expect(container.textContent).toContain("Delete")
  })

  it("renders href items as <a> tags", async () => {
    const items: FloatingMenuItem[] = [
      { label: "Link Item", href: "/some/path" },
    ]
    const { container } = renderMenu(items)
    const trigger = container.querySelector(
      ".relative.inline-block > div",
    ) as HTMLElement
    await fireEvent.click(trigger)
    const anchor = container.querySelector("a")
    expect(anchor).not.toBeNull()
    expect(anchor?.getAttribute("href")).toBe("/some/path")
    expect(anchor?.textContent?.trim()).toBe("Link Item")
    expect(container.querySelector("li button")).toBeNull()
  })

  it("renders onclick items as <button> tags", async () => {
    const items: FloatingMenuItem[] = [
      { label: "Action Item", onclick: () => {} },
    ]
    const { container } = renderMenu(items)
    const trigger = container.querySelector(
      ".relative.inline-block > div",
    ) as HTMLElement
    await fireEvent.click(trigger)
    const button = container.querySelector("li button")
    expect(button).not.toBeNull()
    expect(button?.textContent?.trim()).toBe("Action Item")
    expect(container.querySelector("a")).toBeNull()
  })

  it("calls onclick when a button item is clicked", async () => {
    const handler = vi.fn()
    const items: FloatingMenuItem[] = [{ label: "Do It", onclick: handler }]
    const { container } = renderMenu(items)
    const trigger = container.querySelector(
      ".relative.inline-block > div",
    ) as HTMLElement
    await fireEvent.click(trigger)
    const button = container.querySelector("li button") as HTMLElement
    await fireEvent.click(button)
    expect(handler).toHaveBeenCalledOnce()
  })

  it("calls onclick on href items when both href and onclick are provided", async () => {
    const handler = vi.fn()
    const items: FloatingMenuItem[] = [
      { label: "Both", href: "/path", onclick: handler },
    ]
    const { container } = renderMenu(items)
    const trigger = container.querySelector(
      ".relative.inline-block > div",
    ) as HTMLElement
    await fireEvent.click(trigger)
    const anchor = container.querySelector("a") as HTMLElement
    await fireEvent.click(anchor)
    expect(handler).toHaveBeenCalledOnce()
  })

  it("closes menu after clicking a button item", async () => {
    const items: FloatingMenuItem[] = [{ label: "Action", onclick: () => {} }]
    const { container } = renderMenu(items)
    const trigger = container.querySelector(
      ".relative.inline-block > div",
    ) as HTMLElement
    await fireEvent.click(trigger)
    expect(container.querySelector("ul")).not.toBeNull()
    const button = container.querySelector("li button") as HTMLElement
    await fireEvent.click(button)
    expect(container.querySelector("ul")).toBeNull()
  })

  it("toggles menu open and closed on trigger clicks", async () => {
    const items: FloatingMenuItem[] = [{ label: "Item", onclick: () => {} }]
    const { container } = renderMenu(items)
    const trigger = container.querySelector(
      ".relative.inline-block > div",
    ) as HTMLElement
    await fireEvent.click(trigger)
    expect(container.querySelector("ul")).not.toBeNull()
    await fireEvent.click(trigger)
    expect(container.querySelector("ul")).toBeNull()
  })
})
