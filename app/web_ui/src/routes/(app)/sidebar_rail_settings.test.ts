// @vitest-environment jsdom
import { describe, it, expect } from "vitest"
import { render, fireEvent } from "@testing-library/svelte"
import SidebarRailSettings from "./sidebar_rail_settings.svelte"

describe("SidebarRailSettings", () => {
  it("renders the update dot when hasUpdate is true", () => {
    const { container } = render(SidebarRailSettings, {
      props: { active: false, hasUpdate: true },
    })
    expect(container.querySelector('[data-testid="update-dot"]')).not.toBeNull()
  })

  it("does not render the update dot when hasUpdate is false", () => {
    const { container } = render(SidebarRailSettings, {
      props: { active: false, hasUpdate: false },
    })
    expect(container.querySelector('[data-testid="update-dot"]')).toBeNull()
  })

  it("sets the update-available tooltip and aria-label when hasUpdate is true", () => {
    const { container } = render(SidebarRailSettings, {
      props: { active: false, hasUpdate: true },
    })
    const anchor = container.querySelector("a")
    expect(anchor?.getAttribute("data-tip")).toBe("Settings — Update Available")
    expect(anchor?.getAttribute("aria-label")).toBe(
      "Settings, update available",
    )
  })

  it("sets the plain Settings tooltip when hasUpdate is false", () => {
    const { container } = render(SidebarRailSettings, {
      props: { active: false, hasUpdate: false },
    })
    const anchor = container.querySelector("a")
    expect(anchor?.getAttribute("data-tip")).toBe("Settings")
    expect(anchor?.getAttribute("aria-label")).toBe("Settings")
  })

  it("applies aria-current='page' when active", () => {
    const { container } = render(SidebarRailSettings, {
      props: { active: true, hasUpdate: false },
    })
    const anchor = container.querySelector("a")
    expect(anchor?.getAttribute("aria-current")).toBe("page")
    expect(anchor?.className).toContain("bg-base-300")
  })
})
