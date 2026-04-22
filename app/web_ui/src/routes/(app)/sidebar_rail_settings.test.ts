// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach } from "vitest"
import { render, fireEvent, waitFor, cleanup } from "@testing-library/svelte"
import SidebarRailSettings from "./sidebar_rail_settings.svelte"
import { update_info, default_update_state } from "$lib/utils/update"

// Tooltip is portaled to document.body via <Float portal>, not inside the
// render container. Clean up portaled nodes between tests to avoid leaks.
afterEach(() => {
  cleanup()
  document.body
    .querySelectorAll('[data-testid="rail-tooltip"]')
    .forEach((el) => el.remove())
})

function findTooltip(): HTMLElement | null {
  return document.body.querySelector('[data-testid="rail-tooltip"]')
}

describe("SidebarRailSettings", () => {
  beforeEach(() => {
    update_info.set(default_update_state)
  })

  it("renders the update dot when an update is available", () => {
    update_info.set({
      update_result: {
        has_update: true,
        latest_version: "1.0.0",
        link: "https://example.com",
      },
      update_loading: false,
      update_error: null,
    })
    const { container } = render(SidebarRailSettings, {
      props: { active: false },
    })
    expect(container.querySelector('[data-testid="update-dot"]')).not.toBeNull()
  })

  it("does not render the update dot when no update is available", () => {
    update_info.set(default_update_state)
    const { container } = render(SidebarRailSettings, {
      props: { active: false },
    })
    expect(container.querySelector('[data-testid="update-dot"]')).toBeNull()
  })

  it("sets the update-available aria-label when an update is available", () => {
    update_info.set({
      update_result: {
        has_update: true,
        latest_version: "1.0.0",
        link: "https://example.com",
      },
      update_loading: false,
      update_error: null,
    })
    const { container } = render(SidebarRailSettings, {
      props: { active: false },
    })
    const anchor = container.querySelector("a")
    expect(anchor?.getAttribute("aria-label")).toBe(
      "Settings, update available",
    )
  })

  it("shows the update-available tooltip on hover when an update is available", async () => {
    update_info.set({
      update_result: {
        has_update: true,
        latest_version: "1.0.0",
        link: "https://example.com",
      },
      update_loading: false,
      update_error: null,
    })
    const { container } = render(SidebarRailSettings, {
      props: { active: false },
    })
    const anchor = container.querySelector("a") as HTMLElement
    await fireEvent.mouseEnter(anchor)
    await waitFor(() => expect(findTooltip()).not.toBeNull())
    expect(findTooltip()?.textContent?.trim()).toBe(
      "Settings — Update Available",
    )
  })

  it("shows the plain Settings tooltip on hover when no update is available", async () => {
    update_info.set(default_update_state)
    const { container } = render(SidebarRailSettings, {
      props: { active: false },
    })
    const anchor = container.querySelector("a") as HTMLElement
    await fireEvent.mouseEnter(anchor)
    await waitFor(() => expect(findTooltip()).not.toBeNull())
    expect(findTooltip()?.textContent?.trim()).toBe("Settings")
  })

  it("uses the plain aria-label when no update is available", () => {
    update_info.set(default_update_state)
    const { container } = render(SidebarRailSettings, {
      props: { active: false },
    })
    const anchor = container.querySelector("a")
    expect(anchor?.getAttribute("aria-label")).toBe("Settings")
  })

  it("applies aria-current='page' when active", () => {
    const { container } = render(SidebarRailSettings, {
      props: { active: true },
    })
    const anchor = container.querySelector("a")
    expect(anchor?.getAttribute("aria-current")).toBe("page")
    expect(anchor?.className).toContain("bg-base-300")
  })
})
