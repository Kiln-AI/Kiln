// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest"
import { render, cleanup, fireEvent } from "@testing-library/svelte"
import ContextUsageGauge from "./context_usage_gauge.svelte"
import type { ContextUsage } from "$lib/chat/streaming_chat"

function usage(overrides: Partial<ContextUsage> = {}): ContextUsage {
  return {
    context_tokens: 50_000,
    context_limit: 150_000,
    context_percent: 0.33,
    compacted: false,
    ...overrides,
  }
}

afterEach(() => {
  cleanup()
})

describe("ContextUsageGauge", () => {
  it("renders nothing when usage is null", () => {
    const { queryByTestId } = render(ContextUsageGauge, {
      props: { usage: null },
    })
    expect(queryByTestId("context-usage-gauge")).toBeNull()
  })

  it("renders the rounded percent label", () => {
    const { getByTestId } = render(ContextUsageGauge, {
      props: { usage: usage({ context_percent: 0.336 }) },
    })
    expect(getByTestId("context-usage-percent").textContent?.trim()).toBe(
      "≈34%",
    )
  })

  it("clamps the displayed percent to 100 when over the limit", () => {
    const { getByTestId } = render(ContextUsageGauge, {
      props: { usage: usage({ context_percent: 1.2 }) },
    })
    expect(getByTestId("context-usage-percent").textContent?.trim()).toBe(
      "≈100%",
    )
  })

  it("renders a grey-on-grey two-div bar: subtle track + mid-grey fill", () => {
    const { getByTestId } = render(ContextUsageGauge, {
      props: { usage: usage() },
    })
    const track = getByTestId("context-usage-track")
    const fill = getByTestId("context-usage-fill")
    // Delicate low-opacity greys: very light track, slightly stronger but still
    // light fill — no color-ramp or near-black DaisyUI ``progress`` styling.
    expect(track.getAttribute("class") ?? "").toContain("bg-base-content/10")
    expect(fill.getAttribute("class") ?? "").toContain("bg-base-content/30")
    const allClasses = `${track.getAttribute("class")} ${fill.getAttribute("class")}`
    expect(allClasses).not.toMatch(/progress-(success|warning|error|primary)/)
  })

  it("fill width reflects the (clamped) percent", () => {
    const half = render(ContextUsageGauge, {
      props: { usage: usage({ context_percent: 0.5 }) },
    })
    expect(
      half.getByTestId("context-usage-fill").getAttribute("style"),
    ).toContain("width: 50%")
    cleanup()

    const over = render(ContextUsageGauge, {
      props: { usage: usage({ context_percent: 1.2 }) },
    })
    expect(
      over.getByTestId("context-usage-fill").getAttribute("style"),
    ).toContain("width: 100%")
  })

  it("stacks the percent label above the bar", () => {
    const { getByTestId } = render(ContextUsageGauge, {
      props: { usage: usage() },
    })
    const gauge = getByTestId("context-usage-gauge")
    const label = getByTestId("context-usage-percent")
    const track = getByTestId("context-usage-track")
    // Column layout, label rendered before (above) the bar in DOM order.
    expect(gauge.getAttribute("class") ?? "").toContain("flex-col")
    const order = Array.from(gauge.children)
    expect(order.indexOf(label)).toBeLessThan(order.indexOf(track))
  })

  it("never renders a condensed marker, even when compacted", () => {
    const { queryByTestId, container } = render(ContextUsageGauge, {
      props: { usage: usage({ compacted: true }) },
    })
    expect(queryByTestId("context-usage-condensed")).toBeNull()
    expect(container.textContent).not.toContain("condensed")
  })

  it("makes the trigger keyboard-focusable and shows the tooltip on focus", async () => {
    const { getByTestId, getByRole } = render(ContextUsageGauge, {
      props: { usage: usage() },
    })
    const gauge = getByTestId("context-usage-gauge")
    // The meter trigger must be reachable via keyboard.
    expect(gauge.getAttribute("tabindex")).toBe("0")

    // Hidden by default, revealed on focus (mirrors the mouseenter behavior).
    const tooltip = getByRole("tooltip", { hidden: true })
    expect(tooltip.getAttribute("class") ?? "").toContain("hidden")
    await fireEvent.focus(gauge)
    expect(tooltip.getAttribute("class") ?? "").not.toContain("hidden")
  })

  it("tooltip includes the locale-formatted token counts", () => {
    const { getByRole } = render(ContextUsageGauge, {
      props: {
        usage: usage({
          context_tokens: 93_000,
          context_limit: 150_000,
          context_percent: 0.62,
        }),
      },
    })
    const tooltip = getByRole("tooltip", { hidden: true })
    const text = tooltip.textContent ?? ""
    expect(text).toContain("≈ 62% of context used")
    expect(text).toContain(
      `${(93_000).toLocaleString()} / ${(150_000).toLocaleString()} tokens`,
    )
    expect(text).toContain("automatically summarized")
  })
})
