// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest"
import { render, fireEvent } from "@testing-library/svelte"
import { tick } from "svelte"
import { progress_ui_state } from "$lib/stores/progress_ui_store"
import type { ProgressUIState } from "$lib/stores/progress_ui_store"

vi.mock("$app/navigation", () => ({
  goto: vi.fn(),
}))

// ProgressWidget subscribes to $app/stores "page" which is only available in
// a live SvelteKit request context. Stub it for this test so we can verify
// sidebar_rail_progress's own conditional rendering.
vi.mock("$lib/ui/progress_widget.svelte", async () => {
  const StubModule = await import(
    "./__tests__/sidebar_rail_progress_widget_stub.svelte"
  )
  return { default: StubModule.default }
})

// Import the component under test after the mock is registered.
const SidebarRailProgress = (await import("./sidebar_rail_progress.svelte"))
  .default
const { computePercentComplete } = await import(
  "./sidebar_rail_progress.svelte"
)

function makeState(overrides: Partial<ProgressUIState> = {}): ProgressUIState {
  return {
    title: "Running",
    body: "Step 1 of 3",
    cta: null,
    link: "/",
    progress: 0.33,
    step_count: 3,
    current_step: 1,
    ...overrides,
  }
}

describe("SidebarRailProgress", () => {
  beforeEach(() => {
    progress_ui_state.set(null)
  })

  afterEach(() => {
    progress_ui_state.set(null)
  })

  it("renders nothing when progress_ui_state is null", () => {
    const { container } = render(SidebarRailProgress)
    expect(container.querySelector('[aria-label="In progress"]')).toBeNull()
    expect(container.querySelector('[aria-label="Progress"]')).toBeNull()
  })

  it("renders the trigger button with radial progress when progress_ui_state is set", () => {
    progress_ui_state.set(makeState())
    const { container } = render(SidebarRailProgress)
    const trigger = container.querySelector('[aria-label="In progress"]')
    expect(trigger).not.toBeNull()

    const radial = container.querySelector(".radial-progress") as HTMLElement
    expect(radial).not.toBeNull()
    expect(radial.style.getPropertyValue("--value").trim()).toBe("33")

    // Tooltip not mounted until hover/focus.
    expect(container.querySelector('[aria-label="Progress"]')).toBeNull()
  })

  it("shows the tooltip content on hover", async () => {
    progress_ui_state.set(makeState())
    const { container, findByTestId } = render(SidebarRailProgress)
    const trigger = container.querySelector(
      '[aria-label="In progress"]',
    ) as HTMLElement
    expect(trigger).not.toBeNull()
    const hoverRegion = trigger.parentElement as HTMLElement
    await fireEvent.mouseEnter(hoverRegion)
    const stub = await findByTestId("progress-widget-stub")
    expect(stub).not.toBeNull()
  })

  it("keeps the tooltip open during the grace period after leaving the hover region", async () => {
    vi.useFakeTimers()
    try {
      progress_ui_state.set(makeState())
      const { container } = render(SidebarRailProgress)
      const trigger = container.querySelector(
        '[aria-label="In progress"]',
      ) as HTMLElement
      const hoverRegion = trigger.parentElement as HTMLElement
      await fireEvent.mouseEnter(hoverRegion)
      const tooltipId = trigger.getAttribute("aria-describedby") as string
      expect(tooltipId).not.toBeNull()
      const tooltipWrapper = document.getElementById(tooltipId) as HTMLElement
      expect(tooltipWrapper).not.toBeNull()

      await fireEvent.mouseLeave(hoverRegion)

      // Tooltip still mounted during the grace period.
      expect(document.getElementById(tooltipId)).not.toBeNull()
      expect(trigger.getAttribute("aria-describedby")).toBe(tooltipId)
    } finally {
      vi.useRealTimers()
    }
  })

  it("keeps the tooltip open when the cursor moves from trigger onto the portaled tooltip", async () => {
    vi.useFakeTimers()
    try {
      progress_ui_state.set(makeState())
      const { container } = render(SidebarRailProgress)
      const trigger = container.querySelector(
        '[aria-label="In progress"]',
      ) as HTMLElement
      const hoverRegion = trigger.parentElement as HTMLElement
      await fireEvent.mouseEnter(hoverRegion)
      const tooltipId = trigger.getAttribute("aria-describedby") as string
      expect(tooltipId).not.toBeNull()

      // The Float portal moves the tooltip wrapper out of the trigger's
      // subtree, so hovering the trigger's wrapper and then leaving it
      // (mimicking the cursor transiting onto the floated tooltip) should
      // not dismiss the tooltip as long as the tooltip itself reports
      // being hovered.
      await fireEvent.mouseLeave(hoverRegion)
      const tooltipWrapper = document.getElementById(tooltipId) as HTMLElement
      expect(tooltipWrapper).not.toBeNull()
      await fireEvent.mouseEnter(tooltipWrapper)

      // Advance past the grace period; the tooltip should still be mounted
      // because hovering the tooltip itself keeps it alive.
      await vi.advanceTimersByTimeAsync(500)
      await tick()

      expect(document.getElementById(tooltipId)).not.toBeNull()
      expect(trigger.getAttribute("aria-describedby")).toBe(tooltipId)
    } finally {
      vi.useRealTimers()
    }
  })

  it("hides the tooltip after the grace period elapses", async () => {
    vi.useFakeTimers()
    try {
      progress_ui_state.set(makeState())
      const { container } = render(SidebarRailProgress)
      const trigger = container.querySelector(
        '[aria-label="In progress"]',
      ) as HTMLElement
      const hoverRegion = trigger.parentElement as HTMLElement
      await fireEvent.mouseEnter(hoverRegion)
      const tooltipId = trigger.getAttribute("aria-describedby") as string

      await fireEvent.mouseLeave(hoverRegion)

      // After the grace period elapses, the tooltip is gone.
      await vi.advanceTimersByTimeAsync(200)
      await tick()

      expect(document.getElementById(tooltipId)).toBeNull()
      expect(trigger.getAttribute("aria-describedby")).toBeNull()
    } finally {
      vi.useRealTimers()
    }
  })

  it("navigates to the link when the trigger button is clicked", async () => {
    const { goto } = await import("$app/navigation")
    const gotoMock = goto as unknown as ReturnType<typeof vi.fn>
    gotoMock.mockClear?.()
    progress_ui_state.set(makeState({ link: "/my-target" }))
    const { container } = render(SidebarRailProgress)
    const trigger = container.querySelector(
      '[aria-label="In progress"]',
    ) as HTMLElement
    await fireEvent.click(trigger)
    expect(gotoMock).toHaveBeenCalledWith("/my-target")
  })

  it("uses steps-based percent when progress is null", () => {
    progress_ui_state.set(
      makeState({
        body: "Step 2 of 4",
        progress: null,
        step_count: 4,
        current_step: 2,
      }),
    )
    const { container } = render(SidebarRailProgress)
    const radial = container.querySelector(".radial-progress") as HTMLElement
    expect(radial).not.toBeNull()
    expect(radial.style.getPropertyValue("--value").trim()).toBe("50")
  })
})

describe("computePercentComplete", () => {
  it("returns 0 when state is null", () => {
    expect(computePercentComplete(null)).toBe(0)
  })

  it("converts fractional progress to a rounded percent", () => {
    expect(computePercentComplete(makeState({ progress: 0.33 }))).toBe(33)
  })

  it("clamps progress above 1 to 100", () => {
    expect(computePercentComplete(makeState({ progress: 1.5 }))).toBe(100)
  })

  it("clamps negative progress to 0", () => {
    expect(computePercentComplete(makeState({ progress: -0.1 }))).toBe(0)
  })

  it("falls back to step progress when progress is null", () => {
    expect(
      computePercentComplete(
        makeState({ progress: null, step_count: 4, current_step: 2 }),
      ),
    ).toBe(50)
  })

  it("returns 0 when step_count is 0", () => {
    expect(
      computePercentComplete(
        makeState({ progress: null, step_count: 0, current_step: 0 }),
      ),
    ).toBe(0)
  })

  it("returns 0 when both progress and step fields are null", () => {
    expect(
      computePercentComplete(
        makeState({ progress: null, step_count: null, current_step: null }),
      ),
    ).toBe(0)
  })
})
