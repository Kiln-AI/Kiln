// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from "vitest"
import { render, cleanup } from "@testing-library/svelte"
import { readable } from "svelte/store"

// The real jobs_store opens an EventSource on subscribe; mock it with plain
// stores so the indicator can render in isolation. The component takes
// active_count / total_count overrides for the actual assertions below.
vi.mock("$lib/stores/jobs_store", () => ({
  active_jobs_count: readable(0),
  jobs: readable([]),
}))

const SidebarJobsIndicator = (await import("./SidebarJobsIndicator.svelte"))
  .default

describe("SidebarJobsIndicator", () => {
  afterEach(() => {
    cleanup()
  })

  it("shows a spinner and active count when jobs are active", () => {
    const { container, getByText } = render(SidebarJobsIndicator, {
      props: { active_count: 3, total_count: 5 },
    })
    expect(getByText("3")).not.toBeNull()
    expect(container.querySelector(".loading-spinner")).not.toBeNull()
  })

  it("shows a static muted count without a spinner when none are active", () => {
    const { container, getByText } = render(SidebarJobsIndicator, {
      props: { active_count: 0, total_count: 4 },
    })
    expect(getByText("4")).not.toBeNull()
    expect(container.querySelector(".loading-spinner")).toBeNull()
  })

  it("renders nothing when there are no jobs", () => {
    const { container } = render(SidebarJobsIndicator, {
      props: { active_count: 0, total_count: 0 },
    })
    expect(container.textContent?.trim()).toBe("")
  })

  it("caps the displayed count at 99+", () => {
    const { getByText } = render(SidebarJobsIndicator, {
      props: { active_count: 150, total_count: 150 },
    })
    expect(getByText("99+")).not.toBeNull()
  })

  it("uses the rail variant styling when requested", () => {
    const { container } = render(SidebarJobsIndicator, {
      props: { active_count: 2, total_count: 2, variant: "rail" },
    })
    const span = container.querySelector("span")
    expect(span?.className).toContain("absolute")
  })
})
