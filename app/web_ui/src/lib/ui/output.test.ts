// @vitest-environment jsdom
import { describe, it, expect, afterEach, beforeEach, vi } from "vitest"
import { render, cleanup, fireEvent } from "@testing-library/svelte"
import Output from "./output.svelte"
import OutputSlotHarness from "./output_slot_harness.test.svelte"

afterEach(() => cleanup())

// The surface Output draws when it prints its own text. Pinned so the slot
// branch added alongside it cannot change what every existing caller renders.
describe("output — no slot", () => {
  it("prints raw_output in its own pre, inside the panel", () => {
    const { container } = render(Output, {
      props: { raw_output: "hello world" },
    })

    const pre = container.querySelector("pre")
    expect(pre).not.toBeNull()
    expect(pre!.textContent).toBe("hello world")
    // The pre is the growing child of the panel, and the panel paints base-200.
    expect(pre!.className).toContain("grow")
    expect(pre!.className).toContain("text-xs")
    expect(pre!.parentElement!.className).toContain("bg-base-200")
    // One copy button, beside the content.
    expect(container.querySelectorAll("button").length).toBe(1)
  })

  it("marks a cited span in the printed text", () => {
    const { container } = render(Output, {
      props: { raw_output: "abcdef", mark: { start: 2, end: 4 } },
    })

    const marked = container.querySelector("[data-highlight-target]")
    expect(marked!.textContent).toBe("cd")
  })
})

describe("output — slotted content", () => {
  it("renders the slot inside the same surface, and keeps the copy button", () => {
    const { container } = render(OutputSlotHarness, {
      props: { raw_output: "the plain text" },
    })

    // The slot replaces the printed text: no pre on this path.
    expect(container.querySelector("pre")).toBeNull()
    const slotted = container.querySelector("[data-slotted]")
    expect(slotted).not.toBeNull()
    expect(slotted!.textContent).toBe("rendered content")
    // Still inside Output's panel, and the copy button is still there.
    expect(slotted!.closest(".bg-base-200")).not.toBeNull()
    expect(container.querySelectorAll("button").length).toBe(1)
  })
})

describe("output — the slot inside the control's chrome", () => {
  it("folds long slotted content the way it folds long text", async () => {
    const { container } = render(OutputSlotHarness, {
      props: { raw_output: "the plain text", max_height: "40px" },
    })
    // The fold measures the slot the same way it measures the printed text:
    // the content element is the slotted wrapper, so a caller's own rendering
    // gets the Show All affordance rather than silently overflowing.
    const panel = container.querySelector("[style*='max-height']")
    expect(panel).not.toBeNull()
    expect(
      container
        .querySelector("[data-slotted]")!
        .closest("[style*='max-height']"),
    ).toBe(panel)
  })

  it("honours no_padding on the slot", () => {
    const padded = render(OutputSlotHarness, {
      props: { raw_output: "t" },
    })
    const padded_box =
      padded.container.querySelector("[data-slotted]")!.parentElement!
    expect(padded_box.className).toContain("p-3")
    cleanup()

    const bare = render(OutputSlotHarness, {
      props: { raw_output: "t", no_padding: true },
    })
    const bare_box =
      bare.container.querySelector("[data-slotted]")!.parentElement!
    expect(bare_box.className).not.toContain("p-3")
  })
})

describe("output — copy button", () => {
  const FEEDBACK_MS = 1500

  function set_clipboard(clipboard: Partial<Clipboard> | undefined) {
    Object.defineProperty(navigator, "clipboard", {
      value: clipboard,
      configurable: true,
    })
  }

  function render_output() {
    const result = render(Output, { props: { raw_output: "copy me" } })
    const button = result.getByRole("button", { name: "Copy" })
    const icon = () =>
      button.querySelector("[data-copy-icon]")!.getAttribute("data-copy-icon")
    const announcement = () =>
      result.container.querySelector("[aria-live='polite']")!.textContent
    return { ...result, button, icon, announcement }
  }

  beforeEach(() => {
    vi.useFakeTimers()
    vi.spyOn(console, "error").mockImplementation(() => {})
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
    set_clipboard(undefined)
  })

  it("has an accessible name and tooltip", () => {
    const { button, icon, announcement } = render_output()
    expect(button.getAttribute("aria-label")).toBe("Copy")
    expect(button.getAttribute("title")).toBe("Copy")
    expect(icon()).toBe("idle")
    expect(announcement()).toBe("")
  })

  it("copies raw_output and shows a green check, then reverts", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    set_clipboard({ writeText })
    const { button, icon, announcement } = render_output()

    await fireEvent.click(button)

    expect(writeText).toHaveBeenCalledWith("copy me")
    expect(icon()).toBe("copied")
    expect(button.className).toContain("text-success")
    expect(button.className).not.toContain("text-gray-400")
    expect(announcement()).toBe("Copied")

    await vi.advanceTimersByTimeAsync(FEEDBACK_MS)
    expect(icon()).toBe("idle")
    expect(button.className).toContain("text-gray-400")
    expect(announcement()).toBe("")
  })

  it("restarts the feedback timer on a repeated click", async () => {
    set_clipboard({ writeText: vi.fn().mockResolvedValue(undefined) })
    const { button, icon } = render_output()

    await fireEvent.click(button)
    await vi.advanceTimersByTimeAsync(FEEDBACK_MS - 500)
    await fireEvent.click(button)
    await vi.advanceTimersByTimeAsync(FEEDBACK_MS - 500)
    expect(icon()).toBe("copied")

    await vi.advanceTimersByTimeAsync(500)
    expect(icon()).toBe("idle")
  })

  it("shows a red X instead of crashing when the clipboard API is missing", async () => {
    set_clipboard(undefined)
    const { button, icon, announcement } = render_output()

    await fireEvent.click(button)

    expect(icon()).toBe("failed")
    expect(button.className).toContain("text-error")
    expect(announcement()).toBe("Copy failed")
    expect(console.error).toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(FEEDBACK_MS)
    expect(icon()).toBe("idle")
    expect(announcement()).toBe("")
  })

  it("shows a red X when writeText rejects", async () => {
    set_clipboard({
      writeText: vi.fn().mockRejectedValue(new Error("denied")),
    })
    const { button, icon, announcement } = render_output()

    await fireEvent.click(button)

    expect(icon()).toBe("failed")
    expect(button.className).toContain("text-error")
    expect(announcement()).toBe("Copy failed")
    expect(console.error).toHaveBeenCalled()
  })

  it("clears the feedback timer when destroyed", async () => {
    set_clipboard({ writeText: vi.fn().mockResolvedValue(undefined) })
    const { button, unmount } = render_output()

    await fireEvent.click(button)
    expect(vi.getTimerCount()).toBe(1)

    unmount()
    expect(vi.getTimerCount()).toBe(0)
  })

  it("does not start a feedback timer when the copy resolves after destroy", async () => {
    let resolve_write: () => void = () => {}
    set_clipboard({
      writeText: vi.fn(
        () => new Promise<void>((resolve) => (resolve_write = resolve)),
      ),
    })
    const { button, unmount } = render_output()

    await fireEvent.click(button)
    unmount()
    resolve_write()
    await vi.advanceTimersByTimeAsync(0)
    expect(vi.getTimerCount()).toBe(0)
  })
})
