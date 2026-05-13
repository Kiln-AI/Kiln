// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from "vitest"
import { render, cleanup, fireEvent } from "@testing-library/svelte"
import Trace from "./trace.svelte"
import type { Trace as TraceType, TraceMessage } from "$lib/types"

afterEach(() => cleanup())

function userMsg(content: string): TraceMessage {
  return { role: "user", content } as TraceMessage
}

function assistantMsg(
  content: string | null,
  extras: Partial<{
    tool_calls: unknown[]
    reasoning_content: string
  }> = {},
): TraceMessage {
  return {
    role: "assistant",
    content,
    ...extras,
  } as TraceMessage
}

function systemMsg(content: string): TraceMessage {
  return { role: "system", content } as TraceMessage
}

function toolMsg(content: string, tool_call_id = "call_1"): TraceMessage {
  return { role: "tool", content, tool_call_id } as TraceMessage
}

async function expandAll(container: HTMLElement): Promise<void> {
  const inputs = container.querySelectorAll<HTMLInputElement>(
    "input[type=checkbox]",
  )
  for (const input of Array.from(inputs)) {
    await fireEvent.click(input)
  }
}

describe("Trace component", () => {
  it("renders one collapsible block per message in the trace", () => {
    const trace: TraceType = [
      systemMsg("you are helpful"),
      userMsg("hi"),
      assistantMsg("hello there"),
    ]
    const { container } = render(Trace, { props: { trace } })
    const collapses = container.querySelectorAll(".collapse")
    expect(collapses.length).toBe(3)
  })

  it("shows the role label for each message block", () => {
    const trace: TraceType = [
      systemMsg("s"),
      userMsg("u"),
      assistantMsg("a"),
      toolMsg('{"r":1}'),
    ]
    const { container } = render(Trace, { props: { trace } })
    const text = container.textContent || ""
    // Role labels use CSS uppercase, so the DOM has display-case strings.
    expect(text).toContain("System")
    expect(text).toContain("User")
    expect(text).toContain("Assistant")
    expect(text).toContain("Tool")
  })

  it("starts with all blocks collapsed (no expanded content rendered)", () => {
    const trace: TraceType = [
      userMsg("u1"),
      assistantMsg("a1", { reasoning_content: "thinking" }),
    ]
    const { container } = render(Trace, { props: { trace } })
    // Reasoning content header should not appear until expanded.
    expect(container.textContent).not.toContain("Reasoning")
  })

  it("renders content with raw Output (pre) by default for non-tool messages", async () => {
    const trace: TraceType = [assistantMsg("**bold markdown**")]
    const { container } = render(Trace, { props: { trace } })
    await expandAll(container)
    // Output renders into a <pre> with the raw text, NOT a <strong>.
    const pre = container.querySelector("pre")
    expect(pre).not.toBeNull()
    expect(pre?.textContent).toContain("**bold markdown**")
    expect(container.querySelector("strong")).toBeNull()
  })

  it("renders content as Markdown when markdown_content is true for non-tool messages", async () => {
    const trace: TraceType = [assistantMsg("**bold markdown**")]
    const { container } = render(Trace, {
      props: { trace, markdown_content: true },
    })
    await expandAll(container)
    // ChatMarkdown converts **bold** to <strong>bold</strong>.
    const strong = container.querySelector("strong")
    expect(strong).not.toBeNull()
    expect(strong?.textContent).toBe("bold markdown")
  })

  it("renders user content as Markdown when markdown_content is true", async () => {
    const trace: TraceType = [userMsg("**hello user**")]
    const { container } = render(Trace, {
      props: { trace, markdown_content: true },
    })
    await expandAll(container)
    const strong = container.querySelector("strong")
    expect(strong).not.toBeNull()
    expect(strong?.textContent).toBe("hello user")
  })

  it("never renders tool results as Markdown even when markdown_content is true", async () => {
    const trace: TraceType = [toolMsg("**raw json please**", "call_x")]
    const { container } = render(Trace, {
      props: { trace, markdown_content: true },
    })
    await expandAll(container)
    // Tool result must remain in a <pre> (raw Output), not as <strong>.
    const pre = container.querySelector("pre")
    expect(pre).not.toBeNull()
    expect(pre?.textContent).toContain("**raw json please**")
    expect(container.querySelector("strong")).toBeNull()
  })

  it("renders reasoning content as Markdown when markdown_content is true", async () => {
    const trace: TraceType = [
      assistantMsg("done", { reasoning_content: "**deep thought**" }),
    ]
    const { container } = render(Trace, {
      props: { trace, markdown_content: true },
    })
    await expandAll(container)
    expect(container.textContent).toContain("Reasoning")
    const strong = container.querySelector("strong")
    expect(strong).not.toBeNull()
    expect(strong?.textContent).toBe("deep thought")
  })

  it("renders reasoning content as raw Output by default (no markdown)", async () => {
    const trace: TraceType = [
      assistantMsg("done", { reasoning_content: "**deep thought**" }),
    ]
    const { container } = render(Trace, { props: { trace } })
    await expandAll(container)
    expect(container.textContent).toContain("Reasoning")
    expect(container.querySelector("strong")).toBeNull()
  })

  it("renders an empty trace without errors", () => {
    const { container } = render(Trace, { props: { trace: [] as TraceType } })
    const collapses = container.querySelectorAll(".collapse")
    expect(collapses.length).toBe(0)
  })
})

describe("Trace component — fork affordance", () => {
  function fork_button(container: HTMLElement) {
    return container.querySelectorAll<HTMLButtonElement>(
      'button[aria-label="Fork from this turn"]',
    )
  }

  it("does NOT render a fork button when the user block is collapsed", () => {
    const trace: TraceType = [
      systemMsg("s"),
      userMsg("u1"),
      assistantMsg("a1"),
      userMsg("u2"),
      assistantMsg("a2"),
    ]
    const forkable_run_ids = [null, null, null, "run-2", null]
    const { container } = render(Trace, {
      props: { trace, forkable_run_ids, on_fork: vi.fn() },
    })
    // The fork button now lives inside the expanded content, so it must not
    // render while the user block is collapsed.
    expect(fork_button(container).length).toBe(0)
  })

  it("renders a fork button inside the expanded user block where forkable_run_ids[i] is set", async () => {
    const trace: TraceType = [
      systemMsg("s"),
      userMsg("u1"),
      assistantMsg("a1"),
      userMsg("u2"),
      assistantMsg("a2"),
    ]
    const forkable_run_ids = [null, null, null, "run-2", null]
    const { container } = render(Trace, {
      props: { trace, forkable_run_ids, on_fork: vi.fn() },
    })
    // Expand the forkable user block (index 3).
    const checkboxes = container.querySelectorAll<HTMLInputElement>(
      "input[type=checkbox]",
    )
    await fireEvent.click(checkboxes[3])
    const buttons = fork_button(container)
    expect(buttons.length).toBe(1)
  })

  it("does NOT render a fork button on non-user blocks even if forkable_run_ids[i] is set", async () => {
    const trace: TraceType = [systemMsg("s"), userMsg("u1"), assistantMsg("a1")]
    // Set entries on all blocks; only the user one should produce a button.
    const forkable_run_ids = ["run-sys", "run-user", "run-asst"]
    const { container } = render(Trace, {
      props: { trace, forkable_run_ids, on_fork: vi.fn() },
    })
    await expandAll(container)
    const buttons = fork_button(container)
    expect(buttons.length).toBe(1)
  })

  it("does NOT render any fork button when on_fork is not provided", async () => {
    const trace: TraceType = [userMsg("u1")]
    const forkable_run_ids = ["run-1"]
    const { container } = render(Trace, {
      props: { trace, forkable_run_ids },
    })
    await expandAll(container)
    expect(fork_button(container).length).toBe(0)
  })

  it("does NOT render a fork button when forkable_run_ids[i] is null", async () => {
    const trace: TraceType = [userMsg("u1")]
    const forkable_run_ids = [null]
    const { container } = render(Trace, {
      props: { trace, forkable_run_ids, on_fork: vi.fn() },
    })
    await expandAll(container)
    expect(fork_button(container).length).toBe(0)
  })

  it("invokes on_fork with the mapped run id and trace index, and does not toggle the collapse", async () => {
    const trace: TraceType = [
      systemMsg("s"),
      userMsg("u1"),
      assistantMsg("a1"),
      userMsg("u2"),
    ]
    const forkable_run_ids = [null, null, null, "run-leaf"]
    const on_fork = vi.fn()
    const { container } = render(Trace, {
      props: { trace, forkable_run_ids, on_fork },
    })
    // The fork button is inside the expanded block — expand the target user
    // block (index 3) first.
    const checkboxes = container.querySelectorAll<HTMLInputElement>(
      "input[type=checkbox]",
    )
    const target_checkbox = checkboxes[3]
    await fireEvent.click(target_checkbox)
    expect(target_checkbox.checked).toBe(true)
    const button = fork_button(container)[0]
    expect(button).toBeDefined()
    await fireEvent.click(button)
    expect(on_fork).toHaveBeenCalledTimes(1)
    expect(on_fork).toHaveBeenCalledWith("run-leaf", 3)
    // The button lives inside .collapse-content (not the click-toggle
    // target), so clicking it must not toggle the collapse back to
    // collapsed.
    expect(target_checkbox.checked).toBe(true)
  })

  it("hides messages at or after truncate_at_trace_index", () => {
    const trace: TraceType = [
      systemMsg("s"),
      userMsg("u1"),
      assistantMsg("a1"),
      userMsg("u2"),
      assistantMsg("a2"),
    ]
    const { container } = render(Trace, {
      props: { trace, truncate_at_trace_index: 3 },
    })
    // Only indices 0..2 should render -> 3 collapses.
    const collapses = container.querySelectorAll(".collapse")
    expect(collapses.length).toBe(3)
  })
})
