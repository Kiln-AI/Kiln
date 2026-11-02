// @vitest-environment jsdom
import { describe, it, expect, vi } from "vitest"
import { render, fireEvent, waitFor } from "@testing-library/svelte"
import type { Trace } from "$lib/types"

vi.mock("$lib/ui/dialog.svelte", async () => {
  const StubModule = await import("./__tests__/dialog_stub.svelte")
  return { default: StubModule.default }
})

const JudgeTraceLink = (await import("./judge_trace_link.svelte")).default

const TRACE: Trace = [
  { role: "system", content: "Score the output." },
  { role: "user", content: "Rendered judge prompt with variables" },
  { role: "assistant", content: '{"quality": "4"}' },
]

function link(container: HTMLElement): HTMLButtonElement | null {
  return container.querySelector("button.link")
}

function dialog(container: HTMLElement): Element | null {
  return container.querySelector('[data-title="Judge Trace"]')
}

describe("JudgeTraceLink", () => {
  it("renders nothing without a trace or a loader", () => {
    const { container } = render(JudgeTraceLink)
    expect(link(container)).toBeNull()
    expect(dialog(container)).toBeNull()
  })

  it("treats an empty trace as no trace", () => {
    const { container } = render(JudgeTraceLink, { props: { trace: [] } })
    expect(link(container)).toBeNull()
  })

  it("uses the same quiet link style and casing as View reasoning", () => {
    const { container } = render(JudgeTraceLink, { props: { trace: TRACE } })
    const button = link(container)!
    expect(button.className).toBe("text-xs link link-hover text-gray-400")
    expect(button.textContent?.trim()).toBe("Judge trace")
  })

  it("opens in an extra-wide dialog", () => {
    const { container } = render(JudgeTraceLink, { props: { trace: TRACE } })
    expect(dialog(container)!.getAttribute("data-width")).toBe("extra_wide")
  })

  it("mounts the trace only once the link is clicked", async () => {
    const { container } = render(JudgeTraceLink, { props: { trace: TRACE } })
    expect(dialog(container)!.textContent).not.toContain(
      "Rendered judge prompt",
    )

    await fireEvent.click(link(container)!)

    expect(dialog(container)!.textContent).toContain("Rendered judge prompt")
  })

  it("opens with every message collapsed", async () => {
    const { container } = render(JudgeTraceLink, { props: { trace: TRACE } })
    await fireEvent.click(link(container)!)

    const toggles = Array.from(
      dialog(container)!.querySelectorAll<HTMLInputElement>(
        'input[type="checkbox"]',
      ),
    )
    expect(toggles).toHaveLength(TRACE.length)
    expect(toggles.every((toggle) => !toggle.checked)).toBe(true)
  })

  it("fetches the trace on first click, not before, and only once", async () => {
    const load_trace = vi.fn().mockResolvedValue(TRACE)
    const { container } = render(JudgeTraceLink, { props: { load_trace } })
    expect(load_trace).not.toHaveBeenCalled()

    await fireEvent.click(link(container)!)
    await waitFor(() =>
      expect(dialog(container)!.textContent).toContain("Rendered judge prompt"),
    )
    await fireEvent.click(link(container)!)

    expect(load_trace).toHaveBeenCalledTimes(1)
  })

  it("shows a spinner while the trace loads", async () => {
    let resolve: (trace: Trace) => void = () => {}
    const load_trace = () =>
      new Promise<Trace>((r) => {
        resolve = r
      })
    const { container } = render(JudgeTraceLink, { props: { load_trace } })

    await fireEvent.click(link(container)!)
    expect(
      container.querySelector('[data-testid="judge-trace-loading"]'),
    ).not.toBeNull()

    resolve(TRACE)
    await waitFor(() =>
      expect(
        container.querySelector('[data-testid="judge-trace-loading"]'),
      ).toBeNull(),
    )
    expect(dialog(container)!.textContent).toContain("Rendered judge prompt")
  })

  it("shows the error when loading fails, and retries on the next click", async () => {
    const load_trace = vi
      .fn()
      .mockRejectedValueOnce(new Error("Eval run not found"))
      .mockResolvedValueOnce(TRACE)
    const { container } = render(JudgeTraceLink, { props: { load_trace } })

    await fireEvent.click(link(container)!)
    await waitFor(() =>
      expect(dialog(container)!.textContent).toContain("Eval run not found"),
    )

    await fireEvent.click(link(container)!)
    await waitFor(() =>
      expect(dialog(container)!.textContent).toContain("Rendered judge prompt"),
    )
    expect(load_trace).toHaveBeenCalledTimes(2)
  })

  it("says so when the loader finds no trace", async () => {
    const load_trace = vi.fn().mockResolvedValue(null)
    const { container } = render(JudgeTraceLink, { props: { load_trace } })

    await fireEvent.click(link(container)!)

    await waitFor(() =>
      expect(dialog(container)!.textContent).toContain(
        "No judge trace was saved for this run.",
      ),
    )
  })
})
