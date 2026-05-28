// @vitest-environment jsdom
import { describe, it, expect, vi } from "vitest"
import { render } from "@testing-library/svelte"
import { writable } from "svelte/store"

vi.mock("$lib/api_client", () => ({
  base_url: "http://localhost:8757",
  client: {},
}))

vi.mock("$lib/stores", () => ({
  ui_state: writable({ current_project_id: null }),
}))

const SidebarJobsBadge = (await import("./SidebarJobsBadge.svelte")).default

describe("SidebarJobsBadge", () => {
  it("renders the count when greater than zero", () => {
    const { getByText } = render(SidebarJobsBadge, { props: { count: 3 } })
    expect(getByText("3")).not.toBeNull()
  })

  it("renders nothing when count is zero", () => {
    const { container } = render(SidebarJobsBadge, { props: { count: 0 } })
    expect(container.textContent?.trim()).toBe("")
  })

  it("caps the displayed count at 99+", () => {
    const { getByText } = render(SidebarJobsBadge, { props: { count: 150 } })
    expect(getByText("99+")).not.toBeNull()
  })

  it("uses the rail variant styling when requested", () => {
    const { container } = render(SidebarJobsBadge, {
      props: { count: 2, variant: "rail" },
    })
    const span = container.querySelector("span")
    expect(span?.className).toContain("absolute")
  })
})
