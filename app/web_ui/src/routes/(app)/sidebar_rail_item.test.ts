// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest"
import { render, fireEvent, waitFor, cleanup } from "@testing-library/svelte"
import SidebarRailItem from "./sidebar_rail_item.svelte"

// The shared sidebar_rail_tooltip uses <Float portal> which re-parents the
// tooltip to document.body on mount. Query from document.body rather than
// `container` so the assertions are robust to portaling. Also explicitly
// clean up between tests so portaled nodes from a prior test don't leak.
afterEach(() => {
  cleanup()
  document.body
    .querySelectorAll('[data-testid="rail-tooltip"]')
    .forEach((el) => el.remove())
})

function findTooltip(): HTMLElement | null {
  return document.body.querySelector('[data-testid="rail-tooltip"]')
}

describe("SidebarRailItem", () => {
  it("renders an anchor with the given href and aria-label", () => {
    const { container } = render(SidebarRailItem, {
      props: { href: "/run", label: "Run" },
    })
    const anchor = container.querySelector("a")
    expect(anchor).not.toBeNull()
    expect(anchor?.getAttribute("href")).toBe("/run")
    expect(anchor?.getAttribute("aria-label")).toBe("Run")
  })

  it("renders a tooltip on hover with the label text", async () => {
    const { container } = render(SidebarRailItem, {
      props: { href: "/chat", label: "Chat" },
    })
    const anchor = container.querySelector("a") as HTMLElement
    // No tooltip before hover.
    expect(findTooltip()).toBeNull()
    await fireEvent.mouseEnter(anchor)
    await waitFor(() => expect(findTooltip()).not.toBeNull())
    expect(findTooltip()?.textContent?.trim()).toBe("Chat")
  })

  it("hides the tooltip on mouse leave", async () => {
    const { container } = render(SidebarRailItem, {
      props: { href: "/chat", label: "Chat" },
    })
    const anchor = container.querySelector("a") as HTMLElement
    await fireEvent.mouseEnter(anchor)
    await waitFor(() => expect(findTooltip()).not.toBeNull())
    await fireEvent.mouseLeave(anchor)
    await waitFor(() => expect(findTooltip()).toBeNull())
  })

  it("marks the link aria-current='page' when active", () => {
    const { container } = render(SidebarRailItem, {
      props: { href: "/run", label: "Run", active: true },
    })
    const anchor = container.querySelector("a")
    expect(anchor?.getAttribute("aria-current")).toBe("page")
    expect(anchor?.className).toContain("bg-base-300")
  })

  it("has no aria-current when not active and uses the hover background", () => {
    const { container } = render(SidebarRailItem, {
      props: { href: "/run", label: "Run", active: false },
    })
    const anchor = container.querySelector("a")
    expect(anchor?.getAttribute("aria-current")).toBeNull()
    expect(anchor?.className).toContain("hover:bg-base-300/50")
  })

  it("keeps the visible tooltip pointer-events-none so clicks do not regress", async () => {
    // Regression guard: pre-portal the tooltip is a DOM descendant of the <a>,
    // so it must remain non-interactive or it could swallow clicks on the link.
    const { container } = render(SidebarRailItem, {
      props: { href: "/chat", label: "Chat" },
    })
    const anchor = container.querySelector("a") as HTMLElement
    await fireEvent.mouseEnter(anchor)
    await waitFor(() => expect(findTooltip()).not.toBeNull())
    const tooltip = findTooltip() as HTMLElement
    expect(tooltip.className).toContain("pointer-events-none")
  })
})
