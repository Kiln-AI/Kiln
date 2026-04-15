// @vitest-environment jsdom
import { describe, it, expect } from "vitest"
import { render, fireEvent } from "@testing-library/svelte"
import SidebarRailItem from "./sidebar_rail_item.svelte"

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

  it("sets data-tip to the label", () => {
    const { container } = render(SidebarRailItem, {
      props: { href: "/chat", label: "Chat" },
    })
    const anchor = container.querySelector("a")
    expect(anchor?.getAttribute("data-tip")).toBe("Chat")
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
})
