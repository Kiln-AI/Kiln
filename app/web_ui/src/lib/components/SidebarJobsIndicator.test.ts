// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from "vitest"
import { render, cleanup } from "@testing-library/svelte"
import { readable } from "svelte/store"

// The real jobs_store opens an EventSource on subscribe; mock it with plain
// stores so the indicator can render in isolation. The component takes
// running_count / active_count / total_count overrides for the actual
// assertions below.
vi.mock("$lib/stores/jobs_store", () => ({
  running_jobs_count: readable(0),
  active_jobs_count: readable(0),
  jobs: readable([]),
}))

const SidebarJobsIndicator = (await import("./SidebarJobsIndicator.svelte"))
  .default

describe("SidebarJobsIndicator", () => {
  afterEach(() => {
    cleanup()
  })

  it("shows a spinner and active count when at least one job is running", () => {
    const { container, getByText } = render(SidebarJobsIndicator, {
      props: { running_count: 1, active_count: 3, total_count: 5 },
    })
    expect(getByText("3")).not.toBeNull()
    expect(container.querySelector(".loading-spinner")).not.toBeNull()
  })

  it("does NOT spin when only paused/pending jobs exist (no running)", () => {
    const { container, getByText } = render(SidebarJobsIndicator, {
      props: { running_count: 0, active_count: 2, total_count: 2 },
    })
    expect(getByText("2")).not.toBeNull()
    expect(container.querySelector(".loading-spinner")).toBeNull()
  })

  it("shows a static count without a spinner when no jobs are running", () => {
    const { container, getByText } = render(SidebarJobsIndicator, {
      props: { running_count: 0, active_count: 0, total_count: 4 },
    })
    expect(getByText("4")).not.toBeNull()
    expect(container.querySelector(".loading-spinner")).toBeNull()
  })

  it("renders nothing when there are no jobs", () => {
    const { container } = render(SidebarJobsIndicator, {
      props: { running_count: 0, active_count: 0, total_count: 0 },
    })
    expect(container.textContent?.trim()).toBe("")
  })

  it("caps the displayed count at 99+", () => {
    const { getByText } = render(SidebarJobsIndicator, {
      props: { running_count: 10, active_count: 150, total_count: 150 },
    })
    expect(getByText("99+")).not.toBeNull()
  })

  it("uses the rail variant styling when requested", () => {
    const { container } = render(SidebarJobsIndicator, {
      props: {
        running_count: 1,
        active_count: 2,
        total_count: 2,
        variant: "rail",
      },
    })
    const span = container.querySelector("span")
    expect(span?.className).toContain("absolute")
  })

  it("static rail badge uses a non-muted neutral style", () => {
    const { container } = render(SidebarJobsIndicator, {
      props: {
        running_count: 0,
        active_count: 0,
        total_count: 3,
        variant: "rail",
      },
    })
    const span = container.querySelector("span")
    expect(span?.className).toContain("bg-neutral")
    expect(span?.className).not.toContain("text-base-content/70")
  })
})
